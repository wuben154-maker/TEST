"""Unit tests for binary_analysis.schema.indicator.

FR-09 AC-2: Indicator mandatory fields (id / source_fr / indicator_type /
            severity / confidence / created_at / data).
FR-09 AC-3: fact vs inference enforcement (ADR-03).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schema.indicator import (
    Confidence,
    Indicator,
    Severity,
    new_indicator_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fact(**overrides: object) -> dict:
    """Return a minimal valid fact Indicator payload."""
    base: dict = {
        "source_fr": "FR-04",
        "indicator_type": "pe_header",
        "severity": Severity.INFO,
        "confidence": Confidence.HIGH,
        "kind": "fact",
        "data": {"key": "value"},
    }
    base.update(overrides)
    return base


def _inference(**overrides: object) -> dict:
    """Return a minimal valid inference Indicator payload."""
    base: dict = {
        "source_fr": "FR-08",
        "indicator_type": "behavior_inference",
        "severity": Severity.WARNING,
        "confidence": Confidence.MEDIUM,
        "kind": "inference",
        "evidence_refs": ["01J0000000000000000000001"],
        "data": {"summary": "suspicious"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# FR-09 AC-2: mandatory fields
# ---------------------------------------------------------------------------


class TestIndicatorMandatoryFields:
    def test_fact_minimal_valid(self) -> None:
        ind = Indicator.model_validate(_fact())
        assert ind.source_fr == "FR-04"
        assert ind.indicator_type == "pe_header"
        assert ind.severity == Severity.INFO
        assert ind.confidence == Confidence.HIGH
        assert ind.kind == "fact"
        assert isinstance(ind.data, dict)

    def test_id_auto_generated(self) -> None:
        ind = Indicator.model_validate(_fact())
        assert ind.id  # non-empty string
        assert len(ind.id) == 26  # ULID length

    def test_created_at_auto_generated(self) -> None:
        ind = Indicator.model_validate(_fact())
        assert ind.created_at is not None

    def test_severity_info(self) -> None:
        ind = Indicator.model_validate(_fact(severity=Severity.INFO))
        assert ind.severity == Severity.INFO

    def test_severity_warning(self) -> None:
        ind = Indicator.model_validate(_fact(severity=Severity.WARNING))
        assert ind.severity == Severity.WARNING

    def test_severity_critical(self) -> None:
        ind = Indicator.model_validate(_fact(severity=Severity.CRITICAL))
        assert ind.severity == Severity.CRITICAL

    def test_severity_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            Indicator.model_validate(_fact(severity="UNKNOWN_LEVEL"))

    def test_missing_source_fr_raises(self) -> None:
        payload = _fact()
        del payload["source_fr"]
        with pytest.raises(ValidationError):
            Indicator.model_validate(payload)

    def test_missing_indicator_type_raises(self) -> None:
        payload = _fact()
        del payload["indicator_type"]
        with pytest.raises(ValidationError):
            Indicator.model_validate(payload)

    def test_missing_severity_raises(self) -> None:
        payload = _fact()
        del payload["severity"]
        with pytest.raises(ValidationError):
            Indicator.model_validate(payload)

    def test_missing_kind_raises(self) -> None:
        payload = _fact()
        del payload["kind"]
        with pytest.raises(ValidationError):
            Indicator.model_validate(payload)

    def test_missing_data_raises(self) -> None:
        payload = _fact()
        del payload["data"]
        with pytest.raises(ValidationError):
            Indicator.model_validate(payload)


# ---------------------------------------------------------------------------
# FR-09 AC-3: fact vs inference (ADR-03)
# ---------------------------------------------------------------------------


class TestFactVsInference:
    def test_fact_no_evidence_refs_required(self) -> None:
        ind = Indicator.model_validate(_fact())
        assert ind.evidence_refs == []

    def test_inference_valid(self) -> None:
        ind = Indicator.model_validate(_inference())
        assert ind.kind == "inference"
        assert ind.confidence is not None
        assert len(ind.evidence_refs) >= 1

    def test_inference_missing_confidence_raises(self) -> None:
        """inference without confidence must raise."""
        payload = _inference()
        payload["confidence"] = None
        with pytest.raises(ValidationError):
            Indicator.model_validate(payload)

    def test_inference_empty_evidence_refs_raises(self) -> None:
        """inference with empty evidence_refs must raise."""
        payload = _inference(evidence_refs=[])
        with pytest.raises(ValidationError):
            Indicator.model_validate(payload)

    def test_confidence_levels(self) -> None:
        for level in (Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW):
            ind = Indicator.model_validate(_inference(confidence=level))
            assert ind.confidence == level

    def test_derived_from_optional(self) -> None:
        ind = Indicator.model_validate(
            _inference(derived_from=["01J0000000000000000000000"])
        )
        assert "01J0000000000000000000000" in ind.derived_from

    def test_kind_invalid_literal_raises(self) -> None:
        with pytest.raises(ValidationError):
            Indicator.model_validate(_fact(kind="unknown"))


# ---------------------------------------------------------------------------
# ULID helper
# ---------------------------------------------------------------------------


class TestNewIndicatorId:
    def test_returns_26_char_string(self) -> None:
        uid = new_indicator_id()
        assert isinstance(uid, str)
        assert len(uid) == 26

    def test_unique(self) -> None:
        ids = {new_indicator_id() for _ in range(100)}
        assert len(ids) == 100
