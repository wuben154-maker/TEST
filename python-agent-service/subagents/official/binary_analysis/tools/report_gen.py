"""ReportGenTool — dual-format analyst report (FR-15, NFR-12, C13).

The report pipeline has three layers, from pure to side-effectful:

1. :func:`build_report_v1` — pure function mapping an
   :class:`~schema.evidence_chain.EvidenceChainSnapshot`
   to a frozen :class:`~schema.report.ReportV1` model
   (FR-15 AC-1/5/6/7).  No I/O; trivially unit-testable.
2. :func:`render_json` / :func:`render_markdown` — pure serialisers
   producing the two FR-15 output formats.  JSON keys stay English for
   downstream schema stability (NFR-12); Markdown prose is Chinese
   (FR-15 AC-2).
3. :class:`ReportGenTool` — LangChain ``BaseTool`` wrapper that writes
   the two report files under ``output_dir`` using the FR-15 AC-8
   ``<sha256>.report.{json,md}`` naming convention and cleans the
   host-side ``<tmp_root>/deepagent-analyze-<analysis_id>/`` directory
   (IR-03, FR-15 AC-10).

Red lines
---------

- JSON schema is frozen at v1.0.0 (NFR-12).  Never add a breaking field
  change without bumping :data:`ReportV1.schema_version` major.
- Markdown report is advisory / analyst-facing: the authoritative source
  of truth for downstream integrations is the JSON format.
- The tool NEVER writes back into the evidence chain; it only produces
  output artefacts.  No new bucket is introduced.
- Cleanup operates only on ``<tmp_root>/deepagent-analyze-<analysis_id>/``
  (IR-03).  The ``output_dir`` is out of scope for cleanup — the caller
  decides where final artefacts live.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path, PurePath
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from evidence_chain.store import EvidenceChainStore
from schema.document_enums import (
    DocumentFormat,
    DocumentRole,
    DocumentTier,
    UnknownDowngradeReason,
)
from schema.evidence_chain import Bucket, EvidenceChainSnapshot
from schema.indicator import Confidence, Indicator
from schema.report import (
    MARKDOWN_DEGRADATION_SUGGESTIONS,
    MARKDOWN_DEGRADED_BEHAVIOR,
    MARKDOWN_DEGRADED_DISASSEMBLY,
    MARKDOWN_REPORT_TITLE,
    MARKDOWN_SECTIONS,
    AnalysisCoverage,
    BehaviorChain,
    BehaviorEdge,
    BehaviorNode,
    CoverageStatus,
    EscalationLevel,
    EscalationRecommendation,
    FileMeta,
    Fingerprints,
    MalwareFamily,
    ReportV1,
    RiskScore,
    ThreatClass,
    Verdict,
    VerdictLabel,
)

# ---------------------------------------------------------------------------
# Analysis-coverage dimensions (FR-15 AC-6)
# ---------------------------------------------------------------------------

FR17_PHASE1_MISSING_GAP: str = "fr17_phase1_missing"
"""Gap marker emitted when FR-17 Phase 2 output exists without Phase 1 output.

ADR-07 mandates a module-first, function-second behavior-chain strategy:
Phase 1 clusters the call graph into ``module_behavior_node`` inferences
before Phase 2 drills down into ``function_behavior_node``s.  When
``build_report_v1`` observes ``function_behavior_node`` indicators with
zero prior ``module_behavior_node``, the ADR-07 ordering has been
violated; FR-15 surfaces this by appending :data:`FR17_PHASE1_MISSING_GAP`
to :attr:`AnalysisCoverage.gaps` and downgrading the ``behavior_chain``
dimension from ``COMPLETED`` to ``DEGRADED``.

