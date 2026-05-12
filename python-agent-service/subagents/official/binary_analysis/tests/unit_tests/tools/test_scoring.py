"""Unit tests for :mod:`tools.scoring` (FR-13 AC-1~7).

Coverage map:

- test_load_rules_reads_yaml_version                      -> AC-5 / FR-13 AC-7 (v1.1)
- test_load_rules_rejects_missing_version                 -> AC-5 / §3.3
- test_load_rules_rejects_unknown_bucket                  -> §3.3 input validation
- test_load_rules_rejects_unknown_combo_rule_id           -> §3.3 input validation
- test_score_benign_chain_yields_benign_verdict           -> AC-1 / AC-2
- test_score_suspicious_chain_yields_suspicious_verdict   -> AC-1 / AC-2
- test_score_malicious_chain_yields_malicious_verdict     -> AC-1 / AC-2
- test_score_is_clamped_to_100                            -> AC-1 (bounds)
- test_result_carries_rules_version                       -> AC-5
- test_threat_class_extracted_from_llm_inferences         -> AC-3
- test_threat_class_empty_when_no_inference               -> AC-3 (absent)
- test_family_from_llm_inferences                         -> AC-4
- test_unknown_family_when_no_family_indicator            -> AC-4 (default)
- test_combo_rule_adds_bonus_weight                       -> AC-6
- test_combo_bonus_greater_than_sum_of_singles            -> AC-6 (red-line)
- test_scoring_tool_appends_indicator_to_scoring_bucket   -> AC-7
- test_scoring_tool_writes_evidence_refs                  -> AC-7 (audit)
- test_low_confidence_chain_downgrades_to_unknown         -> AC-8
- test_verdict_divergence_recorded_when_llm_disagrees     -> AC-9
- test_no_divergence_when_llm_agrees                      -> AC-9 (negative)

C9 additions (FR-13 AC-2/3/4/5/6/7 · A-05):

- test_v11_rules_has_document_namespace         -> FR-13 AC-7 / namespace loading
- test_v10_flat_format_treated_as_binary        -> A-05 backward compatibility
- test_v10_flat_format_verdict_identical        -> A-05 backward compatibility (scoring parity)
- test_document_role_clean                      -> FR-13 AC-4/5
- test_document_role_carrier                    -> FR-13 AC-4/5
- test_document_role_payload_host               -> FR-13 AC-4/5
- test_document_role_infection_source           -> FR-13 AC-4/5
- test_document_extract_office_trigger_scores   -> FR-13 AC-4/5 (FR-03 tag alignment)
- test_document_extract_pdf_js_scores           -> FR-13 AC-4/5 (FR-03 tag alignment)
- test_pdf_embedded_pe_scores_payload_host      -> FR-13 AC-4/5 (PDF payload host)
- test_pdf_keyword_summary_scores_exploit_surface -> FR-13 AC-4/5 (PDF keyword summary)
- test_pdf_js_shellcode_scores_carrier          -> FR-13 AC-4/5 (PDF JS exploit marker)
- test_unknown_downgrade_reason_is_enum         -> FR-13 AC-6 (enum migration)
- test_unknown_downgrade_reason_encrypted_office -> FR-13 AC-6 (encrypted_office value)
- test_unknown_namespace_skipped_silently        -> FR-13 AC-7 (unknown namespace tolerance)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence_chain.store import EvidenceChainStore
from schema.document_enums import DocumentRole, UnknownDowngradeReason
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Indicator, Severity
from schema.report import VerdictLabel
from tests.fixtures.evidence_chains import (
    benign,
    combo,
    low_confidence,
    malicious,
    suspicious,
)
from tests.fixtures.evidence_chains._helpers import (
    add_fact,
    add_inference,
    anchor_id,
    new_store,
)
from tools.scoring import (
    RuleEngineConfigError,
    ScoringResult,
    ScoringTool,
    load_rules,
    score_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_rules():
    """Cached default rule set loaded from ``config/scoring_rules.yaml``."""
    return load_rules()


# ---------------------------------------------------------------------------
# load_rules / YAML schema validation (AC-5, §3.3)
# ---------------------------------------------------------------------------


def test_load_rules_reads_yaml_version(default_rules):
    assert default_rules.version == "1.1.1"
    assert default_rules.thresholds.malicious == 70
    assert default_rules.thresholds.suspicious == 30


def test_load_rules_rejects_missing_version(tmp_path: Path):
    bad = tmp_path / "rules.yaml"
    bad.write_text("thresholds: {malicious: 70, suspicious: 30}\nrules: []\n")
    with pytest.raises(RuleEngineConfigError) as exc:
        load_rules(bad)
    assert "version" in str(exc.value).lower()


def test_load_rules_rejects_unknown_bucket(tmp_path: Path):
    bad = tmp_path / "rules.yaml"
    bad.write_text(
        "version: '1.0.0'\n"
        "thresholds: {malicious: 70, suspicious: 30, unknown_low_confidence_max: 50}\n"
        "rules:\n"
        "  - id: R-BAD\n"
        "    description: x\n"
        "    bucket: nonexistent_bucket\n"
        "    weight: 10\n"
        "    match: {severity_in: [WARNING]}\n"
    )
    with pytest.raises(RuleEngineConfigError):
        load_rules(bad)


def test_load_rules_rejects_unknown_combo_rule_id(tmp_path: Path):
    bad = tmp_path / "rules.yaml"
    bad.write_text(
        "version: '1.0.0'\n"
        "thresholds: {malicious: 70, suspicious: 30, unknown_low_confidence_max: 50}\n"
        "rules:\n"
        "  - id: R-A\n"
        "    description: x\n"
        "    bucket: entropy\n"
        "    weight: 10\n"
        "    match: {severity_in: [WARNING]}\n"
        "combos:\n"
        "  - id: COMBO-X\n"
        "    description: y\n"
        "    rule_ids: [R-A, R-DOES-NOT-EXIST]\n"
        "    bonus_weight: 5\n"
    )
    with pytest.raises(RuleEngineConfigError):
        load_rules(bad)


# ---------------------------------------------------------------------------
# Verdict mapping (AC-1, AC-2)
# ---------------------------------------------------------------------------


def test_score_benign_chain_yields_benign_verdict(default_rules):
    store = benign.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert isinstance(result, ScoringResult)
    assert result.rule_score < 30
    assert result.verdict_label == VerdictLabel.BENIGN


def test_format_unsupported_forces_unknown_verdict(default_rules):
    store = new_store(analysis_id="format-unsupported")
    unsupported_id = add_fact(
        store,
        Bucket.file_meta,
        indicator_type="format_unsupported",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        source_fr="FR-01",
        data={"error_code": "ENTRY_FORMAT_UNSUPPORTED"},
    )

    result = score_snapshot(store.snapshot(), default_rules)

    assert result.rule_score == 0
    assert result.verdict_label == VerdictLabel.UNKNOWN
    assert result.contributing_indicator_ids == [unsupported_id]
    assert result.matched_rule_ids == ["R-FORMAT-UNSUPPORTED"]


def test_score_suspicious_chain_yields_suspicious_verdict(default_rules):
    store = suspicious.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert 30 < result.rule_score <= 70
    assert result.verdict_label == VerdictLabel.SUSPICIOUS


def test_score_malicious_chain_yields_malicious_verdict(default_rules):
    store = malicious.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.rule_score > 70
    assert result.verdict_label == VerdictLabel.MALICIOUS


def test_score_is_clamped_to_100(default_rules):
    store = malicious.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert 0 <= result.rule_score <= 100


# ---------------------------------------------------------------------------
# Rule version (AC-5)
# ---------------------------------------------------------------------------


def test_result_carries_rules_version(default_rules):
    store = benign.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.rules_version == "1.1.1"


# ---------------------------------------------------------------------------
# Threat class (AC-3)
# ---------------------------------------------------------------------------


def test_threat_class_extracted_from_llm_inferences(default_rules):
    store = malicious.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.threat_classes == ["InfoStealer", "RAT"]


def test_threat_class_empty_when_no_inference(default_rules):
    store = benign.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.threat_classes == []


# ---------------------------------------------------------------------------
# Family (AC-4)
# ---------------------------------------------------------------------------


def test_family_from_llm_inferences(default_rules):
    store = malicious.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.family_name == "AgentTesla"
    assert result.family_confidence == Confidence.HIGH.value
    assert len(result.family_evidence_refs) >= 1


def test_unknown_family_when_no_family_indicator(default_rules):
    store = benign.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.family_name == "Unknown Family"


# ---------------------------------------------------------------------------
# Combo bonus (AC-6)
# ---------------------------------------------------------------------------


def test_combo_rule_adds_bonus_weight(default_rules):
    store = combo.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert "COMBO-PACKED-DROPPER" in result.matched_combo_ids
    singles_sum = sum(
        h.weight for h in result.rule_hits if h.rule_id != "COMBO-PACKED-DROPPER"
    )
    combo_hit = next(h for h in result.rule_hits if h.rule_id == "COMBO-PACKED-DROPPER")
    assert combo_hit.weight > 0
    assert result.rule_score == singles_sum + combo_hit.weight


def test_combo_bonus_greater_than_sum_of_singles(default_rules):
    """Red-line: combined weight must strictly exceed the sum of the three
    member rules fired in isolation (FR-13 AC-6)."""
    combo_store = combo.build()
    combo_result = score_snapshot(combo_store.snapshot(), default_rules)

    # Singles-only reference: same Indicators but with combo rule disabled
    singles_only_rules = default_rules.without_combos()
    singles_result = score_snapshot(combo_store.snapshot(), singles_only_rules)

    assert singles_result.rule_score == 60
    assert combo_result.rule_score == 85
    assert combo_result.rule_score > singles_result.rule_score


# ---------------------------------------------------------------------------
# Scoring bucket write-through (AC-7)
# ---------------------------------------------------------------------------


def test_scoring_tool_appends_indicator_to_scoring_bucket():
    store = malicious.build()
    tool = ScoringTool(store=store)
    result_dict = tool.invoke({"analysis_id": "malicious-analysis"})

    snap = store.snapshot()
    assert len(snap.scoring) == 1
    scoring_indicator = snap.scoring[0]
    assert scoring_indicator.source_fr == "FR-13"
    assert scoring_indicator.indicator_type == "scoring"
    assert scoring_indicator.kind == "fact"
    assert scoring_indicator.data["verdict"] == VerdictLabel.MALICIOUS.value
    assert scoring_indicator.data["rule_score"] == result_dict["rule_score"]
    assert scoring_indicator.data["rules_version"] == "1.1.1"


def test_scoring_tool_writes_evidence_refs():
    store = malicious.build()
    tool = ScoringTool(store=store)
    tool.invoke({"analysis_id": "malicious-analysis"})

    snap = store.snapshot()
    scoring_indicator = snap.scoring[0]
    assert scoring_indicator.evidence_refs, (
        "scoring Indicator must reference the contributing Indicator IDs (AC-7 audit)"
    )
    all_ids: set[str] = set()
    for field_name in snap.__class__.model_fields:
        items = getattr(snap, field_name)
        for ind in items:
            all_ids.add(ind.id)
    for ref in scoring_indicator.evidence_refs:
        assert ref in all_ids


def test_scoring_tool_returns_structured_config_error(tmp_path: Path):
    bad = tmp_path / "rules.yaml"
    bad.write_text("thresholds: {malicious: 70, suspicious: 30}\nrules: []\n")
    store = malicious.build()
    tool = ScoringTool(store=store, rules_path=bad)

    result = tool.invoke({"analysis_id": "bad-rules-analysis"})

    assert result["ok"] is False
    assert result["error_code"] == "TOOL_SCHEMA_INVALID"
    assert result["reason"] == "missing_version"
    assert store.snapshot().scoring == []


# ---------------------------------------------------------------------------
# AC-8: Low-confidence downgrade to UNKNOWN
# ---------------------------------------------------------------------------


def test_low_confidence_chain_downgrades_to_unknown(default_rules):
    store = low_confidence.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.rule_score == 35
    assert result.verdict_label == VerdictLabel.UNKNOWN
    assert result.unknown_downgrade_reason is not None


# ---------------------------------------------------------------------------
# AC-9: Verdict divergence (LLM vs rule)
# ---------------------------------------------------------------------------


def _inject_llm_verdict(
    store: EvidenceChainStore,
    label: VerdictLabel,
    confidence: Confidence = Confidence.MEDIUM,
) -> str:
    """Append a single ``verdict`` inference to ``llm_inferences``."""
    anchor = store.snapshot().file_meta[0].id
    ind = Indicator(
        source_fr="FR-08",
        indicator_type="verdict",
        severity=Severity.INFO,
        confidence=confidence,
        kind="inference",
        evidence_refs=[anchor],
        data={"label": label.value, "rationale": "LLM synthesis"},
    )
    store.append(Bucket.llm_inferences, ind)
    return ind.id


def test_verdict_divergence_recorded_when_llm_disagrees(default_rules):
    store = malicious.build()
    _inject_llm_verdict(store, VerdictLabel.BENIGN)
    result = score_snapshot(store.snapshot(), default_rules)

    # ADR-04 red-line: final verdict stays rule-authoritative
    assert result.verdict_label == VerdictLabel.MALICIOUS
    assert result.llm_label == VerdictLabel.BENIGN
    assert result.verdict_divergence is not None
    assert "BENIGN" in result.verdict_divergence
    assert "MALICIOUS" in result.verdict_divergence


def test_no_divergence_when_llm_agrees(default_rules):
    store = malicious.build()
    _inject_llm_verdict(store, VerdictLabel.MALICIOUS)
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.verdict_label == VerdictLabel.MALICIOUS
    assert result.llm_label == VerdictLabel.MALICIOUS
    assert result.verdict_divergence is None


# ===========================================================================
# C9 additions — FR-13 AC-2/3/4/5/6/7 · A-05
# ===========================================================================

# ---------------------------------------------------------------------------
# FR-13 AC-7: namespace loading (v1.1 format)
# ---------------------------------------------------------------------------


def test_v11_rules_has_document_namespace(default_rules):
    """v1.1 YAML must expose a non-None document namespace (FR-13 AC-7)."""
    assert default_rules.version == "1.1.1"
    assert default_rules.document is not None
    # binary namespace rules intact
    binary_ids = {r.id for r in default_rules.rules}
    assert "R-ENTROPY-HIGH" in binary_ids
    assert "R-PACKER-KNOWN" in binary_ids
    assert "R-TRIAGE-HIGH-HEURISTIC" in binary_ids
    assert "R-PE-OVERLAY-EMBEDDED-PE" in binary_ids
    assert "R-ELF-EXECUTABLE-STACK" in binary_ids
    assert "R-MACHO-RPATH-ANOMALY" in binary_ids
    assert "R-COMMERCIAL-PROTECTOR" in binary_ids
    assert "R-FAMILY-CANDIDATE-HIGH" in binary_ids
    assert "R-THREAT-CLASS-HIGH" in binary_ids
    assert not any(
        "YARA" in r.id or "YARA" in r.description.upper() for r in default_rules.rules
    )
    # document namespace rules present
    doc_ids = {r.id for r in default_rules.document.rules}
    assert "R-DOC-EMBEDDED-PE" in doc_ids
    assert "R-DOC-VBA-AUTO-TRIGGER" in doc_ids
    assert "R-DOC-REMOTE-TEMPLATE" in doc_ids
    assert "R-DOC-PDF-JBIG2" in doc_ids
    assert "R-DOC-PDF-SHELLCODE-JS" in doc_ids
    # document_role_rules non-empty
    assert len(default_rules.document.document_role_rules) >= 4


# ---------------------------------------------------------------------------
# A-05: v1.0 flat format backward compatibility
# ---------------------------------------------------------------------------

_V10_FLAT_YAML = """\
version: "1.0.0"

