"""Unit tests for :mod:`tools.decision_gate` (C12, FR-14 AC-1~7).

Coverage map:

- test_benign_chain_yields_none                                      -> AC-1 / AC-6
- test_malicious_chain_yields_both                                   -> AC-1
- test_sandbox_only_when_evasion_without_coverage_gap                -> AC-1
- test_manual_reverse_only_when_coverage_gap                         -> AC-1
- test_escalation_reasons_cite_indicator_ids                         -> AC-2
- test_escalation_status_constant                                    -> AC-3
- test_dynamic_behavior_placeholder_is_empty                         -> AC-4
- test_markdown_disclaimer_exact_chinese_text                        -> AC-5
- test_decision_gate_tool_appends_indicator                          -> AC-7
- test_infection_source_incomplete_recursion_triggers_sandbox        -> AC-3 condition 1
- test_p2_tier_with_vba_triggers_manual_reverse                     -> AC-3 condition 2
- test_p2_tier_with_embedded_pe_triggers_manual_reverse             -> AC-3 condition 2
- test_encrypted_office_no_password_triggers_manual_reverse         -> AC-3 condition 3
- test_encrypted_office_via_llm_inferences_mock_triggers_manual     -> AC-3 condition 3 (mock)
- test_infection_source_without_incomplete_recursion_does_not_trigger -> AC-3 condition 1 boundary
- test_p2_tier_without_active_content_does_not_trigger              -> AC-3 condition 2 boundary
"""

from __future__ import annotations

from evidence_chain.store import EvidenceChainStore
from schema.document_enums import (
    DocumentRole,
    DocumentTier,
    UnknownDowngradeReason,
)
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Indicator, Severity
from schema.report import VerdictLabel
from tests.fixtures.evidence_chains import benign, malicious, suspicious
from tests.fixtures.evidence_chains._helpers import add_fact, anchor_id, new_store
from tools.decision_gate import (
    ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED,
    MARKDOWN_DISCLAIMER,
    DecisionGateResult,
    DecisionGateTool,
    RecommendedEscalation,
    decide_escalation,
    markdown_disclaimer,
)
from tools.scoring import ScoringTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _inject_scoring_indicator(
    store: EvidenceChainStore,
    verdict: VerdictLabel,
    *,
    contributing_ids: list[str] | None = None,
    rule_score: int = 80,
) -> str:
    """Append a minimal ``scoring`` fact to stand in for ScoringTool output.

    Used by tests that need to exercise DecisionGateTool decisions without
    re-running the full rule engine.
    """
    anchor = anchor_id(store)
    ind = Indicator(
        source_fr="FR-13",
        indicator_type="scoring",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        kind="fact",
        evidence_refs=contributing_ids or [anchor],
        data={
            "verdict": verdict.value,
            "rule_score": rule_score,
            "rules_version": "1.0.0",
            "contributing_indicator_ids": contributing_ids or [anchor],
        },
    )
    store.append(Bucket.scoring, ind)
    return ind.id


def _run_scoring_tool(store: EvidenceChainStore, analysis_id: str) -> None:
    """Execute the real ScoringTool so the snapshot includes a scoring Indicator."""
    ScoringTool(store=store).invoke({"analysis_id": analysis_id})


# ---------------------------------------------------------------------------
# AC-1 / AC-6 — Recommendation enum across input combinations
# ---------------------------------------------------------------------------


def test_benign_chain_yields_none():
    store = benign.build()
    _run_scoring_tool(store, "benign-analysis")

    result = decide_escalation(store.snapshot())

    assert isinstance(result, DecisionGateResult)
    assert result.recommended_escalation == RecommendedEscalation.NONE


def test_malicious_chain_yields_both():
    """MALICIOUS fixture has evasion (UPX + anti-debug) AND missing disassembly.

    → both sandbox and manual triggers fire → BOTH.
    """
    store = malicious.build()
    _run_scoring_tool(store, "malicious-analysis")

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.BOTH


def test_sandbox_only_when_evasion_without_coverage_gap():
    """Evasion present (packer) but decompilation + behavior chain populated.

    → only sandbox trigger fires → SANDBOX.
    """
    store = new_store(analysis_id="sandbox-only")
    add_fact(
        store,
        Bucket.packer,
        indicator_type="packer_detected",
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        data={"packer": "UPX"},
    )
    add_fact(
        store,
        Bucket.disassembly,
        indicator_type="function_decompiled",
        severity=Severity.INFO,
        data={"function": "sub_401000"},
    )
    add_fact(
        store,
        Bucket.behavior_chain,
        indicator_type="behavior_segment",
        severity=Severity.WARNING,
        data={"segment": "entry -> decrypt -> exec"},
    )
    _inject_scoring_indicator(store, VerdictLabel.MALICIOUS)

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.SANDBOX


