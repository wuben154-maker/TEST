"""Unit tests for :mod:`tools.report_gen` (C11/C13, FR-15 AC-1/2/3/4/5/6/7/8/9/10).

Coverage map (pre-C11):

- test_json_report_has_all_top_level_fields          -> AC-1
- test_markdown_has_mandatory_chinese_sections       -> AC-2
- test_json_and_markdown_conclusions_equivalent      -> AC-3
- test_key_conclusions_carry_evidence_refs           -> AC-5
- test_analysis_coverage_summary_present             -> AC-6
- test_behavior_chain_structural_expression          -> AC-7
- test_output_file_naming_sha256                     -> AC-8
- test_degraded_fixture_surfaces_fixed_phrases       -> AC-9
- test_generate_cleans_tmp_dir                       -> AC-10

C11 additions (FR-15 AC-3/4/5/6/7):

- test_doc_fields_absent_on_minimal_fixture          -> AC-3 backward compat
- test_doc_sections_present_with_doc_fixture         -> AC-4
- test_doc_partial_warning_block_in_sections         -> AC-7
- test_infection_source_embedded_payload_link        -> AC-5/6
- test_schema_version_1_1_0_and_json_doc_fields      -> AC-2/3

Three local evidence-chain fixtures (built atop the frozen
``tests/fixtures/evidence_chains`` helpers) exercise the three FR-15 paths:

- ``_build_normal_chain`` → full evidence chain (MALICIOUS + disassembly
  + behavior_chain), the "正常" happy path
- ``_build_degraded_chain`` → FR-07 / FR-17 degraded (no disassembly, no
  behavior_chain), the "降级" path
- ``_build_exception_chain`` → LOW-confidence chain → UNKNOWN verdict,
  the "异常" / low-signal path
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Indicator, Severity
from schema.report import (
    MARKDOWN_DEGRADED_BEHAVIOR,
    MARKDOWN_DEGRADED_DISASSEMBLY,
    MARKDOWN_REPORT_TITLE,
    MARKDOWN_SECTIONS,
    CoverageStatus,
    ReportV1,
    VerdictLabel,
)
from tests.fixtures.evidence_chains import low_confidence, malicious
from tests.fixtures.evidence_chains._helpers import add_fact, add_inference
from tools.decision_gate import DecisionGateTool
from tools.report_gen import (
    FR17_PHASE1_MISSING_GAP,
    ReportGenResult,
    ReportGenTool,
    build_report_v1,
    render_json,
    render_markdown,
)
from tools.scoring import ScoringTool

_TEST_SHA256 = "b" * 64
_TEST_MD5 = "a" * 32
_TEST_SHA1 = "c" * 40


# ---------------------------------------------------------------------------
# Local fixture builders (three FR-15 paths)
# ---------------------------------------------------------------------------


def _inject_file_meta_fr01(store: EvidenceChainStore) -> str:
    """Inject an FR-01-shaped ``file_meta`` Indicator carrying fingerprints.

    The fixtures from ``tests/fixtures/evidence_chains`` seed a minimal
    ``fixture_anchor`` file_meta record; ReportGenTool needs the real
    FR-01 payload shape (``fingerprints``, ``format``, ``arch``, ...).
    """
    ind = Indicator(
        source_fr="FR-01",
        indicator_type="file_meta",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        kind="fact",
        data={
            "format": "PE32+",
            "arch": "x86_64",
            "routing": "windows",
            "fingerprints": {
                "md5": _TEST_MD5,
                "sha1": _TEST_SHA1,
                "sha256": _TEST_SHA256,
                "imphash": "d" * 32,
                "ssdeep": "96:abcd",
                "tlsh": "T" + "e" * 71,
            },
            "size_bytes": 123456,
            "absolute_path": "C:\\samples\\evil.exe",
            "mtime": 1713600000.0,
            "sandbox_path": "/workspace/analysis-x/sample.bin",
            "coverage_notes": [],
        },
    )
    store.append(Bucket.file_meta, ind)
    return ind.id


def _inject_disassembly_and_chain(store: EvidenceChainStore) -> None:
    """Seed disassembly + richer behavior_chain Indicators for the normal path."""
    add_fact(
        store,
        Bucket.disassembly,
        indicator_type="function_decompiled",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        data={"function": "sub_401000", "pseudo_code_summary": "WinMain stub"},
    )
    add_fact(
        store,
        Bucket.behavior_chain,
        indicator_type="behavior_segment",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"segment": "dropper -> persistence"},
    )


def _build_normal_chain(analysis_id: str = "report-normal") -> EvidenceChainStore:
    """Return a fully populated evidence chain (FR-15 happy path)."""
    store = malicious.build(analysis_id=analysis_id)
    _inject_file_meta_fr01(store)
    _inject_disassembly_and_chain(store)
    ScoringTool(store=store).invoke({"analysis_id": analysis_id})
    DecisionGateTool(store=store).invoke({"analysis_id": analysis_id})
    return store


def _build_degraded_chain(analysis_id: str = "report-degraded") -> EvidenceChainStore:
    """Return a chain where FR-07 / FR-17 are degraded (empty disassembly + chain)."""
    store = malicious.build(analysis_id=analysis_id)
    _inject_file_meta_fr01(store)
    snap = store.snapshot()
    assert not snap.disassembly, "fixture precondition: no disassembly"
    ScoringTool(store=store).invoke({"analysis_id": analysis_id})
    DecisionGateTool(store=store).invoke({"analysis_id": analysis_id})
    # Drop behavior_chain by reconstructing a pruned chain: the malicious
    # fixture seeds behavior_chain to cover R-BEHAVIOR-MAL-CHAIN.  For the
    # degraded path we want both disassembly AND behavior_chain empty, so
    # we build from scratch instead of mutating (append-only contract).
    del store
    bare = low_confidence.build(analysis_id=analysis_id)
    _inject_file_meta_fr01(bare)
    ScoringTool(store=bare).invoke({"analysis_id": analysis_id})
    DecisionGateTool(store=bare).invoke({"analysis_id": analysis_id})
    return bare


def _build_exception_chain(
    analysis_id: str = "report-exception",
) -> EvidenceChainStore:
    """Return a LOW-confidence chain → UNKNOWN verdict (异常 / low-signal path)."""
    store = low_confidence.build(analysis_id=analysis_id)
    _inject_file_meta_fr01(store)
    ScoringTool(store=store).invoke({"analysis_id": analysis_id})
    DecisionGateTool(store=store).invoke({"analysis_id": analysis_id})
    return store


def _build_report_base_chain(analysis_id: str = "report-graph") -> EvidenceChainStore:
    """Return a minimal chain that can be converted into a report."""
    store = EvidenceChainStore(analysis_id=analysis_id)
    _inject_file_meta_fr01(store)
    return store


# ---------------------------------------------------------------------------
# AC-1 — JSON report carries every frozen v1.0.0 top-level field
# ---------------------------------------------------------------------------


def test_json_report_has_all_top_level_fields():
    store = _build_normal_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    payload = json.loads(render_json(report))

    required = {
        "schema_version",
        "file_meta",
        "fingerprints",
        "verdict",
        "risk_score",
        "threat_class",
        "malware_family",
        "evidence_chain",
        "behavior_chain",
        "escalation_recommendation",
        "analysis_coverage",
    }
    assert required.issubset(payload.keys()), (
        f"missing top-level fields: {required - set(payload.keys())}"
    )
    assert payload["schema_version"] == "1.1.0"
    assert payload["fingerprints"]["sha256"] == _TEST_SHA256
    assert payload["file_meta"]["analysis_id"] == "report-normal"


def test_render_json_redacts_host_absolute_path_prefers_sandbox_path():
    """Exported JSON must not leak host layout; prefer logical sandbox path."""
    store = _build_normal_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    payload = json.loads(render_json(report))
    dumped = json.dumps(payload, ensure_ascii=False)
    assert r"C:\samples" not in dumped and "samples\\evil" not in dumped
    fm_fr01 = [
        i
        for i in payload["evidence_chain"]["file_meta"]
        if isinstance(i.get("data"), dict)
        and i["data"].get("sandbox_path", "").startswith("/workspace/")
    ]
    assert fm_fr01, "expected FR-01 file_meta with sandbox_path"
    for ind in fm_fr01:
        assert ind["data"]["absolute_path"] == ind["data"]["sandbox_path"]


def test_render_json_redacts_host_path_to_basename_without_sandbox_path():
    store = _build_normal_chain()
    leak = Indicator(
        source_fr="FR-test",
        indicator_type="file_meta",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        kind="fact",
        data={"absolute_path": r"D:\uploads\u_secret\p_secret\leak.bin"},
    )
    store.append(Bucket.file_meta, leak)
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    payload = json.loads(render_json(report))
    assert r"D:\uploads" not in json.dumps(payload)
    leak_out = next(
        i
        for i in payload["evidence_chain"]["file_meta"]
        if isinstance(i.get("data"), dict) and i["data"].get("absolute_path") == "leak.bin"
    )
    assert leak_out["indicator_type"] == "file_meta"

    raw = json.loads(render_json(report, redact_host_paths=False))
    raw_leak = next(
        i
        for i in raw["evidence_chain"]["file_meta"]
        if i.get("id") == leak.id
    )
    assert r"u_secret" in raw_leak["data"]["absolute_path"]


# ---------------------------------------------------------------------------
# AC-2 — Markdown contains all 10 mandatory Chinese section headings
# (The 3 v1.1.0 document sections are optional and tested separately in C11.)
# ---------------------------------------------------------------------------

_MANDATORY_SECTION_HEADINGS: frozenset[str] = frozenset(
    {
        "摘要",
        "样本指纹",
        "判定结论",
        "风险评分",
        "行为链图谱",
        "IOC 列表",
        "结构异常",
        "反编译与逆向分析",
        "升级建议",
        "分析覆盖度",
    }
)
"""The 10 base section headings that must appear in every Markdown report (FR-15 AC-2)."""


def test_markdown_has_mandatory_chinese_sections():
    store = _build_normal_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    md = render_markdown(report)

    assert MARKDOWN_REPORT_TITLE in md
    for heading in _MANDATORY_SECTION_HEADINGS:
        assert f"## {heading}" in md, f"missing mandatory Markdown section: {heading}"
    assert _MANDATORY_SECTION_HEADINGS.issubset(set(MARKDOWN_SECTIONS.values()))


def test_reverse_analysis_section_renders_disassembly_and_related_inferences():
    """FR-15 Markdown must surface FR-07 facts and linked reverse conclusions."""
    store = _build_normal_chain()
    decompiled_id = add_fact(
        store,
        Bucket.disassembly,
        indicator_type="decompiled_function",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        source_fr="FR-07",
        data={
            "name": "entry",
            "address": "0x42df99",
            "pseudo_code_summary": (
                "Entry stub assigns hard-coded constants to build next-stage "
                "shellcode in .text"
            ),
        },
    )
    add_fact(
        store,
        Bucket.disassembly,
        indicator_type="function_tag",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        source_fr="FR-07",
        data={
            "name": "entry",
            "address": "0x42df99",
            "capability_tags": ["loader_stub", "shellcode_builder"],
            "source": "ghidra",
        },
    )
    add_inference(
        store,
        Bucket.llm_inferences,
        indicator_type="custom_loader_behavior",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        evidence_refs=[decompiled_id],
        source_fr="FR-08",
        data={
            "summary": (
                "入口点存根通过硬编码常量构建下一阶段 shellcode，并在 .text "
                "段内跳转执行。"
            ),
        },
    )

    report = build_report_v1(store.snapshot(), analysis_id="report-reverse")
    md = render_markdown(report)

    assert "## 反编译与逆向分析" in md
    assert "### 反编译事实" in md
    assert "`decompiled_function`" in md
    assert "Entry stub assigns hard-coded constants" in md
    assert "loader_stub, shellcode_builder" in md
    assert "### 逆向结论" in md
    assert "`custom_loader_behavior`" in md
    assert "入口点存根通过硬编码常量构建下一阶段 shellcode" in md
    assert f"[^{decompiled_id}]" in md


# ---------------------------------------------------------------------------
# AC-3 — JSON and Markdown conclusions stay in sync
# ---------------------------------------------------------------------------


def test_json_and_markdown_conclusions_equivalent():
    store = _build_normal_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    payload = json.loads(render_json(report))
    md = render_markdown(report)

    verdict_label = payload["verdict"]["label"]
    score = payload["risk_score"]["score"]

    assert verdict_label in md, "Markdown must echo JSON verdict label"
    assert str(score) in md, "Markdown must echo JSON risk score"

    behavior_nodes = payload["behavior_chain"]["nodes"]
    for node in behavior_nodes:
        assert node["label"] in md, (
            f"behavior-chain node {node['label']!r} missing from Markdown"
        )


# ---------------------------------------------------------------------------
# AC-5 — every key conclusion cites Indicator IDs
# ---------------------------------------------------------------------------


def test_key_conclusions_carry_evidence_refs():
    store = _build_normal_chain()
    snap = store.snapshot()
    report = build_report_v1(snap, analysis_id="report-normal")

    all_ids = {
        ind.id
        for field_name in snap.__class__.model_fields
        for ind in getattr(snap, field_name)
    }

    assert report.risk_score.contributing_indicator_ids
    for ref in report.risk_score.contributing_indicator_ids:
        assert ref in all_ids

    assert report.malware_family.evidence_refs
    for ref in report.malware_family.evidence_refs:
        assert ref in all_ids

    md = render_markdown(report)
    for ref in report.risk_score.contributing_indicator_ids:
        assert f"[^{ref}]" in md, (
            f"Markdown must reference Indicator {ref!r} via a footnote"
        )


# ---------------------------------------------------------------------------
# AC-6 — analysis_coverage summary lists per-dimension statuses
# ---------------------------------------------------------------------------


def test_analysis_coverage_summary_present():
    store = _build_normal_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    md = render_markdown(report)

    expected_dimensions = {
        "structure",
        "entropy",
        "strings",
        "decompilation",
        "behavior_chain",
        "llm_inferences",
    }
    assert expected_dimensions.issubset(report.analysis_coverage.dimensions.keys())
    for status in report.analysis_coverage.dimensions.values():
        assert status in {
            CoverageStatus.COMPLETED,
            CoverageStatus.DEGRADED,
            CoverageStatus.SKIPPED,
        }

    for dim in expected_dimensions:
        assert dim in md


def test_analysis_coverage_reflects_degraded_state():
    store = _build_degraded_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-degraded")

    dims = report.analysis_coverage.dimensions
    assert dims["decompilation"] == CoverageStatus.SKIPPED
    assert dims["behavior_chain"] == CoverageStatus.SKIPPED


# ---------------------------------------------------------------------------
# ADR-07 — FR-17 two-phase ordering (module-first, function-second)
# ---------------------------------------------------------------------------


def test_fr17_phase2_without_phase1_flags_gap_and_degrades_behavior_chain():
    """Phase 2 (`function_behavior_node`) without Phase 1 (`module_behavior_node`)
    must surface ``fr17_phase1_missing`` and downgrade the ``behavior_chain``
    coverage dimension to ``DEGRADED`` (ADR-07 prompt-level enforcement).
    """
    store = _build_normal_chain(analysis_id="report-phase1-missing")
    anchor = store.snapshot().file_meta[0].id
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="function_behavior_node",
        severity=Severity.WARNING,
        confidence=Confidence.MEDIUM,
        evidence_refs=[anchor],
        data={
            "function": "sub_401000",
            "capability": "process_manipulation",
            "rationale": "CreateRemoteThread + WriteProcessMemory",
        },
    )

    report = build_report_v1(store.snapshot(), analysis_id="report-phase1-missing")

    assert FR17_PHASE1_MISSING_GAP in report.analysis_coverage.gaps, (
        "Phase 2 output without Phase 1 must emit fr17_phase1_missing gap"
    )
    assert (
        report.analysis_coverage.dimensions["behavior_chain"] is CoverageStatus.DEGRADED
    ), "behavior_chain dimension must be downgraded to DEGRADED"


def test_fr17_phase1_then_phase2_does_not_flag_gap():
    """Module node present → Phase 2 is legitimate → no gap fires."""
    store = _build_normal_chain(analysis_id="report-phase-ordered")
    anchor = store.snapshot().file_meta[0].id
    module_id = add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="module_behavior_node",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        data={
            "module_id": "mod_0001",
            "capabilities": ["process_manipulation", "persistence"],
        },
    )
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="function_behavior_node",
        severity=Severity.WARNING,
        confidence=Confidence.MEDIUM,
        evidence_refs=[module_id],
        data={"function": "sub_401000", "capability": "process_manipulation"},
    )

    report = build_report_v1(store.snapshot(), analysis_id="report-phase-ordered")

    assert FR17_PHASE1_MISSING_GAP not in report.analysis_coverage.gaps
    assert (
        report.analysis_coverage.dimensions["behavior_chain"]
        is CoverageStatus.COMPLETED
    ), "ordered Phase 1 → Phase 2 must keep behavior_chain COMPLETED"


def test_fr17_phase1_gap_absent_on_malicious_fixture():
    """Existing malicious fixture uses `behavior_segment` (not phase nodes);
    ADR-07 gap must not regress against it (acceptance condition)."""
    store = _build_normal_chain(analysis_id="report-regression")
    report = build_report_v1(store.snapshot(), analysis_id="report-regression")

    assert FR17_PHASE1_MISSING_GAP not in report.analysis_coverage.gaps
    assert (
        report.analysis_coverage.dimensions["behavior_chain"]
        is CoverageStatus.COMPLETED
    )
    md = render_markdown(report)
    assert "```mermaid" in md, (
        "malicious fixture must still produce the full behavior-chain section"
    )


# ---------------------------------------------------------------------------
# AC-7 — behavior chain structural expression (nodes + edges + mermaid)
# ---------------------------------------------------------------------------


def test_behavior_chain_structural_expression():
    store = _build_normal_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    payload = json.loads(render_json(report))

    assert payload["behavior_chain"]["nodes"], "behavior_chain.nodes must not be empty"
    assert isinstance(payload["behavior_chain"]["edges"], list)

    md = render_markdown(report)
    assert "```mermaid" in md, "Markdown behavior chain must include a mermaid block"
    assert "graph TD" in md


def test_behavior_chain_uses_function_edge_indicator():
    """Function-level edge Indicators must render as real graph edges."""
    store = _build_report_base_chain("report-function-edge")
    anchor = store.snapshot().file_meta[0].id
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="module_behavior_node",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        source_fr="FR-17",
        data={"module_id": "mod_0001", "capabilities": ["persistence"]},
    )
    first = add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="function_behavior_node",
        severity=Severity.WARNING,
        confidence=Confidence.MEDIUM,
        evidence_refs=[anchor],
        source_fr="FR-17",
        data={
            "function_address": "0x401000",
            "function_name": "sub_401000",
            "step_label": "Create autorun registry value",
        },
    )
    second = add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="function_behavior_node",
        severity=Severity.WARNING,
        confidence=Confidence.MEDIUM,
        evidence_refs=[anchor],
        source_fr="FR-17",
        data={
            "function_address": "0x402000",
            "function_name": "sub_402000",
            "step_label": "Launch payload after reboot",
        },
    )
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="function_behavior_edge",
        severity=Severity.INFO,
        confidence=Confidence.MEDIUM,
        evidence_refs=[first, second],
        source_fr="FR-17",
        data={"src": first, "dst": second, "edge_kind": "data_flow"},
    )

    report = build_report_v1(store.snapshot(), analysis_id="report-function-edge")

    edges = report.behavior_chain.edges
    assert len(edges) == 1
    assert edges[0].label == "data_flow"
    assert edges[0].source == "n2"
    assert edges[0].target == "n3"
    md = render_markdown(report)
    assert "n2 -->|data_flow| n3" in md


def test_behavior_chain_uses_module_edge_indicator():
    """Module-level edge Indicators must resolve data.src/data.dst module IDs."""
    store = _build_report_base_chain("report-module-edge")
    anchor = store.snapshot().file_meta[0].id
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="module_behavior_node",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        source_fr="FR-17",
        data={"module_id": "mod_0001", "capabilities": ["dynamic_loading"]},
    )
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="module_behavior_node",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        source_fr="FR-17",
        data={"module_id": "mod_0002", "capabilities": ["network_c2"]},
    )
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="module_behavior_edge",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        source_fr="FR-17",
        data={"src": "mod_0001", "dst": "mod_0002", "edge_count": 3},
    )

    report = build_report_v1(store.snapshot(), analysis_id="report-module-edge")

    assert [node.label for node in report.behavior_chain.nodes] == [
        "mod_0001",
        "mod_0002",
    ]
    assert len(report.behavior_chain.edges) == 1
    edge = report.behavior_chain.edges[0]
    assert (edge.source, edge.target, edge.label) == ("n1", "n2", "control_flow")


def test_behavior_chain_legacy_sequential_fallback():
    """Legacy behavior rows without edge Indicators keep insertion-order `next` edges."""
    store = _build_report_base_chain("report-legacy-chain")
    add_fact(
        store,
        Bucket.behavior_chain,
        indicator_type="behavior_segment",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"segment": "dropper stage"},
    )
    add_fact(
        store,
        Bucket.behavior_chain,
        indicator_type="behavior_segment",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"segment": "persistence stage"},
    )

    report = build_report_v1(store.snapshot(), analysis_id="report-legacy-chain")

    assert [node.label for node in report.behavior_chain.nodes] == [
        "dropper stage",
        "persistence stage",
    ]
    assert len(report.behavior_chain.edges) == 1
    assert report.behavior_chain.edges[0].label == "next"
    md = render_markdown(report)
    assert "n1 -->|next| n2" in md


# ---------------------------------------------------------------------------
# AC-8 — default file names follow <sha256>.report.{json,md}
# ---------------------------------------------------------------------------


def test_output_file_naming_sha256(tmp_path: Path):
    store = _build_normal_chain()
    out_dir = tmp_path / "reports"
    tool = ReportGenTool(store=store)
    payload = tool.invoke(
        {
            "analysis_id": "report-normal",
            "output_dir": str(out_dir),
        }
    )

    expected_json = out_dir / f"{_TEST_SHA256}.report.json"
    expected_md = out_dir / f"{_TEST_SHA256}.report.md"
    assert expected_json.is_file()
    assert expected_md.is_file()
    assert payload["json_path"] == str(expected_json)
    assert payload["md_path"] == str(expected_md)
    assert payload["sha256"] == _TEST_SHA256
    assert payload["markdown_content"] == expected_md.read_text(encoding="utf-8")
    assert MARKDOWN_REPORT_TITLE in payload["markdown_content"]

    data = json.loads(expected_json.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.1.0"


# ---------------------------------------------------------------------------
# AC-9 — degraded fixture surfaces the fixed Chinese phrases
# ---------------------------------------------------------------------------


def test_degraded_fixture_surfaces_fixed_phrases():
    store = _build_degraded_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-degraded")
    md = render_markdown(report)

    assert MARKDOWN_DEGRADED_DISASSEMBLY in md
    assert MARKDOWN_DEGRADED_BEHAVIOR in md
    assert "建议" in md, "degradation section must include remediation suggestions"


def test_static_behavior_fallback_renders_degraded_graph():
    """Static imports/IOC evidence should render a fallback graph, not unavailable."""
    store = _build_report_base_chain("report-static-fallback")
    add_fact(
        store,
        Bucket.imports,
        indicator_type="suspicious_import",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"api": "WinHttpSendRequest", "module": "winhttp.dll"},
    )
    add_fact(
        store,
        Bucket.strings_iocs,
        indicator_type="url",
        severity=Severity.WARNING,
        confidence=Confidence.MEDIUM,
        data={"value": "hxxp://example.invalid/a"},
    )
    ScoringTool(store=store).invoke({"analysis_id": "report-static-fallback"})
    DecisionGateTool(store=store).invoke({"analysis_id": "report-static-fallback"})

    report = build_report_v1(store.snapshot(), analysis_id="report-static-fallback")
    md = render_markdown(report)

    assert report.behavior_chain.nodes
    assert (
        report.analysis_coverage.dimensions["behavior_chain"] is CoverageStatus.DEGRADED
    )
    assert MARKDOWN_DEGRADED_BEHAVIOR not in md
    assert "静态证据降级图" in md
    assert "network c2" in md
    assert "```mermaid" in md


def test_exception_path_produces_valid_report():
    """LOW-confidence / UNKNOWN path still produces a schema-compliant report."""
    store = _build_exception_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-exception")

    assert isinstance(report, ReportV1)
    assert report.verdict.label == VerdictLabel.UNKNOWN
    md = render_markdown(report)
    assert VerdictLabel.UNKNOWN.value in md


# ---------------------------------------------------------------------------
# AC-10 — temporary files are cleaned after generate()
# ---------------------------------------------------------------------------


def test_generate_cleans_tmp_dir(tmp_path: Path):
    """``<tmp_root>/deepagent-analyze-<aid>/`` is removed; report files remain."""
    analysis_id = "report-cleanup"
    tmp_root = tmp_path / "hosttmp"
    tmp_root.mkdir()
    analysis_tmp = tmp_root / f"deepagent-analyze-{analysis_id}"
    analysis_tmp.mkdir()
    (analysis_tmp / "ghidra-project.gpr").write_text("dummy")
    (analysis_tmp / "strings.txt").write_text("intermediate")

    out_dir = tmp_path / "reports"
    store = _build_normal_chain(analysis_id=analysis_id)

    tool = ReportGenTool(store=store)
    payload = tool.invoke(
        {
            "analysis_id": analysis_id,
            "output_dir": str(out_dir),
            "tmp_root": str(tmp_root),
        }
    )

    assert not analysis_tmp.exists(), "analysis tmp dir must be cleaned after generate"
    assert Path(payload["json_path"]).is_file()
    assert Path(payload["md_path"]).is_file()


def test_generate_cleanup_skipped_when_tmp_root_absent(tmp_path: Path):
    """When caller does not supply ``tmp_root``, generate() still succeeds."""
    store = _build_normal_chain()
    out_dir = tmp_path / "reports"
    tool = ReportGenTool(store=store)
    payload = tool.invoke(
        {
            "analysis_id": "report-normal",
            "output_dir": str(out_dir),
        }
    )
    assert Path(payload["json_path"]).is_file()


# ---------------------------------------------------------------------------
# Schema-stability sanity
# ---------------------------------------------------------------------------


def test_schema_version_matches_report_v1_default():
    store = _build_normal_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-normal")
    assert report.schema_version == "1.1.0"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_build_report_v1_raises_without_file_meta():
    store = EvidenceChainStore(analysis_id="missing-file-meta")
    with pytest.raises(ValueError, match="file_meta"):
        build_report_v1(store.snapshot(), analysis_id="missing-file-meta")


def test_report_gen_tool_returns_schema_error_without_file_meta(tmp_path: Path):
    store = EvidenceChainStore(analysis_id="missing-file-meta")
    tool = ReportGenTool(store=store)

    result = tool.invoke(
        {
            "analysis_id": "missing-file-meta",
            "output_dir": str(tmp_path / "reports"),
        }
    )

    assert result["ok"] is False
    assert result["error_code"] == "TOOL_SCHEMA_INVALID"
    assert result["reason"] == "report_prerequisite_missing"
    assert "file_meta" in result["message"]


# ---------------------------------------------------------------------------
# C11 — FR-15 AC-3/4/5/6/7: document fields, new sections, child refs
# ---------------------------------------------------------------------------

_CHILD_SHA256 = "f" * 64
_CHILD_AID = "child-analysis-01"


def _inject_document_buckets(
    store: EvidenceChainStore,
    *,
    doc_analysis_partial: bool = False,
    infection_source: bool = False,
    add_embedded_payload: bool = True,
) -> None:
    """Inject minimal document-bucket Indicators for C11 fixture tests.

    All ``indicator_type`` values are drawn from the v1.1 allowed enums
    defined in ``schema/indicator_types_v1_1.py`` (IR-DOC-02).
    """
    # document_analysis bucket — "ole_structure" is a valid DOC_ANALYSIS_TYPES member
    add_fact(
        store,
        Bucket.document_analysis,
        indicator_type="ole_structure",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        data={"ole_version": "3.1", "streams_count": 12, "has_macros": True},
    )
    # macro_analysis bucket — "vba_module" is a valid MACRO_ANALYSIS_TYPES member
    add_fact(
        store,
        Bucket.macro_analysis,
        indicator_type="vba_module",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"macro_name": "AutoOpen", "vba_lines": 42, "obfuscated": True},
    )
    # embedded_payloads bucket — "child_sample_ref" matches a child_analysis_id entry
    if add_embedded_payload:
        payload_data: dict = {
            "sha256": _CHILD_SHA256,
            "type": "PE32",
            "child_analysis_id": _CHILD_AID,
            "size_bytes": 65536,
        }
        if infection_source:
            payload_data["document_role"] = "infection_source"
        add_fact(
            store,
            Bucket.embedded_payloads,
            indicator_type="child_sample_ref",
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            data=payload_data,
        )
    # delivery_chain_doc bucket — "delivery_chain_node" is valid
    add_fact(
        store,
        Bucket.delivery_chain_doc,
        indicator_type="delivery_chain_node",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        data={
            "parent_sha256": _TEST_SHA256,
            "child_sha256": _CHILD_SHA256,
            "depth": 1,
        },
    )
    # Mark doc_analysis_partial in llm_inferences — use add_fact (no evidence_refs required)
    if doc_analysis_partial:
        add_fact(
            store,
            Bucket.llm_inferences,
            indicator_type="analysis_coverage",
            severity=Severity.WARNING,
            confidence=Confidence.HIGH,
            data={"doc_analysis_partial": True, "reason": "token_budget_exhausted"},
        )


def _build_doc_chain(
    *,
    analysis_id: str = "report-doc",
    doc_analysis_partial: bool = False,
    infection_source: bool = False,
    add_embedded_payload: bool = True,
) -> EvidenceChainStore:
    """Return a chain with both binary and document evidence for C11 tests."""
    store = _build_normal_chain(analysis_id=analysis_id)
    _inject_document_buckets(
        store,
        doc_analysis_partial=doc_analysis_partial,
        infection_source=infection_source,
        add_embedded_payload=add_embedded_payload,
    )
    return store


# --- AC-3 backward compat ---


def test_doc_fields_absent_on_minimal_fixture():
    """e2e01 minimal fixture (no doc buckets) → no document chapters in Markdown.

    The 4 evidence-bucket summary fields must be None when the corresponding
    buckets are empty.  ``document_role`` may be non-None (the scoring rule
    engine can classify non-document samples as CLEAN), so we don't assert it.
    """
    store = _build_normal_chain(analysis_id="report-no-doc")
    report = build_report_v1(store.snapshot(), analysis_id="report-no-doc")

    # The 4 document-bucket summaries must be absent
    assert report.document_analysis is None
    assert report.macro_analysis is None
    assert report.embedded_payloads is None
    assert report.delivery_chain_doc is None
    assert report.doc_analysis_partial is False

    # The 3 optional Markdown sections must NOT appear
    md = render_markdown(report)
    assert "## 投递链" not in md
    assert "## 宏与嵌入脚本分析" not in md
    assert "## 嵌入载荷清单" not in md


# --- AC-4: new sections present with doc fixture ---


def test_doc_sections_present_with_doc_fixture():
    """Three new Markdown chapters appear when document buckets have data (FR-15 AC-4)."""
    store = _build_doc_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-doc")
    md = render_markdown(report)

    assert "## 投递链" in md, "missing 投递链 section"
    assert "## 宏与嵌入脚本分析" in md, "missing 宏与嵌入脚本分析 section"
    assert "## 嵌入载荷清单" in md, "missing 嵌入载荷清单 section"

    # Sections must appear after 结构异常 and before 升级建议
    pos_structural = md.index("## 结构异常")
    pos_delivery = md.index("## 投递链")
    pos_macro = md.index("## 宏与嵌入脚本分析")
    pos_payloads = md.index("## 嵌入载荷清单")
    pos_escalation = md.index("## 升级建议")

    assert pos_structural < pos_delivery < pos_escalation
    assert pos_structural < pos_macro < pos_escalation
    assert pos_structural < pos_payloads < pos_escalation

    # Section content must be non-empty (check for data values from injected indicators)
    assert "ole_version" in md or "streams_count" in md or "3.1" in md
    assert "AutoOpen" in md or "vba_lines" in md or "42" in md
    assert _CHILD_SHA256 in md


def test_delivery_chain_parent_child_link_renders_verdict():
    """parent_child_link entries should show parent -> child and child verdict."""
    store = _build_doc_chain()
    add_fact(
        store,
        Bucket.delivery_chain_doc,
        indicator_type="parent_child_link",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        source_fr="FR-30",
        data={
            "parent_analysis_id": "parent-doc",
            "child_sample_id": "child-pe-1",
            "child_sha256": _CHILD_SHA256,
            "child_suggested_format": "PE32+",
            "child_verdict": "MALICIOUS",
        },
    )

    report = build_report_v1(store.snapshot(), analysis_id="report-delivery-link")
    md = render_markdown(report)

    assert "### 父子样本链路" in md
    assert "`parent-doc` → `child-pe-1`" in md
    assert "子样本判定：`MALICIOUS`" in md
    assert "格式：PE32+" in md


# --- AC-7: doc_analysis_partial warning block ---


def test_doc_partial_warning_block_in_sections():
    """doc_analysis_partial=True → each document section contains the ⚠️ warning block."""
    store = _build_doc_chain(doc_analysis_partial=True)
    report = build_report_v1(store.snapshot(), analysis_id="report-partial")

    assert report.doc_analysis_partial is True

    md = render_markdown(report)
    warn_marker = "> ⚠️"
    assert warn_marker in md, "warning block must appear when doc_analysis_partial=True"

    # Warning appears in at least one document section
    delivery_start = md.find("## 投递链")
    escalation_start = md.find("## 升级建议")
    doc_sections_text = md[delivery_start:escalation_start]
    assert warn_marker in doc_sections_text, (
        "⚠️ warning must appear inside the document sections"
    )


def test_doc_partial_absent_when_false():
    """doc_analysis_partial=False → no warning block in document sections."""
    store = _build_doc_chain(doc_analysis_partial=False)
    report = build_report_v1(store.snapshot(), analysis_id="report-nodeg")
    assert report.doc_analysis_partial is False

    md = render_markdown(report)
    assert "> ⚠️" not in md


# --- AC-5/6: infection_source + report_ref ---


def test_infection_source_embedded_payload_link(tmp_path: Path):
    """infection_source role + child_reports → Markdown link + JSON report_ref (FR-15 AC-5/6)."""
    store = _build_doc_chain(infection_source=True)
    # Build a fake child ReportGenResult
    child_result = ReportGenResult(
        json_path=str(tmp_path / f"{_CHILD_SHA256}.report.json"),
        md_path=str(tmp_path / f"{_CHILD_SHA256}.report.md"),
        sha256=_CHILD_SHA256,
        schema_version="1.1.0",
    )
    child_reports = {_CHILD_AID: child_result}

    # Manually inject document_role=infection_source via scoring data manipulation:
    # Since ScoringTool derives document_role from the rule engine (no infection_source
    # rule in default YAML), we test the extractor path directly.
    snapshot = store.snapshot()
    report = build_report_v1(
        snapshot, analysis_id="report-infection", child_reports=child_reports
    )

    # JSON: embedded_payloads[].report_ref must be set
    assert report.embedded_payloads is not None
    payload_entry = report.embedded_payloads[0]
    payload_entry["source"] = "pe_carving"
    payload_entry["source_region"] = "overlay"
    payload_entry["offset"] = 4096
    payload_entry["decoder"] = "xor_single_byte"
    payload_entry["child_recursion_status"] = "completed"
    payload_entry["child_verdict"] = "MALICIOUS"
    assert payload_entry.get("report_ref") == f"{_CHILD_SHA256}.report.json", (
        f"expected report_ref={_CHILD_SHA256}.report.json, got {payload_entry.get('report_ref')!r}"
    )

    payload_json = json.loads(render_json(report))
    ep = payload_json["embedded_payloads"][0]
    assert ep.get("report_ref") == f"{_CHILD_SHA256}.report.json"

    # Markdown: link present for the entry
    md = render_markdown(report)
    assert f"{_CHILD_SHA256}.report.json" in md
    assert "source=pe_carving" in md
    assert "region=overlay" in md
    assert "xor_single_byte" in md
    assert "verdict=MALICIOUS" in md


def test_no_report_ref_without_child_reports():
    """Without child_reports, embedded_payloads entries have no report_ref."""
    store = _build_doc_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-noref")

    assert report.embedded_payloads is not None
    for entry in report.embedded_payloads:
        assert "report_ref" not in entry


# --- AC-2/3: schema_version + JSON doc fields ---


def test_schema_version_1_1_0_and_json_doc_fields():
    """JSON output has schema_version=1.1.0 and all v1.1.0 document fields (FR-15 AC-2/3)."""
    store = _build_doc_chain()
    report = build_report_v1(store.snapshot(), analysis_id="report-v11")

    assert report.schema_version == "1.1.0"

    payload = json.loads(render_json(report))
    assert payload["schema_version"] == "1.1.0"

    v1_1_fields = {
        "document_format",
        "document_tier",
        "document_role",
        "doc_analysis_partial",
        "unknown_downgrade_reason",
        "document_analysis",
        "macro_analysis",
        "embedded_payloads",
        "delivery_chain_doc",
    }
    missing = v1_1_fields - set(payload.keys())
    assert not missing, f"Missing v1.1.0 JSON fields: {missing}"

    # Non-None fields populated from document buckets
    assert payload["document_analysis"] is not None
    assert payload["macro_analysis"] is not None
    assert payload["embedded_payloads"] is not None
    assert payload["delivery_chain_doc"] is not None