This is a prompt-level enforcement path (ADR-07 has no Python state
machine); the gap marker is what the agent's next self-consistency
round is expected to notice and remediate.
"""

_COVERAGE_BUCKET_MAP: dict[str, tuple[Bucket, ...]] = {
    "structure": (
        Bucket.headers,
        Bucket.imports,
        Bucket.exports,
        Bucket.sections,
        Bucket.resources,
    ),
    "entropy": (Bucket.entropy,),
    "strings": (Bucket.strings_iocs,),
    "decompilation": (Bucket.disassembly,),
    "behavior_chain": (Bucket.behavior_chain,),
    "llm_inferences": (Bucket.llm_inferences,),
}
"""Mapping from FR-15 AC-6 dimension names to their backing evidence buckets."""


# ---------------------------------------------------------------------------
# Snapshot extractors — pure
# ---------------------------------------------------------------------------


def _first_file_meta(snapshot: EvidenceChainSnapshot) -> Indicator:
    """Return the FR-01 ``file_meta`` Indicator or raise if absent.

    Prefers the most recent Indicator that carries a populated
    ``fingerprints`` block (produced by FileIdentifyTool, FR-01).  Falls
    back to the first ``file_meta`` Indicator and ultimately raises when
    the bucket is empty.
    """
    if not snapshot.file_meta:
        msg = (
            "evidence chain has no file_meta Indicator — ReportGenTool "
            "requires FileIdentifyTool (FR-01) to have run first"
        )
        raise ValueError(msg)
    for ind in reversed(snapshot.file_meta):
        fingerprints = ind.data.get("fingerprints")
        if isinstance(fingerprints, dict) and fingerprints.get("sha256"):
            return ind
    return snapshot.file_meta[0]


def _last_by_type(indicators: list[Indicator], indicator_type: str) -> Indicator | None:
    """Return the most recent Indicator of the given type, or ``None``."""
    for ind in reversed(indicators):
        if ind.indicator_type == indicator_type:
            return ind
    return None


def _file_meta_and_fingerprints(
    snapshot: EvidenceChainSnapshot, *, analysis_id: str
) -> tuple[FileMeta, Fingerprints]:
    """Extract :class:`FileMeta` + :class:`Fingerprints` from the FR-01 Indicator."""
    ind = _first_file_meta(snapshot)
    data = ind.data
    fingerprints_raw: dict[str, Any] = data.get("fingerprints") or {}

    sha256 = str(fingerprints_raw.get("sha256", ""))
    md5 = str(fingerprints_raw.get("md5", ""))
    sha1 = str(fingerprints_raw.get("sha1", ""))
    if not sha256 or not md5 or not sha1:
        msg = (
            "file_meta Indicator missing required fingerprints (sha256 / md5 "
            "/ sha1); FR-01 FileIdentifyTool must populate all three"
        )
        raise ValueError(msg)

    absolute_path = str(data.get("absolute_path", ""))
    file_name = Path(absolute_path).name or "unknown"

    file_meta = FileMeta(
        file_name=file_name,
        file_size=int(data.get("size_bytes", 0)),
        file_type=str(data.get("format", "unknown")),
        architecture=str(data.get("arch", "unknown")),
        analysis_id=analysis_id,
        mime_type=data.get("mime_type"),
        platform=data.get("platform") or data.get("routing"),
    )
    fingerprints = Fingerprints(
        sha256=sha256,
        md5=md5,
        sha1=sha1,
        imphash=fingerprints_raw.get("imphash"),
        ssdeep=fingerprints_raw.get("ssdeep"),
        tlsh=fingerprints_raw.get("tlsh"),
        rich_header_hash=fingerprints_raw.get("rich_header_hash"),
    )
    return file_meta, fingerprints


def _verdict_and_risk(
    snapshot: EvidenceChainSnapshot,
) -> tuple[Verdict, RiskScore]:
    """Extract :class:`Verdict` + :class:`RiskScore` from the scoring bucket."""
    scoring = _last_by_type(list(snapshot.scoring), "scoring")
    if scoring is None:
        return (
            Verdict(label=VerdictLabel.UNKNOWN, rule_score=0.0),
            RiskScore(score=0, rule_version="0.0.0"),
        )
    data = scoring.data
    label_raw = data.get("verdict") or data.get("verdict_label")
    try:
        label = VerdictLabel(str(label_raw))
    except ValueError:
        label = VerdictLabel.UNKNOWN
    llm_raw = data.get("llm_verdict") or data.get("llm_label")
    llm_label: VerdictLabel | None = None
    if isinstance(llm_raw, str):
        try:
            llm_label = VerdictLabel(llm_raw)
        except ValueError:
            llm_label = None
    rule_score = float(data.get("rule_score", 0))
    verdict = Verdict(
        label=label,
        rule_score=rule_score,
        llm_label=llm_label,
        verdict_divergence=data.get("verdict_divergence"),
    )
    risk = RiskScore(
        score=max(0, min(100, int(rule_score))),
        rule_version=str(
            data.get("rules_version") or data.get("rule_version", "0.0.0")
        ),
        contributing_indicator_ids=list(data.get("contributing_indicator_ids", [])),
    )
    return verdict, risk


def _threat_class_and_family(
    snapshot: EvidenceChainSnapshot,
) -> tuple[ThreatClass, MalwareFamily]:
    """Extract :class:`ThreatClass` + :class:`MalwareFamily` from scoring snapshot."""
    scoring = _last_by_type(list(snapshot.scoring), "scoring")
    if scoring is None:
        return (
            ThreatClass(classes=[]),
            MalwareFamily(name="Unknown Family", confidence="LOW"),
        )
    data = scoring.data
    threat_class = ThreatClass(
        classes=list(data.get("threat_classes", [])),
        confidence=data.get("threat_class_confidence"),
    )
    family = MalwareFamily(
        name=str(data.get("family_name") or "Unknown Family"),
        confidence=str(data.get("family_confidence") or "LOW"),
        evidence_refs=list(data.get("family_evidence_refs", [])),
    )
    return threat_class, family


def _escalation(snapshot: EvidenceChainSnapshot) -> EscalationRecommendation:
    """Extract :class:`EscalationRecommendation` from the decision_gate bucket."""
    gate = _last_by_type(list(snapshot.decision_gate), "decision_gate")
    if gate is None:
        return EscalationRecommendation(level=EscalationLevel.NONE)
    data = gate.data
    level_raw = str(data.get("recommended_escalation", "NONE"))
    # Flatten BOTH → MANUAL_REVERSE on the report schema (v1 EscalationLevel
    # only models NONE/SANDBOX/MANUAL_REVERSE; sandbox reason is still
    # carried via ``reasons``).
    try:
        level = EscalationLevel(level_raw)
    except ValueError:
        level = (
            EscalationLevel.MANUAL_REVERSE
            if level_raw == "BOTH"
            else EscalationLevel.NONE
        )
    reasons_raw = data.get("escalation_reasons", [])
    reasons = [
        str(r.get("reason_text", "")) for r in reasons_raw if isinstance(r, dict)
    ]
    evidence_gaps = [str(gap) for gap in data.get("evidence_gaps", [])]
    return EscalationRecommendation(
        level=level,
        reasons=[r for r in reasons if r],
        evidence_gaps=evidence_gaps,
    )


_BEHAVIOR_EDGE_TYPES: frozenset[str] = frozenset(
    {
        "module_behavior_edge",
        "function_behavior_edge",
        "callgraph_edge",
    }
)
"""Indicator types that describe graph relationships rather than nodes."""

_BEHAVIOR_HIDDEN_TYPES: frozenset[str] = frozenset(
    {
        "analysis_coverage",
        "module_selection",
    }
)
"""Behavior-chain Indicators that should not become analyst-facing graph nodes."""

_BEHAVIOR_NODE_LABEL_KEYS: tuple[str, ...] = (
    "segment",
    "step_label",
    "label",
    "name",
    "function_name",
    "function",
    "module_id",
    "capability",
    "primary_technique",
)

_BEHAVIOR_NODE_ALIAS_KEYS: tuple[str, ...] = (
    "node_id",
    "module_id",
    "function_id",
    "function_address",
    "function_name",
    "function",
    "address",
    "name",
    "label",
    "segment",
)

_BEHAVIOR_EDGE_KEY_PAIRS: tuple[tuple[str, str], ...] = (
    ("src", "dst"),
    ("source", "target"),
    ("caller", "callee"),
    ("caller_id", "callee_id"),
    ("caller_name", "callee_name"),
    ("from", "to"),
)

_BEHAVIOR_EDGE_LABEL_KEYS: tuple[str, ...] = (
    "edge_kind",
    "label",
    "relation",
    "relationship",
    "type",
)

_STATIC_BEHAVIOR_GAP: str = "行为链为静态证据降级图，缺少反编译调用图验证。"
"""Coverage note used when report_gen renders a best-effort static graph."""

_STATIC_BEHAVIOR_API_MAP: dict[str, tuple[str, ...]] = {
    "process_injection": (
        "openprocess",
        "virtualallocex",
        "writeprocessmemory",
        "createremotethread",
        "ntcreatethreadex",
        "ntqueueapcthread",
        "setthreadcontext",
        "ntmapviewofsection",
    ),
    "network_c2": (
        "internetopen",
        "internetconnect",
        "httpsendrequest",
        "winhttpopen",
        "winhttpconnect",
        "winhttpsendrequest",
        "wsastartup",
        "connect",
        "send",
        "recv",
        "dnsquery",
    ),
    "persistence": (
        "regsetvalue",
        "runonce",
        "\\run",
        "createservice",
        "startservice",
        "schtasks",
        "registertask",
        "startup",
    ),
    "crypto_or_config_decode": (
        "cryptacquirecontext",
        "cryptdecrypt",
        "cryptencrypt",
        "bcryptdecrypt",
        "bcryptencrypt",
        "cryptstringtobinary",
        "rc4",
        "aes",
    ),
    "anti_analysis": (
        "isdebuggerpresent",
        "checkremotedebuggerpresent",
        "ntqueryinformationprocess",
        "rdtsc",
        "gettickcount",
        "sleep",
    ),
    "dynamic_loading": (
        "loadlibrary",
        "getprocaddress",
        "ldrgetprocedureaddress",
        "virtualalloc",
        "virtualprotect",
    ),
}
"""Static API-to-capability map for degraded behavior graph generation."""


def _behavior_label(ind: Indicator) -> str:
    """Return a compact analyst-facing label for a behavior node Indicator."""
    for key in _BEHAVIOR_NODE_LABEL_KEYS:
        value = ind.data.get(key)
        if value not in (None, "", [], {}):
            if isinstance(value, list):
                return ", ".join(str(item) for item in value)
            return str(value)
    capabilities = ind.data.get("capabilities")
    if isinstance(capabilities, list) and capabilities:
        return ", ".join(str(item) for item in capabilities)
    return ind.indicator_type


def _indicator_is_static_signal(ind: Indicator) -> bool:
    """Return True when an Indicator is reliable enough for static fallback."""
    return ind.confidence is not Confidence.LOW


def _flatten_static_text(value: Any) -> list[str]:
    """Collect short scalar strings from nested indicator payload data."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten_static_text(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(_flatten_static_text(item))
        return out
    return []


def _static_capabilities_from_imports(
    snapshot: EvidenceChainSnapshot,
) -> dict[str, str]:
    """Map capability labels to backing Indicator IDs from import facts."""
    capabilities: dict[str, str] = {}
    for ind in snapshot.imports:
        if not _indicator_is_static_signal(ind):
            continue
        text = " ".join(_flatten_static_text(ind.data)).casefold()
        text = f"{ind.indicator_type} {text}"
        for capability, needles in _STATIC_BEHAVIOR_API_MAP.items():
            if capability not in capabilities and any(n in text for n in needles):
                capabilities[capability] = ind.id
    return capabilities


def _static_capabilities_from_strings(
    snapshot: EvidenceChainSnapshot,
) -> dict[str, str]:
    """Map IOC/string facts to coarse behavior capabilities."""
    capabilities: dict[str, str] = {}
    network_types = {"url", "domain", "ip", "c2", "http", "network"}
    persistence_types = {"registry", "autorun", "service", "scheduled_task", "startup"}
    for ind in snapshot.strings_iocs:
        if not _indicator_is_static_signal(ind):
            continue
        indicator_type = ind.indicator_type.casefold()
        text = " ".join(_flatten_static_text(ind.data)).casefold()
        if any(token in indicator_type or token in text for token in network_types):
            capabilities.setdefault("network_c2_candidate", ind.id)
        if any(token in indicator_type or token in text for token in persistence_types):
            capabilities.setdefault("persistence_candidate", ind.id)
        if "anti_debug" in indicator_type or "debugger" in text:
            capabilities.setdefault("anti_analysis", ind.id)
        if "mutex" in indicator_type:
            capabilities.setdefault("mutex_or_instance_guard", ind.id)
    return capabilities


