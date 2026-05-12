"""Unit tests for binary_analysis.schema.report.

FR-09 AC-6 / FR-15 AC-2: schema_version written to final report (bumped to 1.1.0 in C1).
FR-15 AC-1: JSON report structure (all top-level fields present).
FR-15 AC-3: v1.1.0 Optional document fields present with None / False defaults.
FR-15 AC-4: JSON schema semantic versioning.
FR-09 AC-5: e2e01 minimal report payload loads without error after v1.1.0 bump.
C11 / FR-15 AC-4: MARKDOWN_SECTIONS contains the 3 new document section keys.
"""

from __future__ import annotations

import re

from schema.document_enums import (
    DocumentFormat,
    DocumentRole,
    DocumentTier,
    UnknownDowngradeReason,
)
from schema.report import (
    MARKDOWN_SECTIONS,
    AnalysisCoverage,
    CoverageStatus,
    EscalationLevel,
    EscalationRecommendation,
    ReportV1,
    Verdict,
    VerdictLabel,
)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_TOP_LEVEL_FIELDS = {
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


def _minimal_report() -> dict:
    """Return the minimum payload needed to instantiate a valid ReportV1."""
    return {
        "file_meta": {
            "file_name": "sample.exe",
            "file_size": 1024,
            "file_type": "PE32",
            "architecture": "x86",
            "analysis_id": "01J0000000000000000000001",
        },
        "fingerprints": {
            "sha256": "a" * 64,
            "md5": "b" * 32,
            "sha1": "c" * 40,
        },
        "verdict": {"label": VerdictLabel.UNKNOWN, "rule_score": 0.0},
        "risk_score": {"score": 0, "rule_version": "1.0.0"},
        "threat_class": {"classes": []},
        "malware_family": {"name": "Unknown Family", "confidence": "LOW"},
        "evidence_chain": {},
        "behavior_chain": {"nodes": [], "edges": []},
        "escalation_recommendation": {"level": EscalationLevel.NONE, "reasons": []},
        "analysis_coverage": {
            "dimensions": {
                "structure": CoverageStatus.COMPLETED,
                "entropy": CoverageStatus.COMPLETED,
                "strings": CoverageStatus.COMPLETED,
                "decompilation": CoverageStatus.SKIPPED,
                "behavior_chain": CoverageStatus.SKIPPED,
                "llm_inferences": CoverageStatus.COMPLETED,
            },
            "gaps": [],
        },
    }


# ---------------------------------------------------------------------------
# FR-09 AC-6: schema_version
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_default_schema_version_is_1_1_0(self) -> None:
        """FR-15 AC-2 / FR-09 AC-5: schema_version default bumped to 1.1.0 in C1."""
        report = ReportV1.model_validate(_minimal_report())
        assert report.schema_version == "1.1.0"

    def test_schema_version_in_json_dump(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        dumped = report.model_dump(mode="json")
        assert dumped["schema_version"] == "1.1.0"


# ---------------------------------------------------------------------------
# FR-15 AC-1: all top-level fields present in model_dump
# ---------------------------------------------------------------------------


class TestReportTopLevelFields:
    def test_all_required_fields_present(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        dumped = report.model_dump(mode="json")
        missing = _REQUIRED_TOP_LEVEL_FIELDS - set(dumped.keys())
        assert not missing, f"Missing top-level fields: {missing}"

    def test_file_meta_fields(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert report.file_meta.file_name == "sample.exe"
        assert report.file_meta.file_size == 1024

    def test_fingerprints_sha256(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert len(report.fingerprints.sha256) == 64

    def test_verdict_unknown(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert report.verdict.label == VerdictLabel.UNKNOWN

    def test_risk_score_range(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert 0 <= report.risk_score.score <= 100

    def test_behavior_chain_structure(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert isinstance(report.behavior_chain.nodes, list)
        assert isinstance(report.behavior_chain.edges, list)

    def test_escalation_none(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert report.escalation_recommendation.level == EscalationLevel.NONE

    def test_analysis_coverage_structure(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert isinstance(report.analysis_coverage.dimensions, dict)

    def test_evidence_chain_is_snapshot(self) -> None:
        from schema.evidence_chain import EvidenceChainSnapshot

        report = ReportV1.model_validate(_minimal_report())
        assert isinstance(report.evidence_chain, EvidenceChainSnapshot)


# ---------------------------------------------------------------------------
# FR-15 AC-4: JSON schema semantic versioning
# ---------------------------------------------------------------------------


class TestJsonSchemaExport:
    def test_model_json_schema_succeeds(self) -> None:
        schema = ReportV1.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_schema_version_field_exists_in_json_schema(self) -> None:
        schema = ReportV1.model_json_schema()
        props = schema.get("properties", {})
        assert "schema_version" in props

    def test_schema_version_pattern_semver(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert SEMVER_RE.match(report.schema_version), (
            f"schema_version '{report.schema_version}' does not match SemVer"
        )

    def test_schema_version_regex_validation(self) -> None:
        """schema_version field must reject non-SemVer strings."""
        import pytest
        from pydantic import ValidationError

        bad_payload = _minimal_report()
        bad_payload["schema_version"] = "v1.0"
        with pytest.raises(ValidationError):
            ReportV1.model_validate(bad_payload)


# ---------------------------------------------------------------------------
# Sub-model smoke tests
# ---------------------------------------------------------------------------


class TestSubModels:
    def test_verdict_labels(self) -> None:
        for label in (
            VerdictLabel.MALICIOUS,
            VerdictLabel.SUSPICIOUS,
            VerdictLabel.BENIGN,
            VerdictLabel.UNKNOWN,
        ):
            v = Verdict(label=label, rule_score=50.0)
            assert v.label == label

    def test_escalation_levels(self) -> None:
        for level in (
            EscalationLevel.NONE,
            EscalationLevel.SANDBOX,
            EscalationLevel.MANUAL_REVERSE,
        ):
            rec = EscalationRecommendation(level=level, reasons=[])
            assert rec.level == level

    def test_coverage_statuses(self) -> None:
        for status in (
            CoverageStatus.COMPLETED,
            CoverageStatus.DEGRADED,
            CoverageStatus.SKIPPED,
        ):
            cov = AnalysisCoverage(
                dimensions={"structure": status},
                gaps=[],
            )
            assert cov.dimensions["structure"] == status


# ---------------------------------------------------------------------------
# FR-15 AC-3: v1.1.0 Optional document fields
# ---------------------------------------------------------------------------


class TestReportV1DocumentFields:
    """C1 / FR-15 AC-3: all 9 new Optional document fields have correct defaults."""

    def test_optional_doc_fields_default_to_none(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert report.document_format is None
        assert report.document_tier is None
        assert report.document_role is None
        assert report.unknown_downgrade_reason is None
        assert report.document_analysis is None
        assert report.macro_analysis is None
        assert report.embedded_payloads is None
        assert report.delivery_chain_doc is None

    def test_doc_analysis_partial_defaults_to_false(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert report.doc_analysis_partial is False

    def test_document_format_field_accepts_enum(self) -> None:
        payload = _minimal_report()
        payload["document_format"] = "pdf"
        report = ReportV1.model_validate(payload)
        assert report.document_format == DocumentFormat.PDF

    def test_document_tier_field_accepts_enum(self) -> None:
        payload = _minimal_report()
        payload["document_tier"] = "P0"
        report = ReportV1.model_validate(payload)
        assert report.document_tier == DocumentTier.P0

    def test_document_role_field_accepts_enum(self) -> None:
        payload = _minimal_report()
        payload["document_role"] = "carrier"
        report = ReportV1.model_validate(payload)
        assert report.document_role == DocumentRole.CARRIER

    def test_unknown_downgrade_reason_accepts_enum(self) -> None:
        payload = _minimal_report()
        payload["unknown_downgrade_reason"] = "all_low_confidence"
        report = ReportV1.model_validate(payload)
        assert (
            report.unknown_downgrade_reason == UnknownDowngradeReason.ALL_LOW_CONFIDENCE
        )

    def test_doc_analysis_partial_can_be_true(self) -> None:
        payload = _minimal_report()
        payload["doc_analysis_partial"] = True
        report = ReportV1.model_validate(payload)
        assert report.doc_analysis_partial is True

    def test_document_analysis_dict_field(self) -> None:
        payload = _minimal_report()
        payload["document_analysis"] = {"ole_structure": "ok"}
        report = ReportV1.model_validate(payload)
        assert report.document_analysis == {"ole_structure": "ok"}

    def test_embedded_payloads_list_field(self) -> None:
        payload = _minimal_report()
        payload["embedded_payloads"] = [{"sha256": "a" * 64, "type": "PE32"}]
        report = ReportV1.model_validate(payload)
        assert isinstance(report.embedded_payloads, list)
        assert len(report.embedded_payloads) == 1

    def test_new_fields_present_in_json_dump(self) -> None:
        """All v1.1.0 fields must appear in model_dump even when None."""
        report = ReportV1.model_validate(_minimal_report())
        dumped = report.model_dump(mode="json")
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
        missing = v1_1_fields - set(dumped.keys())
        assert not missing, f"Missing v1.1.0 fields in JSON dump: {missing}"


# ---------------------------------------------------------------------------
# FR-09 AC-5: e2e01 backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """e2e01 minimal report payload must load without error against v1.1.0 schema."""

    def test_e2e01_minimal_payload_loads(self) -> None:
        """A payload that omits all v1.1.0 Optional fields must validate cleanly."""
        report = ReportV1.model_validate(_minimal_report())
        assert report.schema_version == "1.1.0"
        assert report.document_format is None
        assert report.document_role is None

    def test_explicit_schema_version_override_allowed(self) -> None:
        """Callers may supply an explicit schema_version that differs from the default."""
        payload = _minimal_report()
        payload["schema_version"] = "1.0.0"
        report = ReportV1.model_validate(payload)
        assert report.schema_version == "1.0.0"

    def test_schema_version_1_1_0_is_semver(self) -> None:
        report = ReportV1.model_validate(_minimal_report())
        assert SEMVER_RE.match(report.schema_version)


# ---------------------------------------------------------------------------
# C11 / FR-15 AC-4: MARKDOWN_SECTIONS carries the 3 new document chapter keys
# ---------------------------------------------------------------------------


class TestMarkdownSectionsC11:
    """C11: MARKDOWN_SECTIONS must include the 3 new v1.1.0 document section keys
    in the correct insertion order (after structural_anomalies, before escalation).
    """

    _NEW_DOC_KEYS = (
        "delivery_chain",
        "macro_and_embedded_script",
        "embedded_payloads_list",
    )

    def test_new_section_keys_present(self) -> None:
        for key in self._NEW_DOC_KEYS:
            assert key in MARKDOWN_SECTIONS, f"MARKDOWN_SECTIONS missing key: {key!r}"

    def test_new_section_headings_are_chinese(self) -> None:
        assert MARKDOWN_SECTIONS["delivery_chain"] == "投递链"
        assert MARKDOWN_SECTIONS["macro_and_embedded_script"] == "宏与嵌入脚本分析"
        assert MARKDOWN_SECTIONS["embedded_payloads_list"] == "嵌入载荷清单"

    def test_new_keys_ordered_after_structural_anomalies_before_escalation(
        self,
    ) -> None:
        keys = list(MARKDOWN_SECTIONS.keys())
        idx_structural = keys.index("structural_anomalies")
        idx_escalation = keys.index("escalation")
        for key in self._NEW_DOC_KEYS:
            idx = keys.index(key)
            assert idx_structural < idx < idx_escalation, (
                f"Key {key!r} must be between structural_anomalies and escalation, "
                f"but found at position {idx} (structural={idx_structural}, escalation={idx_escalation})"
            )

    def test_total_sections_count(self) -> None:
        assert len(MARKDOWN_SECTIONS) == 13, (
            f"Expected 13 sections (10 base + 3 document), got {len(MARKDOWN_SECTIONS)}"
        )