def test_manual_reverse_only_when_coverage_gap_without_evasion():
    """No evasion facts but disassembly + behavior chain empty on non-BENIGN verdict.

    → only manual trigger fires → MANUAL_REVERSE.
    """
    store = new_store(analysis_id="manual-only")
    _inject_scoring_indicator(store, VerdictLabel.SUSPICIOUS, rule_score=50)

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.MANUAL_REVERSE


# ---------------------------------------------------------------------------
# AC-2 — escalation_reasons cite real Indicator IDs
# ---------------------------------------------------------------------------


def test_escalation_reasons_cite_indicator_ids():
    store = malicious.build()
    _run_scoring_tool(store, "malicious-analysis")
    snap = store.snapshot()
    all_ids = {
        ind.id
        for field_name in snap.__class__.model_fields
        for ind in getattr(snap, field_name)
    }

    result = decide_escalation(snap)

    assert result.escalation_reasons, (
        "non-NONE escalation must carry at least one structured reason"
    )
    for reason in result.escalation_reasons:
        assert reason.reason_text, "reason_text must be non-empty"
        assert reason.evidence_refs, (
            "each escalation_reason must reference at least one Indicator ID (AC-2)"
        )
        for ref in reason.evidence_refs:
            assert ref in all_ids, (
                f"evidence_ref {ref!r} not found in the current evidence chain"
            )


# ---------------------------------------------------------------------------
# AC-3 — escalation_status constant
# ---------------------------------------------------------------------------


def test_escalation_status_constant():
    store = benign.build()
    _run_scoring_tool(store, "benign-analysis")

    result = decide_escalation(store.snapshot())

    assert result.escalation_status == ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED
    assert result.escalation_status == "RECOMMENDED_NOT_EXECUTED"


# ---------------------------------------------------------------------------
# AC-4 — dynamic_behavior placeholder compatibility
# ---------------------------------------------------------------------------


def test_dynamic_behavior_placeholder_is_empty():
    """Output carries an empty ``dynamic_behavior`` list; schema bucket stays empty."""
    store = suspicious.build()
    _run_scoring_tool(store, "suspicious-analysis")

    result = decide_escalation(store.snapshot())

    assert result.dynamic_behavior == []
    assert store.snapshot().dynamic_behavior == []


# ---------------------------------------------------------------------------
# AC-5 — Markdown disclaimer exact Chinese text
# ---------------------------------------------------------------------------


def test_markdown_disclaimer_exact_chinese_text():
    """Disclaimer is a fixed Chinese string mandated by FR-14 AC-5."""
    text = markdown_disclaimer()

    assert text == MARKDOWN_DISCLAIMER
    assert "本系统当前版本不执行样本代码" in text
    assert "静态分析后的下一步建议" in text
    assert "请由分析师或 SOAR 平台自行调度动态分析" in text


# ---------------------------------------------------------------------------
# AC-7 — DecisionGateTool writes the decision_gate bucket
# ---------------------------------------------------------------------------


def test_decision_gate_tool_appends_indicator_to_decision_gate_bucket():
    store = malicious.build()
    _run_scoring_tool(store, "malicious-analysis")

    tool = DecisionGateTool(store=store)
    payload = tool.invoke({"analysis_id": "malicious-analysis"})

    snap = store.snapshot()
    assert len(snap.decision_gate) == 1
    dg = snap.decision_gate[0]
    assert dg.source_fr == "FR-14"
    assert dg.indicator_type == "decision_gate"
    assert dg.kind == "fact"
    assert dg.data["recommended_escalation"] == RecommendedEscalation.BOTH.value
    assert dg.data["escalation_status"] == ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED
    assert dg.data["dynamic_behavior"] == []
    assert dg.data["markdown_disclaimer"] == MARKDOWN_DISCLAIMER
    assert payload["indicator_id"] == dg.id
    assert payload["recommended_escalation"] == RecommendedEscalation.BOTH.value


def test_decision_gate_tool_aggregates_evidence_refs_into_indicator():
    """The emitted Indicator's ``evidence_refs`` is the union of all reason refs."""
    store = malicious.build()
    _run_scoring_tool(store, "malicious-analysis")

    DecisionGateTool(store=store).invoke({"analysis_id": "malicious-analysis"})

    snap = store.snapshot()
    dg = snap.decision_gate[0]
    expected_refs: set[str] = set()
    for reason in dg.data["escalation_reasons"]:
        expected_refs.update(reason["evidence_refs"])
    assert set(dg.evidence_refs) == expected_refs
    assert expected_refs, "evidence_refs must not be empty for non-NONE escalation"