def _static_behavior_nodes(snapshot: EvidenceChainSnapshot) -> list[BehaviorNode]:
    """Build best-effort static behavior nodes without claiming callgraph edges."""
    node_specs: list[tuple[str, str, str, dict[str, Any]]] = []
    if any(_indicator_is_static_signal(ind) for ind in snapshot.packer):
        ind = next(ind for ind in snapshot.packer if _indicator_is_static_signal(ind))
        packer = ind.data.get("packer") or ind.indicator_type
        node_specs.append(
            (
                "packed_or_protected",
                f"Packed/protected sample: {packer}",
                ind.id,
                {"source": "static_fallback", "capability": "anti_analysis"},
            )
        )
    if any(_indicator_is_static_signal(ind) for ind in snapshot.embedded_payloads):
        ind = next(
            ind
            for ind in snapshot.embedded_payloads
            if _indicator_is_static_signal(ind)
        )
        fmt = ind.data.get("suggested_format") or ind.data.get("type") or "payload"
        node_specs.append(
            (
                "embedded_payload",
                f"Embedded payload staging: {fmt}",
                ind.id,
                {"source": "static_fallback", "capability": "staging"},
            )
        )
    capabilities = {
        **_static_capabilities_from_imports(snapshot),
        **_static_capabilities_from_strings(snapshot),
    }
    for capability, indicator_id in sorted(capabilities.items()):
        label = capability.replace("_", " ")
        node_specs.append(
            (
                capability,
                label,
                indicator_id,
                {"source": "static_fallback", "capability": capability},
            )
        )
    return [
        BehaviorNode(
            node_id=f"static_{idx}",
            label=label,
            indicator_id=indicator_id,
            metadata={**metadata, "static_node_key": key},
        )
        for idx, (key, label, indicator_id, metadata) in enumerate(node_specs, 1)
    ]


def _static_behavior_chain(snapshot: EvidenceChainSnapshot) -> BehaviorChain:
    """Return a degraded static behavior graph when FR-17 produced no nodes."""
    nodes = _static_behavior_nodes(snapshot)
    edges = [
        BehaviorEdge(
            source=nodes[idx].node_id,
            target=nodes[idx + 1].node_id,
            label="static_evidence",
        )
        for idx in range(len(nodes) - 1)
    ]
    return BehaviorChain(nodes=nodes, edges=edges)


def _is_behavior_node_indicator(ind: Indicator) -> bool:
    """Return True when a behavior-chain Indicator should render as a graph node."""
    if ind.indicator_type in _BEHAVIOR_EDGE_TYPES:
        return False
    return ind.indicator_type not in _BEHAVIOR_HIDDEN_TYPES


def _normalise_graph_key(value: Any) -> str | None:
    """Normalise endpoint aliases for graph-node lookup."""
    if value in (None, "", [], {}):
        return None
    if isinstance(value, (list, tuple, set)):
        return None
    return str(value).strip()


def _register_node_alias(aliases: dict[str, str], raw_value: Any, node_id: str) -> None:
    """Register exact and case-folded lookup aliases for a graph node."""
    key = _normalise_graph_key(raw_value)
    if key is None:
        return
    aliases.setdefault(key, node_id)
    aliases.setdefault(key.casefold(), node_id)


def _behavior_node_aliases(ind: Indicator) -> list[Any]:
    """Return values that may identify a node from an edge Indicator."""
    aliases: list[Any] = [ind.id]
    aliases.extend(ind.data.get(key) for key in _BEHAVIOR_NODE_ALIAS_KEYS)
    aliases.extend(ind.derived_from)
    return aliases


def _edge_endpoint_from_data(ind: Indicator) -> tuple[Any, Any] | None:
    """Read the first recognised source/target pair from an edge Indicator."""
    for source_key, target_key in _BEHAVIOR_EDGE_KEY_PAIRS:
        source = ind.data.get(source_key)
        target = ind.data.get(target_key)
        if source not in (None, "", [], {}) and target not in (None, "", [], {}):
            return source, target
    return None


def _edge_endpoint_from_refs(
    ind: Indicator, aliases: dict[str, str]
) -> tuple[str, str] | None:
    """Resolve the first two node-like evidence refs for an edge Indicator."""
    refs = [
        ref for ref in ind.evidence_refs if ref in aliases or ref.casefold() in aliases
    ]
    if len(refs) < 2:
        return None
    return refs[0], refs[1]


def _resolve_node_ref(raw_value: Any, aliases: dict[str, str]) -> str | None:
    """Resolve an edge endpoint value into an internal BehaviorNode id."""
    key = _normalise_graph_key(raw_value)
    if key is None:
        return None
    return aliases.get(key) or aliases.get(key.casefold())


def _edge_label(ind: Indicator) -> str:
    """Return the best available Mermaid edge label for an edge Indicator."""
    for key in _BEHAVIOR_EDGE_LABEL_KEYS:
        value = ind.data.get(key)
        if value not in (None, "", [], {}):
            return str(value)
    if ind.indicator_type in _BEHAVIOR_EDGE_TYPES:
        return "control_flow"
    return "next"


