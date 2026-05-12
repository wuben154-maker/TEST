"""Unit tests for EvidenceChainTool (C3-AC5, FR-09 AC-4/7/8)."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from errors import StateCorruption
from evidence_chain.store import EvidenceChainStore
from evidence_chain.tool import EvidenceChainInput, EvidenceChainTool
from schema.evidence_chain import Bucket

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store() -> EvidenceChainStore:
    return EvidenceChainStore(analysis_id="test-aid")


@pytest.fixture()
def tool(store: EvidenceChainStore) -> EvidenceChainTool:
    return EvidenceChainTool(store=store)


def _fact_payload(
    *,
    source_fr: str = "FR-04",
    indicator_type: str = "pe_header",
    severity: str = "INFO",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_fr": source_fr,
        "indicator_type": indicator_type,
        "severity": severity,
        "kind": "fact",
        "data": data or {"test": True},
    }


def _inference_payload(
    *,
    source_fr: str = "FR-08",
    evidence_id: str = "01ARZ3NDEKTSV4RRFFQ69G5FAV",
) -> dict[str, Any]:
    return {
        "source_fr": source_fr,
        "indicator_type": "behavior_inference",
        "severity": "WARNING",
        "kind": "inference",
        "confidence": "MEDIUM",
        "evidence_refs": [evidence_id],
        "data": {"summary": "suspicious"},
    }


# ---------------------------------------------------------------------------
# C3-AC5: tool.name and schema correctness
# ---------------------------------------------------------------------------


class TestToolSchema:
    def test_tool_name(self, tool: EvidenceChainTool) -> None:
        assert tool.name == "evidence_chain"

    def test_args_schema_is_evidence_chain_input(self, tool: EvidenceChainTool) -> None:
        assert tool.args_schema is EvidenceChainInput

    def test_schema_append_requires_bucket(self) -> None:
        with pytest.raises(Exception):
            EvidenceChainInput(action="append", indicator=_fact_payload())  # type: ignore[arg-type]

    def test_schema_infers_analysis_coverage_bucket_for_fr03_strings_fallback(
        self,
    ) -> None:
        inp = EvidenceChainInput(
            action="append",
            indicator=_fact_payload(
                source_fr="FR-03",
                indicator_type="analysis_coverage",
                data={
                    "dimension": "strings",
                    "status": "DEGRADED",
                    "reason": "peepdf parser failed during extraction",
                },
            ),  # type: ignore[arg-type]
        )

        assert inp.bucket == "strings_iocs"

    def test_schema_append_requires_indicator(self) -> None:
        with pytest.raises(Exception):
            EvidenceChainInput(action="append", bucket="file_meta")

    def test_schema_snapshot_requires_path(self) -> None:
        with pytest.raises(Exception):
            EvidenceChainInput(action="snapshot")

    def test_schema_query_no_required_extra_fields(self) -> None:
        inp = EvidenceChainInput(action="query")
        assert inp.bucket is None
        assert inp.severity is None
        assert inp.source_fr is None

    def test_schema_rejects_analysis_coverage_as_bucket(self) -> None:
        """`analysis_coverage` is an indicator_type, not a bucket.

        Regression guard: LLMs conflate the cross-bucket ``analysis_coverage``
        Indicator convention with a bucket name.  Before this guard a raw
        ``ValueError`` escaped the tool body and crashed the whole LangGraph
        run (see worker traceback ``ValueError: 'analysis_coverage' is not a
        valid Bucket``).  We now raise a pydantic ``ValidationError`` with a
        remediation hint so ``ToolNode`` surfaces it as a recoverable tool
        error and the Agent can self-correct on the next round.
        """
        with pytest.raises(Exception, match="indicator_type"):
            EvidenceChainInput(
                action="append",
                bucket="analysis_coverage",
                indicator=_fact_payload(),  # type: ignore[arg-type]
            )

    def test_schema_rejects_audit_gaps_as_bucket(self) -> None:
        """`audit_gaps` is filled by the audit layer, not the Agent."""
        with pytest.raises(Exception, match="audit layer"):
            EvidenceChainInput(
                action="append",
                bucket="audit_gaps",
                indicator=_fact_payload(),  # type: ignore[arg-type]
            )

    def test_schema_rejects_unknown_bucket_with_valid_list(self) -> None:
        """Unknown bucket names list the valid bucket set for remediation."""
        with pytest.raises(Exception, match="Valid buckets"):
            EvidenceChainInput(
                action="append",
                bucket="totally_made_up",
                indicator=_fact_payload(),  # type: ignore[arg-type]
            )

    def test_schema_query_rejects_unknown_bucket(self) -> None:
        """`query` with an invalid bucket also fails fast."""
        with pytest.raises(Exception, match="Valid buckets"):
            EvidenceChainInput(action="query", bucket="nope")

    def test_schema_query_accepts_missing_bucket(self) -> None:
        """`query` with no bucket means 'match any bucket' — still valid."""
        inp = EvidenceChainInput(action="query")
        assert inp.bucket is None


# ---------------------------------------------------------------------------
# C3-AC5 / FR-09 AC-8: append action
# ---------------------------------------------------------------------------


class TestAppendAction:
    def test_append_fact_indicator(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        result = tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(),
            }
        )
        assert result["ok"] is True
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 26  # ULID length

    def test_append_stores_indicator(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(source_fr="FR-04"),
            }
        )
        indicators = store.query(bucket=Bucket.file_meta)
        assert len(indicators) == 1
        assert indicators[0].source_fr == "FR-04"

    def test_append_accepts_packing_bucket_alias(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        tool.invoke(
            {
                "action": "append",
                "bucket": "packing",
                "indicator": _fact_payload(source_fr="FR-05"),
            }
        )
        assert len(store.query(bucket=Bucket.packer)) == 1
        assert store.query(bucket="packing") == store.query(bucket=Bucket.packer)

    def test_append_duplicate_raises_state_corruption(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        """Same store + same Indicator ID must raise StateCorruption."""
        from schema.indicator import Indicator

        # append once via store directly to get a known ID
        ind = Indicator(**_fact_payload())  # type: ignore[arg-type]
        store.append(Bucket.file_meta, ind)

        # now try to append same ID via tool by injecting it into payload dict
        payload = _fact_payload()
        payload["id"] = ind.id  # type: ignore[assignment]
        with pytest.raises(StateCorruption):
            tool.invoke(
                {
                    "action": "append",
                    "bucket": "triage",
                    "indicator": payload,
                }
            )

    def test_append_inference_indicator(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        # First append a fact to reference
        fact_result = tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(),
            }
        )
        fact_id: str = fact_result["id"]

        result = tool.invoke(
            {
                "action": "append",
                "bucket": "llm_inferences",
                "indicator": _inference_payload(evidence_id=fact_id),
            }
        )
        assert result["ok"] is True

    def test_append_accepts_data_as_json_string(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        """LLMs sometimes emit `data` as a JSON-encoded string; coerce it.

        Regression guard: prior to the ``_coerce_data_from_json_string``
        validator, Gemini / Claude occasionally serialised `data` as
        ``"{\"arch\": \"x64\"}"`` instead of ``{"arch": "x64"}``, which
        broke the FR-01 append with
        ``indicator.data: Input should be a valid dictionary``.
        """
        payload = _fact_payload()
        payload["data"] = json.dumps({"arch": "x64", "format": "PE32+"})
        result = tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": payload,
            }
        )
        assert result["ok"] is True
        stored = store.query(bucket=Bucket.file_meta)[0]
        assert stored.data == {"arch": "x64", "format": "PE32+"}

    def test_append_empty_json_string_data(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        """An empty / whitespace string coerces to an empty dict."""
        payload = _fact_payload()
        payload["data"] = "   "
        result = tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": payload,
            }
        )
        assert result["ok"] is True
        assert store.query(bucket=Bucket.file_meta)[0].data == {}

    def test_append_invalid_document_indicator_type_returns_schema_error(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        """LLM slips in protected document buckets must not abort the run."""
        payload = _fact_payload(
            source_fr="FR-03",
            indicator_type="document_parser_failure",
            severity="WARNING",
        )
        result = tool.invoke(
            {
                "action": "append",
                "bucket": "document_analysis",
                "indicator": payload,
            }
        )

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "document_indicator_type_not_allowed"
        assert result["details"]["suggested_indicator_type"] == "document_parser_failed"
        assert store.query(bucket=Bucket.document_analysis) == []

    def test_append_valid_document_parser_failed_indicator(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        payload = _fact_payload(
            source_fr="FR-03",
            indicator_type="document_parser_failed",
            severity="WARNING",
        )
        result = tool.invoke(
            {
                "action": "append",
                "bucket": "document_analysis",
                "indicator": payload,
            }
        )

        assert result["ok"] is True
        assert store.query(bucket=Bucket.document_analysis)[0].indicator_type == (
            "document_parser_failed"
        )

    def test_append_analysis_coverage_without_bucket_routes_to_strings_iocs(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        result = tool.invoke(
            {
                "action": "append",
                "indicator": _fact_payload(
                    source_fr="FR-03",
                    indicator_type="analysis_coverage",
                    data={
                        "dimension": "strings",
                        "status": "DEGRADED",
                        "reason": "peepdf parser failed during extraction",
                    },
                ),
            }
        )

        assert result["ok"] is True
        stored = store.query(bucket=Bucket.strings_iocs)
        assert len(stored) == 1
        assert stored[0].indicator_type == "analysis_coverage"

    def test_append_legacy_analysis_coverage_payload_is_normalized(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        result = tool.invoke(
            {
                "action": "append",
                "indicator": {
                    "source_fr": "FR-03",
                    "indicator_type": "analysis_coverage",
                    "severity": "INFO",
                    "kind": "fact",
                    "confidence": "HIGH",
                    "evidence_refs": ["workspace/sample.bin"],
                    "derived_from": ["01KQENJ6RG36V6Z9ZFYW18S2S2"],
                    "data": {
                        "analysis_coverage": "peepdf parser failed during extraction"
                    },
                },
            }
        )

        assert result["ok"] is True
        stored = store.query(bucket=Bucket.strings_iocs)[0]
        assert stored.data["dimension"] == "strings"
        assert stored.data["status"] == "DEGRADED"
        assert stored.data["reason"] == "peepdf parser failed during extraction"

    def test_append_rejects_non_object_json_string(self) -> None:
        """JSON that decodes to a non-object (list, scalar) is rejected."""
        payload = _fact_payload()
        payload["data"] = "[1, 2, 3]"
        with pytest.raises(Exception, match="JSON object"):
            EvidenceChainInput(
                action="append",
                bucket="file_meta",
                indicator=payload,  # type: ignore[arg-type]
            )

    def test_append_rejects_invalid_json_string(self) -> None:
        """Unparseable strings surface a clear ValueError."""
        payload = _fact_payload()
        payload["data"] = "not json at all"
        with pytest.raises(Exception, match="valid JSON"):
            EvidenceChainInput(
                action="append",
                bucket="file_meta",
                indicator=payload,  # type: ignore[arg-type]
            )

    def test_append_with_derived_from(
        self, tool: EvidenceChainTool, store: EvidenceChainStore
    ) -> None:
        parent_result = tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(source_fr="FR-04"),
            }
        )
        parent_id: str = parent_result["id"]

        child_payload = _fact_payload(source_fr="FR-05")
        child_payload["derived_from"] = [parent_id]  # type: ignore[assignment]
        tool.invoke(
            {
                "action": "append",
                "bucket": "entropy",
                "indicator": child_payload,
            }
        )

        # ancestors traversal works
        child = store.query(bucket=Bucket.entropy)[0]
        ancestors = store.ancestors(child.id)
        assert any(a.id == parent_id for a in ancestors)


# ---------------------------------------------------------------------------
# C3-AC5 / FR-09 AC-4: query action
# ---------------------------------------------------------------------------


class TestQueryAction:
    def test_query_returns_ok_and_results(self, tool: EvidenceChainTool) -> None:
        tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(source_fr="FR-04"),
            }
        )
        result = tool.invoke({"action": "query", "bucket": "file_meta"})
        assert result["ok"] is True
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 1

    def test_query_by_severity(self, tool: EvidenceChainTool) -> None:
        tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(severity="CRITICAL"),
            }
        )
        tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(severity="INFO"),
            }
        )
        result = tool.invoke({"action": "query", "severity": "CRITICAL"})
        assert len(result["results"]) == 1
        assert result["results"][0]["severity"] == "CRITICAL"

    def test_query_by_source_fr(self, tool: EvidenceChainTool) -> None:
        tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(source_fr="FR-04"),
            }
        )
        tool.invoke(
            {
                "action": "append",
                "bucket": "entropy",
                "indicator": _fact_payload(source_fr="FR-05"),
            }
        )
        result = tool.invoke({"action": "query", "source_fr": "FR-04"})
        assert len(result["results"]) == 1
        assert result["results"][0]["source_fr"] == "FR-04"

    def test_query_results_are_json_serialisable(self, tool: EvidenceChainTool) -> None:
        tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(),
            }
        )
        result = tool.invoke({"action": "query"})
        # Must be able to round-trip through JSON
        json.dumps(result)

    def test_query_empty(self, tool: EvidenceChainTool) -> None:
        result = tool.invoke({"action": "query", "bucket": "file_meta"})
        assert result["ok"] is True
        assert result["results"] == []


# ---------------------------------------------------------------------------
# C3-AC5 / FR-09 AC-7: snapshot action
# ---------------------------------------------------------------------------


class TestSnapshotAction:
    def test_snapshot_creates_file(
        self, tool: EvidenceChainTool, tmp_path: pathlib.Path
    ) -> None:
        dest = tmp_path / "deepagent-analyze-test-aid" / "evidence.json"
        result = tool.invoke(
            {
                "action": "snapshot",
                "snapshot_path": str(dest),
            }
        )
        assert result["ok"] is True
        assert dest.exists()

    def test_snapshot_file_contains_valid_json(
        self, tool: EvidenceChainTool, tmp_path: pathlib.Path
    ) -> None:
        tool.invoke(
            {
                "action": "append",
                "bucket": "file_meta",
                "indicator": _fact_payload(source_fr="FR-01"),
            }
        )
        dest = tmp_path / "evidence.json"
        tool.invoke({"action": "snapshot", "snapshot_path": str(dest)})

        data = json.loads(dest.read_text(encoding="utf-8"))
        assert "file_meta" in data
        assert data["file_meta"][0]["source_fr"] == "FR-01"

    def test_snapshot_creates_parent_dirs(
        self, tool: EvidenceChainTool, tmp_path: pathlib.Path
    ) -> None:
        dest = tmp_path / "deep" / "nested" / "evidence.json"
        result = tool.invoke(
            {
                "action": "snapshot",
                "snapshot_path": str(dest),
            }
        )
        assert result["ok"] is True
        assert dest.exists()
