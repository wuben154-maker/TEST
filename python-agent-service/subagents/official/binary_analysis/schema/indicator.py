"""Indicator schema — the atomic evidence unit in the evidence chain.

Each Indicator represents a single observation or inference written to one
evidence-chain bucket.  The schema is frozen at v1.0.0 (C2); only additive
optional fields are allowed in future batches (NFR-12 SemVer).

ADR-02: every Tool output is normalised into Indicator records.
ADR-03: `kind` separates tool-produced facts from LLM-produced inferences;
        inference Indicators MUST carry a non-null confidence and at least one
        evidence_ref.
IR-12:  Indicator IDs are globally unique; generated via ULID.
NFR-11: Confidence calibration — HIGH ≥ 90 %, MEDIUM ≥ 70 %, LOW ≥ 50 %.
"""

from __future__ import annotations

import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from ulid import ULID


class Severity(StrEnum):
    """Threat severity level for an Indicator."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Confidence(StrEnum):
    """Confidence calibration level (NFR-11).

    Semantics:
    - HIGH   — derived directly from tool facts or cross-validated by multiple sources.
    - MEDIUM — LLM inference with corroborating evidence.
    - LOW    — LLM inference without corroborating evidence.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def new_indicator_id() -> str:
    """Generate a globally unique Indicator ID (ULID, 26 characters)."""
    return str(ULID())


class Indicator(BaseModel):
    """Atomic evidence record written to an evidence-chain bucket.

    Fields marked as required have no default; they must be supplied by the
    caller (Tool or LLM layer).  `id` and `created_at` are auto-populated when
    omitted so that callers can construct Indicators without managing IDs.

    Args:
        id: Globally unique ULID identifier (IR-12).  Auto-generated if omitted.
        source_fr: Functional-requirement identifier that produced this record
            (e.g. ``"FR-04"``).
        indicator_type: Domain label describing the observation
            (e.g. ``"pe_header"``, ``"entropy_spike"``).
        severity: Threat severity level (INFO / WARNING / CRITICAL).
        confidence: Confidence calibration level (HIGH / MEDIUM / LOW).
            Required for ``inference`` kind; optional for ``fact``.
        kind: ``"fact"`` for tool-produced observations; ``"inference"`` for
            LLM-produced conclusions (ADR-03).
        evidence_refs: List of Indicator IDs that support this record.
            Required to be non-empty when ``kind == "inference"`` (ADR-03).
        derived_from: Optional list of Indicator IDs from which this record
            was derived (supports reasoning-chain traversal, IR-12).
        created_at: UTC timestamp.  Auto-populated to ``datetime.now(UTC)``
            when omitted.
        data: Arbitrary structured payload produced by the originating Tool or
            LLM.  Content schema is bucket-specific and defined in IMPL-GUIDE.
    """

    id: str = Field(default_factory=new_indicator_id)
    source_fr: str
    indicator_type: str
    severity: Severity
    confidence: Confidence | None = None
    kind: Literal["fact", "inference"]
    evidence_refs: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
    )
    data: dict[str, Any]

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _enforce_inference_rules(self) -> Indicator:
        """Enforce ADR-03 constraints for inference-kind Indicators."""
        if self.kind == "inference":
            if self.confidence is None:
                msg = "inference Indicator must have a non-null confidence level"
                raise ValueError(msg)
            if not self.evidence_refs:
                msg = "inference Indicator must reference at least one evidence ID"
                raise ValueError(msg)
        return self