def _behavior_chain(snapshot: EvidenceChainSnapshot) -> BehaviorChain:
    """Convert the ``behavior_chain`` bucket into node/edge arrays (FR-15 AC-7).

    Node Indicators (``module_behavior_node``, ``function_behavior_node``,
    and legacy displayable behavior rows) become graph nodes.  Edge
    Indicators are parsed from explicit source/target fields first and from
    node-like ``evidence_refs`` second.  Legacy chains with no parseable edge
    Indicators keep the historical insertion-order ``next`` fallback.
    """
    nodes: list[BehaviorNode] = []
    aliases: dict[str, str] = {}
    node_indicators = [
        ind for ind in snapshot.behavior_chain if _is_behavior_node_indicator(ind)
    ]
    for idx, ind in enumerate(node_indicators):
        node_id = f"n{idx + 1}"
        nodes.append(
            BehaviorNode(
                node_id=node_id,
                label=_behavior_label(ind),
                indicator_id=ind.id,
                metadata={
                    k: v
                    for k, v in ind.data.items()
                    if k
                    in {
                        "segment",
                        "technique",
                        "mitre",
                        "mitre_attack",
                        "module_id",
                        "function_address",
                        "function_name",
                        "capability",
                        "capabilities",
                    }
                },
            )
        )
        for alias in _behavior_node_aliases(ind):
            _register_node_alias(aliases, alias, node_id)

    edge_indicators = [
        ind
        for ind in (*snapshot.behavior_chain, *snapshot.disassembly)
        if ind.indicator_type in _BEHAVIOR_EDGE_TYPES
    ]
    edges: list[BehaviorEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for ind in edge_indicators:
        endpoint = _edge_endpoint_from_data(ind) or _edge_endpoint_from_refs(
            ind, aliases
        )
        if endpoint is None:
            continue
        source = _resolve_node_ref(endpoint[0], aliases)
        target = _resolve_node_ref(endpoint[1], aliases)
        if source is None or target is None:
            continue
        label = _edge_label(ind)
        edge_key = (source, target, label)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append(BehaviorEdge(source=source, target=target, label=label))

    if not edges:
        edges = [
            BehaviorEdge(
                source=nodes[i].node_id, target=nodes[i + 1].node_id, label="next"
            )
            for i in range(len(nodes) - 1)
        ]
    chain = BehaviorChain(nodes=nodes, edges=edges)
    if not chain.nodes:
        return _static_behavior_chain(snapshot)
    return chain


def _coverage_status_for_dimension(
    snapshot: EvidenceChainSnapshot, dimension: str, buckets: tuple[Bucket, ...]
) -> CoverageStatus:
    """Derive the FR-15 AC-6 coverage status for a single dimension.

    Explicit DEGRADED / SKIPPED markers (Indicators with
    ``indicator_type='analysis_coverage'`` whose ``data.dimension ==
    dimension``) take precedence over bucket-presence heuristics.
    """
    for field_name in snapshot.__class__.model_fields:
        for ind in getattr(snapshot, field_name):
            if ind.indicator_type != "analysis_coverage":
                continue
            if str(ind.data.get("dimension")) != dimension:
                continue
            status_raw = str(ind.data.get("status", ""))
            try:
                return CoverageStatus(status_raw)
            except ValueError:
                continue
    for bucket in buckets:
        if getattr(snapshot, bucket.value):
            return CoverageStatus.COMPLETED
    return CoverageStatus.SKIPPED


def _has_fr17_phase1_gap(snapshot: EvidenceChainSnapshot) -> bool:
    """Return ``True`` when Phase 2 output exists without Phase 1 output.

    The check inspects the ``behavior_chain`` bucket for ADR-07 ordering:
    ``function_behavior_node`` indicators (Phase 2) are only legitimate
    once at least one ``module_behavior_node`` (Phase 1) has been written.
    Absence of *both* indicator types is not a gap (that's the normal
    skipped / mechanical-segment path handled elsewhere) — only the
    strict "Phase 2 without Phase 1" pattern returns ``True``.
    """
    has_module_node = False
    has_function_node = False
    for ind in snapshot.behavior_chain:
        if ind.indicator_type == "module_behavior_node":
            has_module_node = True
        elif ind.indicator_type == "function_behavior_node":
            has_function_node = True
    return has_function_node and not has_module_node


def _analysis_coverage(
    snapshot: EvidenceChainSnapshot, *, behavior_chain: BehaviorChain | None = None
) -> AnalysisCoverage:
    """Build the :class:`AnalysisCoverage` summary (FR-15 AC-6)."""
    dimensions: dict[str, CoverageStatus] = {
        name: _coverage_status_for_dimension(snapshot, name, buckets)
        for name, buckets in _COVERAGE_BUCKET_MAP.items()
    }
    gaps: list[str] = []
    if dimensions["decompilation"] is not CoverageStatus.COMPLETED:
        gaps.append(MARKDOWN_DEGRADED_DISASSEMBLY)
    if dimensions["behavior_chain"] is not CoverageStatus.COMPLETED:
        if behavior_chain is not None and behavior_chain.nodes:
            dimensions["behavior_chain"] = CoverageStatus.DEGRADED
            gaps.append(_STATIC_BEHAVIOR_GAP)
        else:
            gaps.append(MARKDOWN_DEGRADED_BEHAVIOR)
    if _has_fr17_phase1_gap(snapshot):
        gaps.append(FR17_PHASE1_MISSING_GAP)
        # ADR-07 violation: Phase 2 nodes cannot stand alone. Downgrade
        # the behavior_chain dimension to DEGRADED so FR-14 / FR-15
        # consumers treat the section as low-confidence, without
        # overwriting an already DEGRADED / SKIPPED status upstream.
        if dimensions["behavior_chain"] is CoverageStatus.COMPLETED:
            dimensions["behavior_chain"] = CoverageStatus.DEGRADED
    return AnalysisCoverage(dimensions=dimensions, gaps=gaps)


# ---------------------------------------------------------------------------
# v1.1.0 document-field extractors (FR-15 AC-3, C11)
# ---------------------------------------------------------------------------

_DOC_BUCKET_MAX_ITEMS: int = 20
"""Maximum number of Indicators harvested per document bucket for the summary."""


def _extract_document_format(snapshot: EvidenceChainSnapshot) -> DocumentFormat | None:
    """Read ``document_format`` from the most recent FR-01 file_meta Indicator."""
    try:
        ind = _first_file_meta(snapshot)
    except ValueError:
        return None
    raw = ind.data.get("document_format")
    if raw is None:
        return None
    try:
        return DocumentFormat(str(raw))
    except ValueError:
        return None


def _extract_document_tier(snapshot: EvidenceChainSnapshot) -> DocumentTier | None:
    """Read ``document_tier`` from the most recent FR-01 file_meta Indicator."""
    try:
        ind = _first_file_meta(snapshot)
    except ValueError:
        return None
    raw = ind.data.get("document_tier")
    if raw is None:
        return None
    try:
        return DocumentTier(str(raw))
    except ValueError:
        return None


def _extract_document_role(snapshot: EvidenceChainSnapshot) -> DocumentRole | None:
    """Read ``document_role`` from the most recent scoring Indicator (C9)."""
    scoring = _last_by_type(list(snapshot.scoring), "scoring")
    if scoring is None:
        return None
    raw = scoring.data.get("document_role")
    if raw is None:
        return None
    try:
        return DocumentRole(str(raw))
    except ValueError:
        return None


def _extract_unknown_downgrade_reason(
    snapshot: EvidenceChainSnapshot,
) -> UnknownDowngradeReason | None:
    """Read ``unknown_downgrade_reason`` from the most recent scoring Indicator."""
    scoring = _last_by_type(list(snapshot.scoring), "scoring")
    if scoring is None:
        return None
    raw = scoring.data.get("unknown_downgrade_reason")
    if raw is None:
        return None
    try:
        return UnknownDowngradeReason(str(raw))
    except ValueError:
        return None


def _extract_doc_analysis_partial(snapshot: EvidenceChainSnapshot) -> bool:
    """Return True when any llm_inferences or scoring Indicator flags doc_analysis_partial."""
    for ind in reversed(list(snapshot.llm_inferences)):
        if ind.data.get("doc_analysis_partial") is True:
            return True
    scoring = _last_by_type(list(snapshot.scoring), "scoring")
    if scoring and scoring.data.get("doc_analysis_partial") is True:
        return True
    return False


def _extract_document_analysis(
    snapshot: EvidenceChainSnapshot,
) -> dict[str, Any] | None:
    """Merge data from the first N ``document_analysis`` Indicators into a summary dict."""
    inds = list(snapshot.document_analysis)
    if not inds:
        return None
    merged: dict[str, Any] = {}
    for ind in inds[:_DOC_BUCKET_MAX_ITEMS]:
        merged.update(ind.data)
    return merged or None


def _extract_macro_analysis(snapshot: EvidenceChainSnapshot) -> dict[str, Any] | None:
    """Merge data from the first N ``macro_analysis`` Indicators into a summary dict."""
    inds = list(snapshot.macro_analysis)
    if not inds:
        return None
    merged: dict[str, Any] = {}
    for ind in inds[:_DOC_BUCKET_MAX_ITEMS]:
        merged.update(ind.data)
    return merged or None


def _extract_embedded_payloads(
    snapshot: EvidenceChainSnapshot,
    child_reports: dict[str, ReportGenResult] | None = None,
) -> list[dict[str, Any]] | None:
    """Build the embedded-payloads summary list, injecting report_ref for child reports.

    For each embedded_payload Indicator, if the Indicator's child analysis
    identifier matches a key in *child_reports*, the entry receives a
    ``report_ref`` pointing to the child's JSON report file (FR-15 AC-5).
    New producers use ``child_sample_id``; older fixtures may still carry
    ``child_analysis_id``.
    """
    inds = list(snapshot.embedded_payloads)
    if not inds:
        return None
    result: list[dict[str, Any]] = []
    for ind in inds[:_DOC_BUCKET_MAX_ITEMS]:
        entry: dict[str, Any] = dict(ind.data)
        child_aid = entry.get("child_analysis_id") or entry.get("child_sample_id")
        if child_aid and child_reports and child_aid in child_reports:
            sha256 = entry.get("sha256", "")
            if sha256:
                entry["report_ref"] = f"{sha256}.report.json"
        result.append(entry)
    return result or None


def _extract_delivery_chain_doc(
    snapshot: EvidenceChainSnapshot,
) -> dict[str, Any] | None:
    """Return the last ``delivery_chain_doc`` Indicator's data as the hierarchy summary."""
    inds = list(snapshot.delivery_chain_doc)
    if not inds:
        return None
    return dict(inds[-1].data) or None


# ---------------------------------------------------------------------------
# Public pure entry point
# ---------------------------------------------------------------------------


def build_report_v1(
    snapshot: EvidenceChainSnapshot,
    *,
    analysis_id: str,
    child_reports: dict[str, ReportGenResult] | None = None,
) -> ReportV1:
    """Build a :class:`ReportV1` from an evidence-chain snapshot (pure).

    Args:
        snapshot: Frozen snapshot from
            :meth:`~binary_analysis.evidence_chain.store.EvidenceChainStore.snapshot`.
        analysis_id: ULID string identifying the analysis run (used as
            :attr:`FileMeta.analysis_id`).
        child_reports: Optional mapping from ``child_analysis_id`` to the
            :class:`ReportGenResult` produced for that child sample.  When
            supplied, ``embedded_payloads[].report_ref`` is filled with the
            child's ``<sha256>.report.json`` filename (FR-15 AC-5).

    Returns:
        A fully populated :class:`ReportV1` ready for JSON / Markdown
        rendering.

    Raises:
        ValueError: If the snapshot lacks an FR-01 ``file_meta`` Indicator
            or its fingerprints block is incomplete.
    """
    file_meta, fingerprints = _file_meta_and_fingerprints(
        snapshot, analysis_id=analysis_id
    )
    verdict, risk_score = _verdict_and_risk(snapshot)
    threat_class, malware_family = _threat_class_and_family(snapshot)
    escalation = _escalation(snapshot)
    behavior_chain = _behavior_chain(snapshot)
    coverage = _analysis_coverage(snapshot, behavior_chain=behavior_chain)
    return ReportV1(
        file_meta=file_meta,
        fingerprints=fingerprints,
        verdict=verdict,
        risk_score=risk_score,
        threat_class=threat_class,
        malware_family=malware_family,
        evidence_chain=snapshot,
        behavior_chain=behavior_chain,
        escalation_recommendation=escalation,
        analysis_coverage=coverage,
        # v1.1.0 document fields (FR-15 AC-3, C11)
        document_format=_extract_document_format(snapshot),
        document_tier=_extract_document_tier(snapshot),
        document_role=_extract_document_role(snapshot),
        doc_analysis_partial=_extract_doc_analysis_partial(snapshot),
        unknown_downgrade_reason=_extract_unknown_downgrade_reason(snapshot),
        document_analysis=_extract_document_analysis(snapshot),
        macro_analysis=_extract_macro_analysis(snapshot),
        embedded_payloads=_extract_embedded_payloads(snapshot, child_reports),
        delivery_chain_doc=_extract_delivery_chain_doc(snapshot),
    )


def _redact_indicator_data_absolute_path(data: dict[str, Any]) -> None:
    """Strip host filesystem layout from ``data['absolute_path']`` (in-place).

    Export-safe values: logical ``/workspace/...`` from the sandbox, or the
    bare filename. Prefer ``sandbox_path`` when present (FR-01).
    """
    ap = data.get("absolute_path")
    if not isinstance(ap, str) or not ap.strip():
        return
    sp = data.get("sandbox_path")
    if isinstance(sp, str) and sp.strip().startswith("/workspace/"):
        data["absolute_path"] = sp.strip()
        return
    norm = ap.replace("\\", "/").strip()
    if norm.startswith("/workspace/"):
        data["absolute_path"] = norm
        return
    if norm.startswith("workspace/"):
        data["absolute_path"] = "/" + norm
        return
    windows_abs = len(ap) >= 2 and ap[1] == ":"
    unix_host_abs = norm.startswith("/") and not norm.startswith("/workspace/")
    if "\\" in ap or windows_abs or unix_host_abs:
        data["absolute_path"] = PurePath(ap).name or "<redacted>"


def redact_report_for_export(report: ReportV1) -> ReportV1:
    """Return a copy of ``report`` with host paths redacted in ``evidence_chain``.

    FR-01 stores the resolved host path on disk in ``file_meta`` indicators for
    tooling; JSON/Markdown exports for analysts must not leak server layout
    (e.g. ``D:\\...\\uploads\\u_...``).

    The in-memory :class:`EvidenceChainStore` / live :class:`ReportV1` used
    during analysis is unchanged; only serialisation should call this (via
    :func:`render_json` / :func:`render_markdown`).
    """
    payload = copy.deepcopy(report.model_dump(mode="json"))
    ec = payload.get("evidence_chain")
    if not isinstance(ec, dict):
        return report
    for _bucket, items in ec.items():
        if not isinstance(items, list):
            continue
        for ind in items:
            if not isinstance(ind, dict):
                continue
            dat = ind.get("data")
            if isinstance(dat, dict):
                _redact_indicator_data_absolute_path(dat)
    return ReportV1.model_validate(payload)


# ---------------------------------------------------------------------------
# JSON rendering
# ---------------------------------------------------------------------------


def render_json(report: ReportV1, *, redact_host_paths: bool = True) -> str:
    """Render ``report`` as a stable, human-diffable JSON string.

    Uses ``ensure_ascii=False`` so non-ASCII Indicator fields (family
    names, Chinese reasons) stay readable; indents with two spaces for
    predictable diffs.

    Args:
        report: Fully populated :class:`ReportV1`.
        redact_host_paths: When ``True`` (default), evidence-chain
            ``file_meta.absolute_path`` values are replaced with
            ``sandbox_path`` or basename so host layout is not persisted
            (e.g. uploads dir, drive letters). Set ``False`` only for
            trusted debugging.

    Returns:
        A JSON string; callers are responsible for persisting it.
    """
    to_dump = redact_report_for_export(report) if redact_host_paths else report
    payload = to_dump.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Markdown rendering (FR-15 AC-2 / AC-5 / AC-7 / AC-9)
# ---------------------------------------------------------------------------


def _md_heading(key: str) -> str:
    """Return the ``## <heading>`` line for a canonical section key."""
    return f"## {MARKDOWN_SECTIONS[key]}"


def _md_footnote_refs(refs: list[str]) -> str:
    """Render a comma-joined footnote chain ``[^id1][^id2]`` for AC-5."""
    return "".join(f"[^{ref}]" for ref in refs)


def _section_summary(report: ReportV1) -> str:
    verdict_label = report.verdict.label.value
    family = report.malware_family.name
    score = report.risk_score.score
    classes = ", ".join(report.threat_class.classes) or "未分类"
    return (
        f"{_md_heading('summary')}\n\n"
        f"- 判定：**{verdict_label}**\n"
        f"- 风险评分：**{score}** / 100\n"
        f"- 家族归类：{family}（{report.malware_family.confidence}）\n"
        f"- 威胁类型：{classes}\n"
    )


def _section_fingerprints(report: ReportV1) -> str:
    fp = report.fingerprints
    fm = report.file_meta
    rows = [
        f"{_md_heading('fingerprints')}",
        "",
        f"- 文件名：`{fm.file_name}`",
        f"- 文件类型：{fm.file_type}（架构：{fm.architecture}）",
        f"- 文件大小：{fm.file_size} 字节",
        f"- SHA-256：`{fp.sha256}`",
        f"- MD5：`{fp.md5}`",
        f"- SHA-1：`{fp.sha1}`",
    ]
    if fp.imphash:
        rows.append(f"- IMPHASH：`{fp.imphash}`")
    if fp.ssdeep:
        rows.append(f"- SSDEEP：`{fp.ssdeep}`")
    if fp.tlsh:
        rows.append(f"- TLSH：`{fp.tlsh}`")
    rows.append("")
    return "\n".join(rows)


def _section_verdict(report: ReportV1) -> str:
    refs = _md_footnote_refs(report.risk_score.contributing_indicator_ids)
    divergence = (
        f"\n- LLM 旁证：{report.verdict.llm_label.value}（{report.verdict.verdict_divergence}）"
        if report.verdict.verdict_divergence and report.verdict.llm_label
        else ""
    )
    return (
        f"{_md_heading('verdict')}\n\n"
        f"- 结论：**{report.verdict.label.value}**{refs}\n"
        f"- 规则评分：{report.verdict.rule_score}"
        f"{divergence}\n"
    )


def _section_risk_score(report: ReportV1) -> str:
    refs = _md_footnote_refs(report.risk_score.contributing_indicator_ids)
    return (
        f"{_md_heading('risk_score')}\n\n"
        f"- 风险评分：**{report.risk_score.score}** / 100{refs}\n"
        f"- 规则版本：`{report.risk_score.rule_version}`\n"
        f"- 贡献指标数量：{len(report.risk_score.contributing_indicator_ids)}\n"
    )


def _section_behavior_chain(report: ReportV1) -> str:
    chain = report.behavior_chain
    degraded = (
        report.analysis_coverage.dimensions.get("behavior_chain")
        is not CoverageStatus.COMPLETED
    )
    if not chain.nodes:
        suggestion = MARKDOWN_DEGRADATION_SUGGESTIONS["behavior_chain"]
        return (
            f"{_md_heading('behavior_chain')}\n\n"
            f"- {MARKDOWN_DEGRADED_BEHAVIOR}\n"
            f"- 建议补充：{suggestion}\n"
        )
    intro = (
        "行为链为静态证据降级图，缺少反编译调用图验证；以下节点仅表示已观测到的能力证据。"
        if degraded
        else f"行为链包含 {len(chain.nodes)} 个节点 / {len(chain.edges)} 条边："
    )
    mermaid_lines = ["```mermaid", "graph TD"]
    for node in chain.nodes:
        mermaid_lines.append(f'    {node.node_id}["{node.label}"]')
    for edge in chain.edges:
        label = f"|{edge.label}|" if edge.label else ""
        mermaid_lines.append(f"    {edge.source} -->{label} {edge.target}")
    mermaid_lines.append("```")
    node_list = "\n".join(
        f"- `{n.node_id}` {n.label}"
        + (f"[^{n.indicator_id}]" if n.indicator_id else "")
        for n in chain.nodes
    )
    return (
        f"{_md_heading('behavior_chain')}\n\n"
        f"{intro}\n\n"
        f"{node_list}\n\n" + "\n".join(mermaid_lines) + "\n"
    )


def _section_iocs(report: ReportV1) -> str:
    iocs = report.evidence_chain.strings_iocs
    if not iocs:
        return f"{_md_heading('iocs')}\n\n- 未采集到 IOC 条目。\n"
    lines = [f"{_md_heading('iocs')}", ""]
    for ind in iocs:
        summary = ind.data.get("string") or ind.data.get("value") or ind.indicator_type
        lines.append(f"- `{summary}`（类型：{ind.indicator_type}）[^{ind.id}]")
    lines.append("")
    return "\n".join(lines)


def _section_structural_anomalies(report: ReportV1) -> str:
    snap = report.evidence_chain
    items: list[str] = []
    for bucket in (
        snap.headers,
        snap.sections,
        snap.imports,
        snap.packer,
        snap.entropy,
    ):
        for ind in bucket:
            if ind.severity.value == "INFO":
                continue
            summary = (
                ind.data.get("note")
                or ind.data.get("section")
                or ind.data.get("packer")
                or ind.indicator_type
            )
            items.append(f"- {ind.indicator_type}：{summary}[^{ind.id}]")
    body = "\n".join(items) if items else "- 未检测到显著结构异常。"
    return f"{_md_heading('structural_anomalies')}\n\n{body}\n"


_REVERSE_ANALYSIS_TYPES: frozenset[str] = frozenset(
    {
        "analysis_coverage",
        "callgraph_edge",
        "decompile_error",
        "decompile_input",
        "decompile_priority",
        "decompile_timeout",
        "decompiled_function",
        "function_decompiled",
        "function_tag",
        "managed_config_candidate",
        "managed_metadata",
        "managed_resource",
    }
)
"""Indicator types that are meaningful in the reverse-analysis section."""

_REVERSE_ANALYSIS_TERMS: tuple[str, ...] = (
    "decompil",
    "disassembl",
    "ghidra",
    "reverse",
    "entry",
    "stub",
    "shellcode",
    "反编译",
    "逆向",
    "入口",
    "存根",
    "壳代码",
)
"""Terms used to identify reverse-engineering inferences without direct refs."""

_REVERSE_SECTION_MAX_ITEMS: int = 8
"""Maximum rows shown per subsection to keep Markdown reports bounded."""

_REVERSE_INLINE_MAX_CHARS: int = 240
"""Maximum length of one inline reverse-analysis value."""


def _md_inline_value(value: Any) -> str:
    """Convert structured Indicator data into a bounded Markdown inline value."""
    if isinstance(value, dict):
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            text = str(value)
    elif isinstance(value, (list, tuple, set)):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > _REVERSE_INLINE_MAX_CHARS:
        return f"{text[: _REVERSE_INLINE_MAX_CHARS - 3]}..."
    return text


def _first_data_value(ind: Indicator, keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty Indicator data value for ``keys``."""
    for key in keys:
        value = ind.data.get(key)
        if value not in (None, "", [], {}):
            return _md_inline_value(value)
    return None


def _reverse_fact_label(ind: Indicator) -> str:
    """Return a compact label for a disassembly Indicator."""
    label = _first_data_value(
        ind,
        (
            "name",
            "function",
            "method",
            "symbol",
            "address",
            "caller_name",
            "caller",
            "dimension",
        ),
    )
    return label or ind.indicator_type


def _reverse_fact_summary(ind: Indicator) -> str:
    """Return the most analyst-useful summary for a disassembly Indicator."""
    data = ind.data
    if ind.indicator_type == "callgraph_edge":
        caller = data.get("caller_name") or data.get("caller") or "unknown"
        callee = data.get("callee_name") or data.get("callee") or "unknown"
        return f"{_md_inline_value(caller)} -> {_md_inline_value(callee)}"
    summary = _first_data_value(
        ind,
        (
            "pseudo_code_summary",
            "summary",
            "analysis",
            "rationale",
            "note",
            "reason",
            "status",
            "capability_tags",
            "capability",
            "description",
            "output_path",
        ),
    )
    if summary:
        return summary
    visible = {
        key: value
        for key, value in data.items()
        if key
        in {
            "address",
            "budget",
            "format",
            "input_path",
            "lines_read",
            "priority_rank",
            "source",
            "truncated",
        }
    }
    return _md_inline_value(visible) if visible else ind.indicator_type


def _reverse_fact_line(ind: Indicator) -> str:
    """Render one disassembly Indicator as a Markdown bullet."""
    label = _reverse_fact_label(ind)
    summary = _reverse_fact_summary(ind)
    return f"- `{ind.indicator_type}`：{label} — {summary}{_md_footnote_refs([ind.id])}"


def _text_contains_reverse_term(text: str) -> bool:
    """Return True when text appears to describe reverse-engineering evidence."""
    lowered = text.lower()
    return any(term in lowered for term in _REVERSE_ANALYSIS_TERMS)


def _is_reverse_inference(ind: Indicator, disassembly_ids: set[str]) -> bool:
    """Return True when an LLM inference belongs in reverse-analysis context."""
    if set(ind.evidence_refs) & disassembly_ids:
        return True
    if _text_contains_reverse_term(ind.indicator_type):
        return True
    try:
        data_text = json.dumps(ind.data, ensure_ascii=False, default=str)
    except TypeError:
        data_text = str(ind.data)
    return _text_contains_reverse_term(data_text)


def _reverse_inference_line(ind: Indicator) -> str:
    """Render one reverse-related LLM inference as a Markdown bullet."""
    summary = _first_data_value(
        ind,
        (
            "summary",
            "analysis",
            "finding",
            "conclusion",
            "rationale",
            "note",
            "description",
            "behavior",
            "details",
        ),
    )
    if summary is None:
        summary = _md_inline_value(ind.data)
    refs = [ind.id, *ind.evidence_refs]
    confidence = f"（{ind.confidence.value}）" if ind.confidence else ""
    return f"- `{ind.indicator_type}`{confidence}：{summary}{_md_footnote_refs(refs)}"


def _section_reverse_analysis(report: ReportV1) -> str:
    """Render Ghidra / decompiler facts plus related LLM reverse analysis."""
    snap = report.evidence_chain
    disassembly = [
        ind
        for ind in snap.disassembly
        if ind.indicator_type in _REVERSE_ANALYSIS_TYPES
        or _text_contains_reverse_term(ind.indicator_type)
    ]
    disassembly_ids = {ind.id for ind in snap.disassembly}
    inferences = [
        ind
        for ind in snap.llm_inferences
        if _is_reverse_inference(ind, disassembly_ids)
    ]

    lines = [_md_heading("reverse_analysis"), ""]
    if not disassembly:
        status = report.analysis_coverage.dimensions.get("decompilation")
        if status is CoverageStatus.COMPLETED:
            lines.append(
                "- 反编译覆盖度标记为完成，但未发现可渲染的 `disassembly` fact。"
            )
        else:
            lines.append("- 未采集到可渲染的反编译或逆向分析事实。")
            lines.append(
                f"- 建议补充：{MARKDOWN_DEGRADATION_SUGGESTIONS['decompilation']}"
            )
    else:
        lines.append("### 反编译事实")
        lines.append("")
        for ind in disassembly[:_REVERSE_SECTION_MAX_ITEMS]:
            lines.append(_reverse_fact_line(ind))
        if len(disassembly) > _REVERSE_SECTION_MAX_ITEMS:
            hidden = len(disassembly) - _REVERSE_SECTION_MAX_ITEMS
            lines.append(f"- 另有 {hidden} 条反编译事实未展开。")
    if inferences:
        lines.append("")
        lines.append("### 逆向结论")
        lines.append("")
        for ind in inferences[:_REVERSE_SECTION_MAX_ITEMS]:
            lines.append(_reverse_inference_line(ind))
        if len(inferences) > _REVERSE_SECTION_MAX_ITEMS:
            hidden = len(inferences) - _REVERSE_SECTION_MAX_ITEMS
            lines.append(f"- 另有 {hidden} 条逆向结论未展开。")
    lines.append("")
    return "\n".join(lines)


_DOC_PARTIAL_WARN: str = "> ⚠️ 父文档分析因预算约束被降级，见子样本完整报告"
"""FR-15 AC-7: Markdown blockquote warning emitted when doc_analysis_partial=True."""


def _delivery_parent_child_links(report: ReportV1) -> list[Indicator]:
    """Return recorded document parent -> child links from the evidence chain."""
    return [
        ind
        for ind in report.evidence_chain.delivery_chain_doc
        if ind.indicator_type == "parent_child_link"
    ]


def _delivery_link_line(ind: Indicator) -> str:
    """Render one ``parent_child_link`` Indicator as a concise Markdown bullet."""
    data = ind.data
    parent = data.get("parent_analysis_id") or data.get("parent_sha256") or "parent"
    child = data.get("child_sample_id") or data.get("child_sha256") or "child"
    verdict = data.get("child_verdict", "unknown")
    child_sha = data.get("child_sha256")
    child_format = data.get("child_suggested_format")
    details = [f"子样本判定：`{verdict}`"]
    if child_sha:
        details.append(f"SHA-256：`{child_sha}`")
    if child_format:
        details.append(f"格式：{child_format}")
    return (
        f"- `{parent}` → `{child}`（{'; '.join(details)}）{_md_footnote_refs([ind.id])}"
    )


def _section_delivery_chain(report: ReportV1) -> str | None:
    """Render the 投递链 section (FR-15 AC-4).

    Returns ``None`` when ``delivery_chain_doc`` is absent so that
    ``render_markdown`` omits the section for non-document samples
    (backward-compatible with e2e01 fixtures).
    """
    if report.delivery_chain_doc is None:
        return None
    lines = [_md_heading("delivery_chain"), ""]
    if report.doc_analysis_partial:
        lines.append(_DOC_PARTIAL_WARN)
        lines.append("")
    parent_child_links = _delivery_parent_child_links(report)
    if parent_child_links:
        lines.append("### 父子样本链路")
        lines.append("")
        for ind in parent_child_links[:_DOC_BUCKET_MAX_ITEMS]:
            lines.append(_delivery_link_line(ind))
        if len(parent_child_links) > _DOC_BUCKET_MAX_ITEMS:
            hidden = len(parent_child_links) - _DOC_BUCKET_MAX_ITEMS
            lines.append(f"- 另有 {hidden} 条父子链接未展开。")
        lines.append("")
    for key, val in report.delivery_chain_doc.items():
        lines.append(f"- **{key}**：{val}")
    if not report.delivery_chain_doc:
        lines.append("- 无投递链层级记录。")
    lines.append("")
    return "\n".join(lines)


def _section_macro_and_embedded_script(report: ReportV1) -> str | None:
    """Render the 宏与嵌入脚本分析 section (FR-15 AC-4).

    Returns ``None`` when both ``macro_analysis`` and ``document_analysis``
    are absent.
    """
    if report.macro_analysis is None and report.document_analysis is None:
        return None
    lines = [_md_heading("macro_and_embedded_script"), ""]
    if report.doc_analysis_partial:
        lines.append(_DOC_PARTIAL_WARN)
        lines.append("")
    if report.document_analysis:
        lines.append("### 文档结构分析")
        lines.append("")
        for key, val in report.document_analysis.items():
            lines.append(f"- **{key}**：{val}")
        lines.append("")
    if report.macro_analysis:
        lines.append("### 宏分析")
        lines.append("")
        for key, val in report.macro_analysis.items():
            lines.append(f"- **{key}**：{val}")
        lines.append("")
    return "\n".join(lines)


def _section_embedded_payloads_list(report: ReportV1) -> str | None:
    """Render the 嵌入载荷清单 section (FR-15 AC-4/5/6).

    - Returns ``None`` when ``embedded_payloads`` is absent (backward compat).
    - Annotates each entry that has a ``report_ref`` with a Markdown link
      (FR-15 AC-5).
    - When ``document_role == infection_source`` entries without a
      ``report_ref`` are explicitly marked as missing (FR-15 AC-6).
    """
    if report.embedded_payloads is None:
        return None
    is_infection_source = report.document_role is DocumentRole.INFECTION_SOURCE
    lines = [_md_heading("embedded_payloads_list"), ""]
    if report.doc_analysis_partial:
        lines.append(_DOC_PARTIAL_WARN)
        lines.append("")
    for idx, payload in enumerate(report.embedded_payloads, 1):
        sha = payload.get("sha256", "未知")
        payload_type = payload.get("type") or payload.get("format", "未知")
        report_ref = payload.get("report_ref")
        lines.append(f"#### 载荷 {idx}")
        lines.append(f"- SHA-256：`{sha}`")
        lines.append(f"- 类型：{payload_type}")
        source = payload.get("source")
        source_region = payload.get("source_region")
        offset = payload.get("offset")
        decoder = payload.get("decoder")
        if source or source_region or offset is not None:
            parts = []
            if source:
                parts.append(f"source={source}")
            if source_region:
                parts.append(f"region={source_region}")
            if offset is not None:
                parts.append(f"offset={offset}")
            lines.append(f"- 来源：`{'; '.join(parts)}`")
        if decoder and decoder != "none":
            lines.append(f"- 静态解码：`{decoder}`")
        recursion_status = payload.get("child_recursion_status")
        child_verdict = payload.get("child_verdict")
        if recursion_status or child_verdict:
            lines.append(
                "- 子样本分析："
                f"{recursion_status or 'unknown'}"
                f" / verdict={child_verdict or 'unknown'}"
            )
        if report_ref:
            lines.append(f"- 独立报告：[{report_ref}]({report_ref})")
        elif is_infection_source:
            lines.append("- 独立报告：（未生成）")
        lines.append("")
    if not report.embedded_payloads:
        lines.append("- 无嵌入载荷记录。")
        lines.append("")
    return "\n".join(lines)


def _section_escalation(report: ReportV1) -> str:
    from tools.decision_gate import markdown_disclaimer

    level = report.escalation_recommendation.level.value
    reasons = report.escalation_recommendation.reasons
    reasons_block = (
        "\n".join(f"- {r}" for r in reasons) if reasons else "- 无升级建议。"
    )
    return (
        f"{_md_heading('escalation')}\n\n"
        f"{markdown_disclaimer()}\n\n"
        f"- 推荐动作：**{level}**\n\n"
        f"{reasons_block}\n"
    )


def _section_coverage(report: ReportV1) -> str:
    rows = [f"{_md_heading('coverage')}", "", "| 维度 | 状态 |", "|------|------|"]
    for dim, status in report.analysis_coverage.dimensions.items():
        rows.append(f"| {dim} | {status.value} |")
    if report.analysis_coverage.gaps:
        rows.append("")
        rows.append("### 缺口与建议")
        for gap in report.analysis_coverage.gaps:
            suggestion_key = (
                "decompilation"
                if gap == MARKDOWN_DEGRADED_DISASSEMBLY
                else "behavior_chain"
                if gap == MARKDOWN_DEGRADED_BEHAVIOR
                else None
            )
            if suggestion_key:
                rows.append(
                    f"- {gap} — 建议补充：{MARKDOWN_DEGRADATION_SUGGESTIONS[suggestion_key]}"
                )
            else:
                rows.append(f"- {gap}")
    rows.append("")
    return "\n".join(rows)


def _footnote_definitions(report: ReportV1) -> str:
    """Emit ``[^id]: ...`` definitions for every Indicator footnote used."""
    snap = report.evidence_chain
    lines: list[str] = []
    for field_name in snap.__class__.model_fields:
        for ind in getattr(snap, field_name):
            lines.append(
                f"[^{ind.id}]: {ind.indicator_type} · "
                f"{ind.severity.value} · {field_name} 桶"
            )
    return "\n".join(lines) + ("\n" if lines else "")


def render_markdown(report: ReportV1, *, redact_host_paths: bool = True) -> str:
    """Render ``report`` as a Chinese, analyst-friendly Markdown document.

    Structure follows :data:`MARKDOWN_SECTIONS` ordering (9 mandatory
    sections per FR-15 AC-2).  Every key conclusion carries a ``[^id]``
    footnote (AC-5); the behavior chain renders as both a node list and
    a ``mermaid`` block (AC-7); FR-07 / FR-17 degradations surface the
    fixed phrases mandated by AC-9.

    Args:
        report: Fully populated :class:`ReportV1`.
        redact_host_paths: When ``True`` (default), uses the same evidence-chain
            redaction as :func:`render_json` so inlined indicator excerpts do not
            leak host paths.

    Returns:
        Markdown string.  Callers are responsible for persisting it.
    """
    if redact_host_paths:
        report = redact_report_for_export(report)
    sections: list[str] = [
        f"# {MARKDOWN_REPORT_TITLE}",
        "",
        _section_summary(report),
        _section_fingerprints(report),
        _section_verdict(report),
        _section_risk_score(report),
        _section_behavior_chain(report),
        _section_iocs(report),
        _section_structural_anomalies(report),
        _section_reverse_analysis(report),
    ]
    # v1.1.0 optional document sections (FR-15 AC-4) — omitted for non-document samples
    for optional_sec in (
        _section_delivery_chain(report),
        _section_macro_and_embedded_script(report),
        _section_embedded_payloads_list(report),
    ):
        if optional_sec is not None:
            sections.append(optional_sec)
    sections.extend(
        [
            _section_escalation(report),
            _section_coverage(report),
            _footnote_definitions(report),
        ]
    )
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Tmp-dir cleanup (FR-15 AC-10, IR-03)
# ---------------------------------------------------------------------------


def _cleanup_analysis_tmp(tmp_root: Path | None, analysis_id: str) -> bool:
    """Remove the host-side ``deepagent-analyze-<analysis_id>`` sub-directory.

    Args:
        tmp_root: Host tmpdir root configured by the caller.  When
            ``None`` the cleanup is a no-op (caller opted out).
        analysis_id: Current analysis ID (ADR-10 tmpdir naming).

    Returns:
        ``True`` if a directory was removed, ``False`` otherwise.
    """
    if tmp_root is None:
        return False
    target = Path(tmp_root) / f"deepagent-analyze-{analysis_id}"
    if not target.exists():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return not target.exists()


# ---------------------------------------------------------------------------
# LangChain tool wrapper (AC-8 / AC-10 side effects)
# ---------------------------------------------------------------------------


class ReportGenInput(BaseModel):
    """Input schema for :class:`ReportGenTool`.

    Args:
        analysis_id: ULID of the analysis run (propagated into FileMeta
            and used to resolve the tmpdir for cleanup).
        output_dir: Directory where the two report files are written.
            Created if absent.
        tmp_root: Optional host tmpdir root; when supplied, the
            ``deepagent-analyze-<analysis_id>`` sub-directory is removed
            after generation (FR-15 AC-10 / IR-03).
    """

    analysis_id: str
    output_dir: str
    tmp_root: str | None = None

    model_config = ConfigDict(extra="forbid")


class ReportGenResult(BaseModel):
    """Return payload for :class:`ReportGenTool`."""

    json_path: str
    md_path: str
    sha256: str
    schema_version: str
    markdown_content: str = Field(
        default="",
        description="Full Markdown report body for user-visible appendices.",
    )
    cleanup_performed: bool = False


class ReportGenTool(BaseTool):
    """LangChain tool that generates the FR-15 dual-format report.

    Args:
        store: Shared per-analysis
            :class:`~evidence_chain.store.EvidenceChainStore`.

    The tool is synchronous: :func:`build_report_v1` is pure and the
    only side effects (two file writes + one ``rmtree``) are synchronous.
    """

    name: str = "report_gen"
    description: str = (
        "Generate the FR-15 dual-format analyst report from the current "
        "evidence chain. Produces two files under 'output_dir': "
        "'<sha256>.report.json' (frozen report schema, NFR-12) and "
        "'<sha256>.report.md' (Chinese analyst-facing narrative with 9 "
        "mandatory sections and mermaid behavior-chain diagram). Every "
        "key conclusion carries Indicator footnotes (FR-15 AC-5). Returns "
        "'markdown_content' with the full Markdown body so the final "
        "user-visible answer can append the detailed report without "
        "reading host-only paths. When "
        "'tmp_root' is supplied, removes the host-side "
        "'deepagent-analyze-<analysis_id>/' sub-directory after the "
        "report is written (FR-15 AC-10 / IR-03)."
    )
    args_schema: type[BaseModel] = ReportGenInput
    store: EvidenceChainStore = Field(...)

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        inp = ReportGenInput(**kwargs)
        snapshot = self.store.snapshot()
        try:
            report = build_report_v1(snapshot, analysis_id=inp.analysis_id)
        except ValueError as exc:
            return {
                "ok": False,
                "error_code": "TOOL_SCHEMA_INVALID",
                "reason": "report_prerequisite_missing",
                "message": str(exc),
                "details": {
                    "reason": "report_prerequisite_missing",
                    "analysis_id": inp.analysis_id,
                },
            }

        output_dir = Path(inp.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        sha256 = report.fingerprints.sha256
        json_path = output_dir / f"{sha256}.report.json"
        md_path = output_dir / f"{sha256}.report.md"
        markdown_content = render_markdown(report)

        json_path.write_text(render_json(report), encoding="utf-8")
        md_path.write_text(markdown_content, encoding="utf-8")

        tmp_root = Path(inp.tmp_root) if inp.tmp_root is not None else None
        cleanup_performed = _cleanup_analysis_tmp(tmp_root, inp.analysis_id)

        result = ReportGenResult(
            json_path=str(json_path),
            md_path=str(md_path),
            sha256=sha256,
            schema_version=report.schema_version,
            markdown_content=markdown_content,
            cleanup_performed=cleanup_performed,
        )
        return result.model_dump()

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        return self._run(**kwargs)


__all__ = [
    "FR17_PHASE1_MISSING_GAP",
    "ReportGenInput",
    "ReportGenResult",
    "ReportGenTool",
    "build_report_v1",
    "redact_report_for_export",
    "render_json",
    "render_markdown",
]