thresholds:
  malicious: 70
  suspicious: 30
  unknown_low_confidence_max: 50

rules:
  - id: R-ENTROPY-HIGH
    description: High-entropy section indicates packing / compression
    bucket: entropy
    weight: 25
    match:
      severity_in: [WARNING, CRITICAL]

  - id: R-IMPORTS-SPARSE
    description: Sparse import table
    bucket: imports
    weight: 15
    match:
      indicator_type: imports_sparse

  - id: R-ANTIDEBUG-STRING
    description: Anti-debug strings
    bucket: strings_iocs
    weight: 20
    match:
      indicator_type: anti_debug_string

  - id: R-PACKER-KNOWN
    description: Known packer detected
    bucket: packer
    weight: 30
    match:
      severity_in: [WARNING, CRITICAL]

  - id: R-BEHAVIOR-MAL-CHAIN
    description: CRITICAL behavior chain segment
    bucket: behavior_chain
    weight: 20
    match:
      severity_in: [CRITICAL]

  - id: R-LLM-MAL-INFERENCE
    description: LLM CRITICAL HIGH confidence
    bucket: llm_inferences
    weight: 15
    match:
      severity_in: [CRITICAL]
      confidence_in: [HIGH]

combos:
  - id: COMBO-PACKED-DROPPER
    description: Packed dropper silhouette
    rule_ids: [R-ENTROPY-HIGH, R-IMPORTS-SPARSE, R-ANTIDEBUG-STRING]
    bonus_weight: 25
