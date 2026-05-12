"""EvidenceChainTool — LangChain tool wrapping the evidence-chain store (C3-AC5).

The tool exposes three actions to the Agent:

- ``append``   — write one Indicator to a bucket (FR-09 AC-8 append-only).
- ``query``    — filter Indicators by bucket / severity / source_fr (FR-09 AC-4).
- ``snapshot`` — serialise the full chain to the ADR-10 tmpdir (FR-09 AC-7).

All three actions share one Pydantic input schema so that the LangChain /
LangGraph tool-calling layer can validate inputs before they reach the store.

Usage::

    store = EvidenceChainStore(analysis_id="<uuid>")
    tool  = EvidenceChainTool(store=store)

    # append a fact Indicator
    tool.invoke({
        "action": "append",
        "bucket": "file_meta",
        "indicator": {
            "source_fr": "FR-04",
            "indicator_type": "pe_header",
            "severity": "INFO",
            "kind": "fact",
            "data": {"machine": "AMD64"},
        },
    })

    # query by bucket
    tool.invoke({"action": "query", "bucket": "file_meta"})

    # snapshot to tmpdir
    tool.invoke({
        "action": "snapshot",
        "snapshot_path": "/tmp/deepagent-analyze-<uuid>/evidence.json",
    })
"""

from __future__ import annotations

import json
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Final, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator, model_validator

from schema.evidence_chain import (
    BUCKET_NAMES,
    Bucket,
    canonical_bucket_str,
    parse_bucket,
)
from schema.indicator import Confidence, Indicator, Severity
from schema.indicator_types_v1_1 import (
    DELIVERY_CHAIN_DOC_TYPES,
    DOC_ANALYSIS_TYPES,
    EMBEDDED_PAYLOADS_TYPES,
    MACRO_ANALYSIS_TYPES,
)

from .store import EvidenceChainStore

# ---------------------------------------------------------------------------
# Bucket validation helpers
# ---------------------------------------------------------------------------

_CROSS_BUCKET_CONVENTIONS: Final[dict[str, str]] = {
    # Names that LLMs occasionally pass as `bucket` but are actually
    # `indicator_type` values — cross-bucket conventions surfaced by the
    # skill `binary-analysis-evidence-chain-protocol`.
    "analysis_coverage": (
        "'analysis_coverage' is an indicator_type, NOT a bucket. It is a "
        "cross-bucket convention: append the Indicator with "
        "indicator_type='analysis_coverage' into the most-relevant domain "
        "bucket instead — e.g. 'disassembly' for FR-07/FR-17 skips, "
        "'behavior_chain' for behavior-chain skips, 'strings_iocs' for "
        "FLOSS downgrades or document-parser-fallback strings paths, 'triage' "
        "for triage-level downgrades, or 'llm_inferences' for LLM-driven "
        "downgrades. Never use v1.1 document buckets ('document_analysis', "
        "'macro_analysis', 'embedded_payloads', 'delivery_chain_doc'): their "
        "indicator_type values are schema-enumerated only (IR-DOC-02)."
    ),
    "audit_gaps": (
        "'audit_gaps' is a cross-bucket convention filled by the Python "
        "audit layer (tool failures, schema rejects, budget warnings), NOT "
        "a bucket the Agent writes to. If you need to record an issue, "
        "write an Indicator into the stage's domain bucket or into "
        "'llm_inferences' with an appropriate indicator_type."
    ),
}

_DOC_BUCKET_ENUM: Final[dict[str, frozenset[str]]] = {
    Bucket.document_analysis.value: DOC_ANALYSIS_TYPES,
    Bucket.macro_analysis.value: MACRO_ANALYSIS_TYPES,
    Bucket.embedded_payloads.value: EMBEDDED_PAYLOADS_TYPES,
    Bucket.delivery_chain_doc.value: DELIVERY_CHAIN_DOC_TYPES,
}

_ANALYSIS_COVERAGE_DIMENSION_BUCKETS: Final[dict[str, str]] = {
    "structure": Bucket.headers.value,
    "entropy": Bucket.entropy.value,
    "strings": Bucket.strings_iocs.value,
    "decompilation": Bucket.disassembly.value,
    "behavior_chain": Bucket.behavior_chain.value,
    "llm_inferences": Bucket.llm_inferences.value,
}


def _validate_bucket_value(raw: str) -> None:
    """Validate a bucket string passed by the Agent.

    Accepts any canonical :class:`Bucket` value or the legacy alias
    ``"packing"`` (mapped to ``"packer"`` via
    :func:`canonical_bucket_str`).  Raises ``ValueError`` with a
    remediation hint when the value is a known cross-bucket convention
    (``"analysis_coverage"`` / ``"audit_gaps"``) or an unknown bucket
    name — pydantic wraps this into a ``ValidationError`` so LangGraph's
    ``ToolNode`` returns the message as a recoverable tool error instead
    of aborting the run.
    """
    canonical = canonical_bucket_str(raw)
    if canonical in BUCKET_NAMES:
        return
    hint = _CROSS_BUCKET_CONVENTIONS.get(raw)
    if hint is None:
        hint = (
            f"'{raw}' is not a valid bucket. Valid buckets: {', '.join(BUCKET_NAMES)}."
        )
    raise ValueError(hint)