# ---------------------------------------------------------------------------
# FR-14 AC-3: Document-specific escalation triggers (C10)
# ---------------------------------------------------------------------------


def _inject_scoring_with_document_fields(
    store: EvidenceChainStore,
    verdict: VerdictLabel,
    *,
    document_role: DocumentRole | None = None,
    unknown_downgrade_reason: UnknownDowngradeReason | None = None,
) -> str:
    """Append a scoring Indicator carrying optional document-analysis fields."""
    anchor = anchor_id(store)
    ind = Indicator(
        source_fr="FR-13",
        indicator_type="scoring",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        kind="fact",
        evidence_refs=[anchor],
        data={
            "verdict": verdict.value,
            "rule_score": 60,
            "rules_version": "1.1.0",
            "contributing_indicator_ids": [anchor],
            "document_role": document_role.value if document_role is not None else None,
            "unknown_downgrade_reason": (
                unknown_downgrade_reason.value
                if unknown_downgrade_reason is not None
                else None
            ),
        },
    )
    store.append(Bucket.scoring, ind)
    return ind.id


def test_infection_source_incomplete_recursion_triggers_sandbox():
    """FR-14 AC-3 cond-1: infection_source + recursion_budget_exceeded → SANDBOX."""
    store = new_store(analysis_id="doc-infection-source")
    add_fact(
        store,
        Bucket.file_meta,
        indicator_type="file_meta",
        severity=Severity.INFO,
        data={"document_tier": DocumentTier.P0, "document_format": "ooxml_docx_macro"},
    )
    embed_id = add_fact(
        store,
        Bucket.embedded_payloads,
        indicator_type="embedded_ole_object",
        severity=Severity.CRITICAL,
        data={"suggested_format": "pe"},
    )
    scoring_id = _inject_scoring_with_document_fields(
        store,
        VerdictLabel.MALICIOUS,
        document_role=DocumentRole.INFECTION_SOURCE,
        unknown_downgrade_reason=UnknownDowngradeReason.RECURSION_BUDGET_EXCEEDED,
    )
    # Populate disassembly + behavior_chain so coverage-gap manual trigger does NOT fire.
    add_fact(
        store,
        Bucket.disassembly,
        indicator_type="function_decompiled",
        severity=Severity.INFO,
        data={"function": "sub_401000"},
    )
    add_fact(
        store,
        Bucket.behavior_chain,
        indicator_type="behavior_segment",
        severity=Severity.WARNING,
        data={"segment": "entry -> dropper"},
    )

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.SANDBOX
    doc_reasons = [r for r in result.escalation_reasons if r.trigger == "sandbox"]
    assert doc_reasons, "expected at least one sandbox escalation reason"
    infection_reason = next(
        (r for r in doc_reasons if "infection_source" in r.reason_text),
        None,
    )
    assert infection_reason is not None, "infection_source trigger reason not found"
    assert scoring_id in infection_reason.evidence_refs
    assert embed_id in infection_reason.evidence_refs
    assert "recursion_budget_exceeded" in infection_reason.reason_text


def test_p2_tier_with_vba_triggers_manual_reverse():
    """FR-14 AC-3 cond-2: P2 tier + VBA macro present → MANUAL_REVERSE."""
    store = new_store(analysis_id="doc-p2-vba")
    add_fact(
        store,
        Bucket.file_meta,
        indicator_type="file_meta",
        severity=Severity.INFO,
        data={"document_tier": DocumentTier.P2, "document_format": "encrypted_office"},
    )
    vba_id = add_fact(
        store,
        Bucket.macro_analysis,
        indicator_type="vba_module",
        severity=Severity.WARNING,
        data={"module_name": "ThisDocument", "auto_exec": True},
    )
    _inject_scoring_indicator(store, VerdictLabel.SUSPICIOUS)

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.MANUAL_REVERSE
    manual_reasons = [r for r in result.escalation_reasons if r.trigger == "manual"]
    p2_reason = next(
        (r for r in manual_reasons if "P2" in r.reason_text),
        None,
    )
    assert p2_reason is not None, "P2-tier trigger reason not found"
    assert vba_id in p2_reason.evidence_refs
    assert "VBA 宏" in p2_reason.reason_text