"""


@pytest.fixture
def v10_rules(tmp_path: Path):
    """Load a v1.0 flat-format YAML (legacy backward-compat path)."""
    f = tmp_path / "rules_v10.yaml"
    f.write_text(_V10_FLAT_YAML, encoding="utf-8")
    return load_rules(f)


def test_v10_flat_format_treated_as_binary(v10_rules):
    """v1.0 flat YAML loads without error; document namespace is None (A-05)."""
    assert v10_rules.version == "1.0.0"
    assert v10_rules.document is None
    assert v10_rules.thresholds.malicious == 70
    assert v10_rules.thresholds.suspicious == 30
    binary_ids = {r.id for r in v10_rules.rules}
    assert "R-ENTROPY-HIGH" in binary_ids


def test_v10_flat_format_verdict_identical(v10_rules, default_rules):
    """Legacy fixtures still score the same under v1.0 and current v1.1 rules."""
    for store_fn in (benign.build, suspicious.build, malicious.build):
        store = store_fn()
        snap = store.snapshot()
        result_v10 = score_snapshot(snap, v10_rules)
        result_v11 = score_snapshot(snap, default_rules)
        assert result_v10.verdict_label == result_v11.verdict_label, (
            f"verdict mismatch for {store_fn.__module__}: "
            f"v1.0={result_v10.verdict_label} v1.1={result_v11.verdict_label}"
        )
        assert result_v10.rule_score == result_v11.rule_score, (
            f"score mismatch for {store_fn.__module__}: "
            f"v1.0={result_v10.rule_score} v1.1={result_v11.rule_score}"
        )


# ---------------------------------------------------------------------------
# v1.1.1 binary scoring expansion — no YARA dependency
# ---------------------------------------------------------------------------


def test_binary_structural_and_triage_rules_score_without_yara(default_rules):
    """Current binary scoring consumes heuristic and structural facts, not YARA."""
    store = new_store("binary-structural-rules")

    add_fact(
        store,
        Bucket.triage,
        indicator_type="triage_risk_level",
        severity=Severity.WARNING,
        source_fr="FR-02",
        data={"risk_level": "HIGH", "reason": "heuristic structure profile"},
    )
    add_fact(
        store,
        Bucket.triage,
        indicator_type="packing_severity_hint",
        severity=Severity.CRITICAL,
        source_fr="FR-02",
        data={"packing_severity_hint": "SEVERE"},
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="entry_point_wx_section",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="entry_point_oob",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="tls_callback_oob",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="tls_callback_wx",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.sections,
        indicator_type="overlay_embedded_pe",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="elf_executable_stack",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="elf_wx_load_segment",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="macho_mod_init_func",
        severity=Severity.WARNING,
        source_fr="FR-04",
    )
    add_fact(
        store,
        Bucket.headers,
        indicator_type="macho_rpath_anomaly",
        severity=Severity.CRITICAL,
        source_fr="FR-04",
    )

    result = score_snapshot(store.snapshot(), default_rules)

    expected = {
        "R-TRIAGE-HIGH-HEURISTIC",
        "R-TRIAGE-SEVERE-PACKING",
        "R-PE-ENTRYPOINT-WX",
        "R-PE-ENTRYPOINT-OOB",
        "R-PE-TLS-CALLBACK-OOB",
        "R-PE-TLS-CALLBACK-WX",
        "R-PE-OVERLAY-EMBEDDED-PE",
        "R-ELF-EXECUTABLE-STACK",
        "R-ELF-WX-LOAD-SEGMENT",
        "R-MACHO-MOD-INIT-FUNC",
        "R-MACHO-RPATH-ANOMALY",
    }
    assert expected <= set(result.matched_rule_ids)
    assert not any("YARA" in rid for rid in result.matched_rule_ids)


def test_binary_commercial_protector_and_behavior_path_rules(default_rules):
    """Protector and behavior-chain facts contribute beyond generic bucket severity."""
    store = new_store("binary-protector-behavior")

    add_fact(
        store,
        Bucket.packer,
        indicator_type="commercial_packer_match",
        severity=Severity.CRITICAL,
        source_fr="FR-05",
        data={"die_type": "protector", "name": "VMProtect"},
    )
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="module_chain_summary",
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor_id(store)],
        source_fr="FR-17",
        data={"end_state": "Persistent backdoor with HTTPS C2."},
    )
    add_inference(
        store,
        Bucket.behavior_chain,
        indicator_type="function_behavior_node",
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor_id(store)],
        source_fr="FR-17",
        data={"capability": "process_injection"},
    )

    result = score_snapshot(store.snapshot(), default_rules)

    assert "R-PACKER-KNOWN" in result.matched_rule_ids
    assert "R-COMMERCIAL-PROTECTOR" in result.matched_rule_ids
    assert "R-BEHAVIOR-MAL-CHAIN" in result.matched_rule_ids
    assert "R-BEHAVIOR-CRITICAL-SUMMARY" in result.matched_rule_ids
    assert "R-BEHAVIOR-CRITICAL-FUNCTION" in result.matched_rule_ids


def test_binary_high_confidence_family_and_threat_class_rules(default_rules):
    """HIGH-confidence FR-08/FR-13 inferences now influence binary scoring."""
    store = new_store("binary-llm-inference-rules")
    anchor = anchor_id(store)

    add_inference(
        store,
        Bucket.llm_inferences,
        indicator_type="family_candidate",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        source_fr="FR-13",
        data={"family": "AgentTesla", "rationale": "SMTP exfil and keylog hooks."},
    )
    add_inference(
        store,
        Bucket.llm_inferences,
        indicator_type="threat_class",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        source_fr="FR-08",
        data={"classes": ["InfoStealer", "RAT"]},
    )

    result = score_snapshot(store.snapshot(), default_rules)

    assert "R-FAMILY-CANDIDATE-HIGH" in result.matched_rule_ids
    assert "R-THREAT-CLASS-HIGH" in result.matched_rule_ids
    assert result.family_name == "AgentTesla"
    assert result.threat_classes == ["InfoStealer", "RAT"]


# ---------------------------------------------------------------------------
# FR-13 AC-4/5: document_role — 4 output paths
# ---------------------------------------------------------------------------


def _build_doc_store_clean() -> EvidenceChainStore:
    """No document indicators → document_role = clean."""
    return new_store("doc-clean")


def _build_doc_store_carrier() -> EvidenceChainStore:
    """Macro sim events only (delivery logic, no embedded PE) → carrier."""
    store = new_store("doc-carrier")
    add_fact(
        store,
        Bucket.macro_analysis,
        indicator_type="macro_action_call",
        severity=Severity.WARNING,
        data={"tag": "command_invocation", "command": "powershell -enc ..."},
    )
    return store


def _build_doc_store_payload_host() -> EvidenceChainStore:
    """Embedded PE, no delivery-logic indicators → payload_host."""
    store = new_store("doc-payload-host")
    add_fact(
        store,
        Bucket.embedded_payloads,
        indicator_type="embedded_ole_object",
        severity=Severity.CRITICAL,
        data={"suggested_format": "pe", "size_bytes": 45056},
    )
    return store


def _build_doc_store_infection_source() -> EvidenceChainStore:
    """Embedded PE + macro delivery-logic → infection_source."""
    store = new_store("doc-infection-source")
    add_fact(
        store,
        Bucket.embedded_payloads,
        indicator_type="embedded_ole_object",
        severity=Severity.CRITICAL,
        data={"suggested_format": "pe", "size_bytes": 45056},
    )
    add_fact(
        store,
        Bucket.macro_analysis,
        indicator_type="macro_action_call",
        severity=Severity.CRITICAL,
        data={"tag": "command_invocation", "command": "wscript.exe payload.vbs"},
    )
    return store


def test_document_role_clean(default_rules):
    """Evidence chain with no document indicators → document_role = clean."""
    store = _build_doc_store_clean()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.document_role == DocumentRole.CLEAN


def test_document_role_carrier(default_rules):
    """Macro delivery-logic indicator (no embedded PE) → document_role = carrier."""
    store = _build_doc_store_carrier()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.document_role == DocumentRole.CARRIER


def test_document_role_payload_host(default_rules):
    """Embedded PE without delivery logic → document_role = payload_host."""
    store = _build_doc_store_payload_host()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.document_role == DocumentRole.PAYLOAD_HOST


def test_document_role_infection_source(default_rules):
    """Embedded PE + macro delivery-logic → document_role = infection_source."""
    store = _build_doc_store_infection_source()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.document_role == DocumentRole.INFECTION_SOURCE


def test_document_extract_office_trigger_scores(default_rules):
    """FR-03 Office trigger facts carry the tag used by document scoring."""
    store = new_store("doc-office-trigger")
    add_fact(
        store,
        Bucket.document_analysis,
        indicator_type="trigger",
        severity=Severity.WARNING,
        data={"type": "AutoOpen", "tag": "auto_trigger", "source": "olevba"},
    )
    result = score_snapshot(store.snapshot(), default_rules)
    assert "R-DOC-VBA-AUTO-TRIGGER" in result.matched_rule_ids
    assert result.document_role == DocumentRole.CARRIER


def test_document_extract_pdf_js_scores(default_rules):
    """FR-03 PDF action-chain facts carry the tag used by PDF JS scoring."""
    store = new_store("doc-pdf-js")
    add_fact(
        store,
        Bucket.document_analysis,
        indicator_type="pdf_action_chain",
        severity=Severity.INFO,
        data={"chain": ["OpenAction", "JavaScript"], "tag": "js_trigger"},
    )
    result = score_snapshot(store.snapshot(), default_rules)
    assert "R-DOC-PDF-JS" in result.matched_rule_ids
    assert result.document_role == DocumentRole.CARRIER


def test_pdf_embedded_pe_scores_payload_host(default_rules):
    """PDF embedded executable payloads are scored like payload-hosting documents."""
    store = new_store("doc-pdf-payload-host")
    add_fact(
        store,
        Bucket.embedded_payloads,
        indicator_type="pdf_embedded_file",
        severity=Severity.WARNING,
        data={"name": "payload.exe", "suggested_format": "pe"},
    )
    result = score_snapshot(store.snapshot(), default_rules)
    assert "R-DOC-PDF-EMBEDDED-PE" in result.matched_rule_ids
    assert result.document_role == DocumentRole.PAYLOAD_HOST


def test_pdf_keyword_summary_scores_exploit_surface(default_rules):
    """PDF keyword summaries expose exploit/phishing surface to scoring."""
    store = new_store("doc-pdf-keywords")
    add_fact(
        store,
        Bucket.document_analysis,
        indicator_type="pdf_keyword_summary",
        severity=Severity.WARNING,
        data={
            "keywords": {"/JBIG2Decode": 1, "/SubmitForm": 1},
            "risk_counts": {"high": 1, "medium": 1, "low": 0},
            "has_jbig2decode": True,
            "has_submit_form": True,
        },
    )
    result = score_snapshot(store.snapshot(), default_rules)
    assert "R-DOC-PDF-JBIG2" in result.matched_rule_ids
    assert "R-DOC-PDF-SUBMITFORM" in result.matched_rule_ids
    assert result.document_role == DocumentRole.CARRIER


def test_pdf_js_shellcode_scores_carrier(default_rules):
    """PDF JavaScript shellcode markers are strong carrier evidence."""
    store = new_store("doc-pdf-shellcode-js")
    add_fact(
        store,
        Bucket.document_analysis,
        indicator_type="pdf_js_analysis",
        severity=Severity.CRITICAL,
        data={
            "markers": {"heap_spray": 1, "eval_call": 1},
            "has_shellcode_markers": True,
            "has_obfuscation_markers": True,
        },
    )
    result = score_snapshot(store.snapshot(), default_rules)
    assert "R-DOC-PDF-SHELLCODE-JS" in result.matched_rule_ids
    assert "R-DOC-PDF-OBFUSCATED-JS" in result.matched_rule_ids
    assert result.document_role == DocumentRole.CARRIER


def test_document_role_none_without_document_namespace(v10_rules):
    """v1.0 rules (no document namespace) → document_role is None."""
    store = _build_doc_store_infection_source()
    result = score_snapshot(store.snapshot(), v10_rules)
    assert result.document_role is None


# ---------------------------------------------------------------------------
# FR-13 AC-6: unknown_downgrade_reason enum migration
# ---------------------------------------------------------------------------


def test_unknown_downgrade_reason_is_enum(default_rules):
    """AC-8 downgrade emits UnknownDowngradeReason enum, not a free string."""
    store = low_confidence.build()
    result = score_snapshot(store.snapshot(), default_rules)
    assert result.verdict_label == VerdictLabel.UNKNOWN
    assert isinstance(result.unknown_downgrade_reason, UnknownDowngradeReason)
    assert result.unknown_downgrade_reason == UnknownDowngradeReason.ALL_LOW_CONFIDENCE


def test_unknown_downgrade_reason_encrypted_office():
    """encrypted_office_no_password is a valid UnknownDowngradeReason value (FR-13 AC-6).

    The value is set externally (e.g. by DocExtractTool) and carried through
    ScoringResult.  This test verifies the enum member exists and that
    ScoringResult accepts it without validation errors.
    """
    # Verify enum member exists
    assert (
        UnknownDowngradeReason.ENCRYPTED_OFFICE_NO_PASSWORD
        == "encrypted_office_no_password"
    )

    # ScoringResult must accept the value
    result = ScoringResult(
        rule_score=0,
        verdict_label=VerdictLabel.UNKNOWN,
        rules_version="1.1.0",
        unknown_downgrade_reason=UnknownDowngradeReason.ENCRYPTED_OFFICE_NO_PASSWORD,
    )
    assert (
        result.unknown_downgrade_reason
        == UnknownDowngradeReason.ENCRYPTED_OFFICE_NO_PASSWORD
    )
    # JSON serialisation produces the string value (StrEnum)
    dumped = result.model_dump(mode="json")
    assert dumped["unknown_downgrade_reason"] == "encrypted_office_no_password"


# ---------------------------------------------------------------------------
# FR-13 AC-7: unknown namespace skipped silently
# ---------------------------------------------------------------------------


def test_unknown_namespace_skipped_silently(tmp_path: Path):
    """A YAML with an unknown top-level namespace loads without error (FR-13 AC-7)."""
    yaml_content = """\
rules_version: "1.1.0"

binary:
  thresholds:
    malicious: 70
    suspicious: 30
    unknown_low_confidence_max: 50
  rules:
    - id: R-ENTROPY-HIGH
      description: High entropy
      bucket: entropy
      weight: 25
      match:
        severity_in: [WARNING, CRITICAL]

future_namespace_v2:
  some_key: some_value
"""
    f = tmp_path / "rules_future.yaml"
    f.write_text(yaml_content, encoding="utf-8")
    # Must not raise even though future_namespace_v2 is unknown
    rules = load_rules(f)
    assert rules.version == "1.1.0"
    assert rules.document is None
    assert len(rules.rules) == 1