def _document_indicator_type_error(
    bucket: Bucket, indicator_type: str
) -> dict[str, Any] | None:
    """Return a recoverable schema error for invalid v1.1 document types."""
    allowed_types = _DOC_BUCKET_ENUM.get(bucket.value)
    if allowed_types is None or indicator_type in allowed_types:
        return None

    sorted_allowed = sorted(allowed_types)
    matches = get_close_matches(indicator_type, sorted_allowed, n=1, cutoff=0.72)
    suggestion = matches[0] if matches else None
    message = (
        f"indicator_type {indicator_type!r} is not allowed for bucket "
        f"{bucket.value!r}. Use one of: {', '.join(sorted_allowed)}."
    )
    if suggestion is not None:
        message += f" Did you mean {suggestion!r}?"

    details: dict[str, Any] = {
        "bucket": bucket.value,
        "indicator_type": indicator_type,
        "allowed_indicator_types": sorted_allowed,
    }
    if suggestion is not None:
        details["suggested_indicator_type"] = suggestion

    return {
        "ok": False,
        "error_code": "TOOL_SCHEMA_INVALID",
        "reason": "document_indicator_type_not_allowed",
        "message": message,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


class _IndicatorPayload(BaseModel):
    """Partial Indicator payload supplied by the Agent.

    ``id`` is optional — when omitted the :class:`Indicator` auto-generates a
    ULID (IR-12 uniqueness guarantee).  ``created_at`` is always auto-populated
    and cannot be overridden by the Agent.
    """

    id: str | None = None
    source_fr: str
    indicator_type: str
    severity: Severity
    confidence: Confidence | None = None
    kind: Literal["fact", "inference"]
    evidence_refs: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data", mode="before")
    @classmethod
    def _coerce_data_from_json_string(cls, value: Any) -> Any:
        """Accept ``data`` as either a JSON object or a JSON-encoded string.

        Some LLM providers (notably Gemini, occasionally Claude / GPT under
        strict JSON-mode) serialise nested ``object`` fields as JSON
        *strings* when emitting tool calls — ``data`` is the worst offender
        because its shape is free-form (``dict[str, Any]``). Strict
        Pydantic v2 validation rejects those with
        ``indicator.data: Input should be a valid dictionary``, aborting
        the tool call.

        This validator loosens that single coercion point: if the LLM
        passes ``data`` as a string that parses to a JSON object, we
        accept it; any other shape (``None``, bare list, non-JSON string)
        still raises a clear error.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return {}
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                msg = (
                    "indicator.data was provided as a string but is not "
                    f"valid JSON: {exc.msg}. Pass the data as a JSON "
                    'object (e.g. {"key": "value"}), not a quoted '
                    "string."
                )
                raise ValueError(msg) from exc
            if not isinstance(parsed, dict):
                msg = (
                    "indicator.data string decoded to a "
                    f"{type(parsed).__name__}, but a JSON object is "
                    "required. Pass the data as a JSON object "
                    '(e.g. {"key": "value"}).'
                )
                raise ValueError(msg)
            return parsed
        return value

    @model_validator(mode="after")
    def _normalize_analysis_coverage_data(self) -> _IndicatorPayload:
        """Normalize legacy LLM coverage markers into reportable fields."""
        if self.indicator_type != "analysis_coverage":
            return self

        data = dict(self.data)
        legacy_reason = data.get("analysis_coverage")
        if "reason" not in data and isinstance(legacy_reason, str) and legacy_reason:
            data["reason"] = legacy_reason
        if "dimension" not in data:
            dimension = _infer_analysis_coverage_dimension(self)
            if dimension is not None:
                data["dimension"] = dimension
        if "status" not in data and data.get("reason"):
            data["status"] = "DEGRADED"
        self.data = data
        return self


def _infer_analysis_coverage_dimension(indicator: _IndicatorPayload) -> str | None:
    """Infer a coverage dimension for common downgrade payloads."""
    raw_dimension = indicator.data.get("dimension")
    if isinstance(raw_dimension, str) and raw_dimension.strip():
        return raw_dimension.strip()

    raw_reason = indicator.data.get("reason", indicator.data.get("analysis_coverage", ""))
    reason = raw_reason.casefold() if isinstance(raw_reason, str) else ""
    if indicator.source_fr == "FR-03":
        return "strings"
    if "parser" in reason or "peepdf" in reason or "extraction" in reason:
        return "strings"
    return None


def _infer_missing_append_bucket(indicator: _IndicatorPayload) -> str | None:
    """Infer only high-confidence cross-bucket convention routes."""
    if indicator.indicator_type != "analysis_coverage":
        return None
    dimension = _infer_analysis_coverage_dimension(indicator)
    if dimension is None:
        return None
    return _ANALYSIS_COVERAGE_DIMENSION_BUCKETS.get(dimension)


class EvidenceChainInput(BaseModel):
    """Unified input schema for all EvidenceChainTool actions.

    Exactly one of ``indicator`` / ``snapshot_path`` is expected depending on
    ``action``; the :meth:`_validate_action_fields` validator enforces this at
    parse time so the tool body can assume valid input.
    """

    action: Literal["append", "query", "snapshot"]
    bucket: str | None = None
    severity: str | None = None
    source_fr: str | None = None
    indicator: _IndicatorPayload | None = None
    snapshot_path: str | None = None

    @model_validator(mode="after")
    def _validate_action_fields(self) -> EvidenceChainInput:
        """Enforce per-action required fields."""
        if self.action == "append":
            if self.indicator is None:
                msg = "action='append' requires 'indicator'"
                raise ValueError(msg)
            if self.bucket is None:
                self.bucket = _infer_missing_append_bucket(self.indicator)
            if self.bucket is None:
                msg = "action='append' requires 'bucket'"
                raise ValueError(msg)
            _validate_bucket_value(self.bucket)
        if self.action == "query" and self.bucket is not None:
            _validate_bucket_value(self.bucket)
        if self.action == "snapshot" and self.snapshot_path is None:
            msg = "action='snapshot' requires 'snapshot_path'"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class EvidenceChainTool(BaseTool):
    """LangChain tool for reading and writing the evidence chain (FR-09, ADR-02).

    The tool wraps an :class:`EvidenceChainStore` instance and enforces the
    append-only contract on behalf of the Agent.

    Args:
        store: The shared evidence-chain store for the current analysis session.
    """

    name: str = "evidence_chain"
    description: str = (
        "Manage the binary-analysis evidence chain. "
        "Actions: "
        "'append' — write one Indicator to a named bucket; "
        "'query'  — filter Indicators by bucket/severity/source_fr; "
        "'snapshot' — serialise the full evidence chain to a JSON file. "
        "IMPORTANT: `indicator.data` MUST be a JSON object "
        '(e.g. {"key": "value"}), NOT a JSON-encoded string. '
        'Do NOT wrap it in quotes — `"data": "{\\"k\\": 1}"` is wrong, '
        '`"data": {"k": 1}` is correct. A stringified payload will still '
        "be accepted via best-effort decoding, but emit it as an object "
        "to avoid unnecessary validation round-trips. "
        "CRITICAL FOR DOCUMENT MODE: 4 buckets (`document_analysis`, "
        "`macro_analysis`, `embedded_payloads`, `delivery_chain_doc`) enforce "
        "strict v1.1 `indicator_type` enum from `schema/indicator_types_v1_1.py`. "
        "Use `document_parser_failed` for parser failures; "
        "`document_parser_failure` is not valid. "
        "`analysis_coverage` is a cross-bucket indicator_type — write it to "
        "`strings_iocs` or `llm_inferences` instead. See SKILL.md 'Schema "
        "Compliance Rules' for full whitelist and examples. Violating this "
        "returns a recoverable schema error with the allowed values."
    )
    args_schema: type[BaseModel] = EvidenceChainInput
    store: EvidenceChainStore

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> Any:  # type: ignore[override]
        """Dispatch to the appropriate store method based on ``action``.

        Args:
            **kwargs: Keyword arguments matching :class:`EvidenceChainInput`.

        Returns:
            Action-specific result (see individual handler docs).
        """
        inp = EvidenceChainInput(**kwargs)
        if inp.action == "append":
            return self._handle_append(inp)
        if inp.action == "query":
            return self._handle_query(inp)
        return self._handle_snapshot(inp)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _handle_append(self, inp: EvidenceChainInput) -> dict[str, Any]:
        """Append a new Indicator to the store.

        Returns:
            Mapping with ``ok=True`` and the assigned Indicator ``id``.
        """
        assert inp.indicator is not None  # validated by schema  # noqa: S101
        assert inp.bucket is not None  # validated by schema  # noqa: S101
        payload = inp.indicator.model_dump(exclude_none=False)
        if payload.get("id") is None:
            del payload["id"]
        indicator = Indicator(**payload)
        bucket = parse_bucket(inp.bucket)
        type_error = _document_indicator_type_error(bucket, indicator.indicator_type)
        if type_error is not None:
            return type_error
        self.store.append(bucket, indicator)
        return {"ok": True, "id": indicator.id}

    def _handle_query(self, inp: EvidenceChainInput) -> dict[str, Any]:
        """Query Indicators from the store.

        Returns:
            Mapping with ``ok=True`` and a ``results`` list of serialised
            Indicators.
        """
        results = self.store.query(
            bucket=inp.bucket,
            severity=inp.severity,
            source_fr=inp.source_fr,
        )
        return {
            "ok": True,
            "results": [json.loads(ind.model_dump_json()) for ind in results],
        }

    def _handle_snapshot(self, inp: EvidenceChainInput) -> dict[str, Any]:
        """Serialise the full evidence chain to a JSON file.

        The parent directory of ``snapshot_path`` must already exist.

        Returns:
            Mapping with ``ok=True`` and the resolved ``path``.
        """
        assert inp.snapshot_path is not None  # validated by schema  # noqa: S101
        dest = Path(inp.snapshot_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.store.snapshot_to(dest)
        return {"ok": True, "path": str(dest)}