def test_p2_tier_with_embedded_pe_triggers_manual_reverse():
    """FR-14 AC-3 cond-2: P2 tier + embedded PE → MANUAL_REVERSE."""
    store = new_store(analysis_id="doc-p2-pe")
    add_fact(
        store,
        Bucket.file_meta,
        indicator_type="file_meta",
        severity=Severity.INFO,
        data={"document_tier": DocumentTier.P2, "document_format": "onenote"},
    )
    pe_id = add_fact(
        store,
        Bucket.embedded_payloads,
        indicator_type="embedded_ole_object",
        severity=Severity.CRITICAL,
        data={"suggested_format": "pe"},
    )
    _inject_scoring_indicator(store, VerdictLabel.MALICIOUS)

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.MANUAL_REVERSE
    manual_reasons = [r for r in result.escalation_reasons if r.trigger == "manual"]
    p2_reason = next(
        (r for r in manual_reasons if "P2" in r.reason_text),
        None,
    )
    assert p2_reason is not None
    assert pe_id in p2_reason.evidence_refs
    assert "嵌入 PE" in p2_reason.reason_text


def test_encrypted_office_no_password_triggers_manual_reverse():
    """FR-14 AC-3 cond-3: encrypted_office_no_password in scoring → MANUAL_REVERSE."""
    store = new_store(analysis_id="doc-enc-no-pwd")
    scoring_id = _inject_scoring_with_document_fields(
        store,
        VerdictLabel.UNKNOWN,
        unknown_downgrade_reason=UnknownDowngradeReason.ENCRYPTED_OFFICE_NO_PASSWORD,
    )

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.MANUAL_REVERSE
    manual_reasons = [r for r in result.escalation_reasons if r.trigger == "manual"]
    enc_reason = next(
        (r for r in manual_reasons if "encrypted_office_no_password" in r.reason_text),
        None,
    )
    assert enc_reason is not None, (
        "encrypted_office_no_password trigger reason not found"
    )
    assert scoring_id in enc_reason.evidence_refs


def test_encrypted_office_via_llm_inferences_mock_triggers_manual():
    """FR-14 AC-3 cond-3: encrypted_office_no_password in llm_inferences → MANUAL_REVERSE.

    This tests the parallel-batch mock interface where C5 has not yet written
    to the scoring bucket and instead injects the marker into llm_inferences.
    """
    store = new_store(analysis_id="doc-enc-mock")
    llm_id = add_fact(
        store,
        Bucket.llm_inferences,
        indicator_type="llm_document_inference",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        data={"unknown_downgrade_reason": "encrypted_office_no_password"},
    )

    result = decide_escalation(store.snapshot())

    assert result.recommended_escalation == RecommendedEscalation.MANUAL_REVERSE
    manual_reasons = [r for r in result.escalation_reasons if r.trigger == "manual"]
    enc_reason = next(
        (r for r in manual_reasons if "encrypted_office_no_password" in r.reason_text),
        None,
    )
    assert enc_reason is not None
    assert llm_id in enc_reason.evidence_refs


def test_infection_source_without_incomplete_recursion_does_not_trigger():
    """FR-14 AC-3 cond-1 boundary: infection_source alone (no downgrade) → no doc trigger."""
    store = new_store(analysis_id="doc-infection-no-budget")
    add_fact(
        store,
        Bucket.embedded_payloads,
        indicator_type="embedded_ole_object",
        severity=Severity.CRITICAL,
        data={"suggested_format": "pe"},
    )
    _inject_scoring_with_document_fields(
        store,
        VerdictLabel.MALICIOUS,
        document_role=DocumentRole.INFECTION_SOURCE,
        unknown_downgrade_reason=None,
    )
    # disassembly + behavior_chain populated → no coverage-gap manual trigger either
    add_fact(
        store,
        Bucket.disassembly,
        indicator_type="function_decompiled",
        severity=Severity.INFO,
        data={"function": "sub_401000"},
    )
    add_fact(
        store,
        Bucket.behavior_chain,
        indicator_type="behavior_segment",
        severity=Severity.WARNING,
        data={"segment": "entry -> payload"},
    )

    result = decide_escalation(store.snapshot())

    infection_reasons = [
        r for r in result.escalation_reasons if "infection_source" in r.reason_text
    ]
    assert infection_reasons == [], (
        "infection_source trigger must NOT fire when no incomplete-recursion downgrade"
    )


def test_p2_tier_without_active_content_does_not_trigger():
    """FR-14 AC-3 cond-2 boundary: P2 tier but no VBA/JS/PE → no P2 trigger."""
    store = new_store(analysis_id="doc-p2-no-content")
    add_fact(
        store,
        Bucket.file_meta,
        indicator_type="file_meta",
        severity=Severity.INFO,
        data={"document_tier": DocumentTier.P2, "document_format": "onenote"},
    )
    _inject_scoring_indicator(store, VerdictLabel.BENIGN)

    result = decide_escalation(store.snapshot())

    p2_reasons = [r for r in result.escalation_reasons if "P2" in r.reason_text]
    assert p2_reasons == [], (
        "P2 trigger must NOT fire when no VBA / embedded JS / embedded PE detected"
    )
