"""Report schema — top-level JSON report structure (FR-15, NFR-12).

`ReportV1` is the v1.1.0 schema for the JSON analysis report.  All
downstream consumers (CLI, Python API, integration tests) must import types
from this module.

Schema stability rules (NFR-12 SemVer):
- Adding new optional fields is allowed (minor / patch bump).
- Renaming, removing, or changing the type of existing fields requires a
  major version bump and full downstream regression.
- `schema_version` is validated against the SemVer pattern ``^\\d+\\.\\d+\\.\\d+$``.

FR-15 AC-1 top-level fields (v1.0.0):
    schema_version, file_meta, fingerprints, verdict, risk_score,
    threat_class, malware_family, evidence_chain, behavior_chain,
    escalation_recommendation, analysis_coverage.

FR-15 AC-3 additional fields (v1.1.0, all Optional):
    document_format, document_tier, document_role, doc_analysis_partial,
    unknown_downgrade_reason, document_analysis, macro_analysis,
    embedded_payloads, delivery_chain_doc.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field

from schema.document_enums import (
    DocumentFormat,
    DocumentRole,
    DocumentTier,
    UnknownDowngradeReason,
)
from schema.evidence_chain import EvidenceChainSnapshot

# ---------------------------------------------------------------------------
# Supporting enumerations
# ---------------------------------------------------------------------------


class VerdictLabel(StrEnum):
    """Final verdict for a binary sample (ADR-04)."""

    MALICIOUS = "MALICIOUS"
    SUSPICIOUS = "SUSPICIOUS"
    BENIGN = "BENIGN"
    UNKNOWN = "UNKNOWN"


class EscalationLevel(StrEnum):
    """Recommended escalation action after static analysis (FR-14)."""

    NONE = "NONE"
    SANDBOX = "SANDBOX"
    MANUAL_REVERSE = "MANUAL_REVERSE"


class CoverageStatus(StrEnum):
    """Execution status for an analysis dimension (FR-15 AC-6)."""

    COMPLETED = "COMPLETED"
    DEGRADED = "DEGRADED"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class FileMeta(BaseModel):
    """Sample identity and file-system metadata.

    Args:
        file_name: Original file name (may contain Unicode / special chars, IR-08).
        file_size: File size in bytes.
        file_type: Detected file type (e.g. ``"PE32"``, ``"ELF64"``).
        architecture: CPU architecture (e.g. ``"x86"``, ``"x86_64"``, ``"arm64"``).
        analysis_id: ULID of the analysis run that produced this report.
        mime_type: MIME type string when available.
        platform: Target OS platform (e.g. ``"Windows"``, ``"Linux"``, ``"macOS"``).
    """

    file_name: str
    file_size: int
    file_type: str
    architecture: str
    analysis_id: str
    mime_type: str | None = None
    platform: str | None = None


class Fingerprints(BaseModel):
    """Cryptographic and fuzzy hashes for sample identification.

    Args:
        sha256: SHA-256 hex digest (64 chars).
        md5: MD5 hex digest (32 chars).
        sha1: SHA-1 hex digest (40 chars).
        imphash: Import-table hash (PE only).
        ssdeep: Context-triggered piecewise hash for fuzzy matching.
        tlsh: Trend Micro Locality Sensitive Hash.
        rich_header_hash: Rich header hash (PE only).
    """

    sha256: str
    md5: str
    sha1: str
    imphash: str | None = None
    ssdeep: str | None = None
    tlsh: str | None = None
    rich_header_hash: str | None = None


class Verdict(BaseModel):
    """Verdict produced by the scoring rule engine (ADR-04).

    Args:
        label: Final verdict label (MALICIOUS / SUSPICIOUS / BENIGN / UNKNOWN).
        rule_score: Numeric risk score (0–100) from the rule engine.
        llm_label: LLM-suggested verdict (recorded as secondary evidence when
            it diverges from `label`; ADR-04).
        verdict_divergence: Human-readable note when rule and LLM verdicts
            diverge significantly.
    """

    label: VerdictLabel
    rule_score: float
    llm_label: VerdictLabel | None = None
    verdict_divergence: str | None = None


class RiskScore(BaseModel):
    """Quantitative risk score with provenance (FR-13 AC-1).

    Args:
        score: Integer risk score in range 0–100.
        rule_version: Version string of the scoring rule set used.
        contributing_indicator_ids: Indicator IDs that contributed to the score.
    """

    score: Annotated[int, Field(ge=0, le=100)]
    rule_version: str
    contributing_indicator_ids: list[str] = Field(default_factory=list)


class ThreatClass(BaseModel):
    """Threat-type classification (FR-13 AC-3).

    Args:
        classes: List of threat-type labels inferred by the LLM
            (e.g. ``["Dropper", "InfoStealer"]``).
        confidence: Confidence level for the primary classification.
    """

    classes: list[str]
    confidence: str | None = None


class MalwareFamily(BaseModel):
    """Malware family attribution (FR-13 AC-4).

    Args:
        name: Family name or ``"Unknown Family"`` when confidence is insufficient.
        confidence: Confidence level for the attribution.
        evidence_refs: Indicator IDs supporting the attribution.
    """

    name: str
    confidence: str
    evidence_refs: list[str] = Field(default_factory=list)


class BehaviorNode(BaseModel):
    """A node in the behavior-chain graph (FR-15 AC-7).

    Args:
        node_id: Unique node identifier within this report.
        label: Short descriptive label (e.g. ``"LoadLibrary"``).
        indicator_id: Backing Indicator ID in the evidence chain.
    """

    node_id: str
    label: str
    indicator_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BehaviorEdge(BaseModel):
    """A directed edge in the behavior-chain graph (FR-15 AC-7).

    Args:
        source: `node_id` of the source node.
        target: `node_id` of the target node.
        label: Optional edge label (e.g. ``"calls"``, ``"writes"``).
    """

    source: str
    target: str
    label: str | None = None


class BehaviorChain(BaseModel):
    """Structured behavior-chain graph (FR-15 AC-7).

    JSON representation uses node/edge arrays; Markdown rendering (Mermaid)
    is deferred to C13.

    Args:
        nodes: Ordered list of behavior nodes.
        edges: Directed edges between nodes.
    """

    nodes: list[BehaviorNode] = Field(default_factory=list)
    edges: list[BehaviorEdge] = Field(default_factory=list)


class EscalationRecommendation(BaseModel):
    """Structured escalation recommendation from DecisionGateTool (FR-14).

    Args:
        level: Recommended action (NONE / SANDBOX / MANUAL_REVERSE).
        reasons: Human-readable justification strings.
        evidence_gaps: Descriptions of missing evidence that prompted
            escalation.
    """

    level: EscalationLevel
    reasons: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class AnalysisCoverage(BaseModel):
    """Per-dimension analysis coverage summary (FR-15 AC-6).

    Args:
        dimensions: Mapping from dimension name to its execution status.
            Standard keys: ``structure``, ``entropy``, ``strings``,
            ``decompilation``, ``behavior_chain``, ``llm_inferences``.
        gaps: Free-text descriptions of evidence gaps or skipped steps.
    """

    dimensions: dict[str, CoverageStatus]
    gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level report model
# ---------------------------------------------------------------------------

_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


class ReportV1(BaseModel):
    """Top-level JSON report produced by ReportGenTool (FR-15, NFR-12).

    Schema version bumped to ``1.1.0`` (C1 / FR-15 AC-2 / NFR-12).  All
    v1.1.0 additions are Optional with ``None`` / ``False`` defaults so that
    e2e01 consumers loading a v1.1.0 report ignore unknown fields without
    error.

    Args:
        schema_version: SemVer string (default ``"1.1.0"``).  Must match
            pattern ``^\\d+\\.\\d+\\.\\d+$``.
        file_meta: Sample identity and file-system metadata.
        fingerprints: Cryptographic and fuzzy hashes.
        verdict: Rule-engine verdict with optional LLM secondary verdict.
        risk_score: Quantitative risk score (0–100) with rule provenance.
        threat_class: Threat-type classification (LLM-inferred).
        malware_family: Malware family attribution.
        evidence_chain: Complete evidence-chain snapshot at report time.
        behavior_chain: Structured behavior-chain graph (nodes + edges).
        escalation_recommendation: Recommended escalation action.
        analysis_coverage: Per-dimension execution status and evidence gaps.
        document_format: Detected document format (v1.1.0, FR-15 AC-3).
        document_tier: Analysis-complexity tier (v1.1.0, FR-15 AC-3).
        document_role: Threat delivery role (v1.1.0, FR-13 AC-4 / FR-15 AC-3).
        doc_analysis_partial: True when document analysis was budget-degraded
            (v1.1.0, FR-15 AC-3/7).
        unknown_downgrade_reason: Enumerated reason for UNKNOWN verdict
            downgrade (v1.1.0, FR-13 AC-6 / FR-15 AC-3).
        document_analysis: Summary dict from the ``document_analysis`` evidence
            bucket (v1.1.0, FR-15 AC-3).
        macro_analysis: Summary dict from the ``macro_analysis`` evidence
            bucket (v1.1.0, FR-15 AC-3).
        embedded_payloads: List of embedded payload summary dicts from the
            ``embedded_payloads`` evidence bucket (v1.1.0, FR-15 AC-3).
        delivery_chain_doc: Delivery-chain hierarchy summary dict from the
            ``delivery_chain_doc`` evidence bucket (v1.1.0, FR-15 AC-3).
    """

    schema_version: Annotated[
        str,
        Field(
            default="1.1.0",
            pattern=_SEMVER_PATTERN,
            description="SemVer schema version; v1.1.0 adds document fields (NFR-12).",
        ),
    ] = "1.1.0"

    file_meta: FileMeta
    fingerprints: Fingerprints
    verdict: Verdict
    risk_score: RiskScore
    threat_class: ThreatClass
    malware_family: MalwareFamily
    evidence_chain: EvidenceChainSnapshot
    behavior_chain: BehaviorChain
    escalation_recommendation: EscalationRecommendation
    analysis_coverage: AnalysisCoverage

    # v1.1.0 document fields — all Optional for backward compatibility (FR-09 AC-5 / NFR-12)
    document_format: DocumentFormat | None = None
    document_tier: DocumentTier | None = None
    document_role: DocumentRole | None = None
    doc_analysis_partial: bool = False
    unknown_downgrade_reason: UnknownDowngradeReason | None = None
    document_analysis: dict[str, Any] | None = None
    macro_analysis: dict[str, Any] | None = None
    embedded_payloads: list[dict[str, Any]] | None = None
    delivery_chain_doc: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Markdown template constants (C13 / FR-15 AC-2, AC-9)
# ---------------------------------------------------------------------------
#
# These constants are additive ONLY; they do not alter the frozen v1.0.0 JSON
# schema above.  They are consumed by
# :mod:`tools.report_gen` to render the analyst-facing
# Chinese Markdown report.  JSON keys remain English for downstream schema
# stability (FR-15 AC-2 red-line).

MARKDOWN_REPORT_TITLE: str = "二进制分析报告"
"""Top-level H1 title of the Markdown report."""

MARKDOWN_SECTIONS: dict[str, str] = {
    "summary": "摘要",
    "fingerprints": "样本指纹",
    "verdict": "判定结论",
    "risk_score": "风险评分",
    "behavior_chain": "行为链图谱",
    "iocs": "IOC 列表",
    "structural_anomalies": "结构异常",
    "reverse_analysis": "反编译与逆向分析",
    # v1.1.0 document sections (FR-15 AC-4) — optional, rendered only when data exists
    "delivery_chain": "投递链",
    "macro_and_embedded_script": "宏与嵌入脚本分析",
    "embedded_payloads_list": "嵌入载荷清单",
    "escalation": "升级建议",
    "coverage": "分析覆盖度",
}
"""Ordered dict of Markdown section headings for the analyst-facing report.

The 10 base sections (FR-15 AC-2) are always rendered.  The 3 v1.1.0 document
sections (``delivery_chain`` / ``macro_and_embedded_script`` /
``embedded_payloads_list``, FR-15 AC-4) are optional — rendered only when the
corresponding evidence-chain buckets contain data.  Insertion order defines the
document structure produced by
:func:`binary_analysis.tools.report_gen.render_markdown`.
"""

MARKDOWN_DEGRADED_DISASSEMBLY: str = "反编译分析不可用"
"""Fixed Chinese phrase surfaced when ``decompilation`` coverage ≠ COMPLETED (FR-15 AC-9)."""

MARKDOWN_DEGRADED_BEHAVIOR: str = "行为链重建不可用"
"""Fixed Chinese phrase surfaced when ``behavior_chain`` coverage ≠ COMPLETED (FR-15 AC-9)."""

MARKDOWN_DEGRADATION_SUGGESTIONS: dict[str, str] = {
    "decompilation": "建议在具备 Ghidra / IDA Pro 环境下对关键函数进行人工反编译补齐。",
    "behavior_chain": "建议结合动态沙箱或人工逆向手工梳理核心恶意路径。",
}
"""Fixed Chinese remediation suggestions surfaced alongside AC-9 degradation notices."""
