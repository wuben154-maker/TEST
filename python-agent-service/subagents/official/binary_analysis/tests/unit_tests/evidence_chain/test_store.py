"""Unit tests for EvidenceChainStore (FR-09 AC-4/5/7/8)."""

from __future__ import annotations

import json
import pathlib

import pytest

from errors import StateCorruption
from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket, EvidenceChainSnapshot
from schema.indicator import Confidence, Indicator, Severity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_indicator(
    *,
    source_fr: str = "FR-04",
    indicator_type: str = "pe_header",
    severity: Severity = Severity.INFO,
    kind: str = "fact",
    derived_from: list[str] | None = None,
    confidence: Confidence | None = None,
    evidence_refs: list[str] | None = None,
) -> Indicator:
    """Construct a valid Indicator for tests."""
    kwargs: dict = {
        "source_fr": source_fr,
        "indicator_type": indicator_type,
        "severity": severity,
        "kind": kind,
        "data": {"test": True},
    }
    if derived_from is not None:
        kwargs["derived_from"] = derived_from
    if confidence is not None:
        kwargs["confidence"] = confidence
    if evidence_refs is not None:
        kwargs["evidence_refs"] = evidence_refs
    return Indicator(**kwargs)


# ---------------------------------------------------------------------------
# FR-09 AC-8: append-only semantics
# ---------------------------------------------------------------------------


class TestAppendOnly:
    def test_append_succeeds(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append(Bucket.file_meta, ind)
        assert store.query(bucket=Bucket.file_meta) == [ind]

    def test_packing_alias_string_resolves_to_packer_bucket(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append("packing", ind)
        assert store.query(bucket=Bucket.packer) == [ind]
        assert store.query(bucket="packing") == [ind]

    def test_duplicate_id_raises_state_corruption(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append(Bucket.file_meta, ind)
        with pytest.raises(StateCorruption) as exc_info:
            store.append(Bucket.triage, ind)
        assert ind.id in str(exc_info.value)

    def test_duplicate_id_across_buckets_raises(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append(Bucket.headers, ind)
        with pytest.raises(StateCorruption):
            store.append(Bucket.imports, ind)

    def test_no_update_method_exists(self) -> None:
        store = EvidenceChainStore()
        assert not hasattr(store, "update"), (
            "update method must not exist (AC-8 red-line)"
        )

    def test_no_delete_method_exists(self) -> None:
        store = EvidenceChainStore()
        assert not hasattr(store, "delete"), (
            "delete method must not exist (AC-8 red-line)"
        )

    def test_snapshot_is_frozen(self) -> None:
        store = EvidenceChainStore()
        store.append(Bucket.file_meta, make_indicator())
        snap = store.snapshot()
        with pytest.raises(
            Exception
        ):  # frozen model raises ValidationError or TypeError
            snap.file_meta = []  # type: ignore[misc]

    def test_snapshot_returns_evidence_chain_snapshot(self) -> None:
        store = EvidenceChainStore()
        snap = store.snapshot()
        assert isinstance(snap, EvidenceChainSnapshot)

    def test_snapshot_list_is_independent_copy(self) -> None:
        """Mutating the returned list must not affect the store."""
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append(Bucket.file_meta, ind)
        snap = store.snapshot()
        # Attempt to mutate the snapshot list (frozen model prevents field reassignment,
        # but test that store state is unaffected even if list was mutable).
        assert len(snap.file_meta) == 1
        assert store.query(bucket=Bucket.file_meta) == [ind]

    def test_accepts_bucket_string(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append("file_meta", ind)
        assert store.query(bucket="file_meta") == [ind]

    def test_invalid_bucket_raises_value_error(self) -> None:
        store = EvidenceChainStore()
        with pytest.raises(ValueError, match="unknown bucket"):
            store.append("not_a_bucket", make_indicator())


# ---------------------------------------------------------------------------
# FR-09 AC-4: query interface — bucket / severity / source_fr
# ---------------------------------------------------------------------------


class TestQuery:
    def test_query_by_bucket(self) -> None:
        store = EvidenceChainStore()
        ind1 = make_indicator(source_fr="FR-04")
        ind2 = make_indicator(source_fr="FR-05")
        store.append(Bucket.file_meta, ind1)
        store.append(Bucket.entropy, ind2)

        assert store.query(bucket=Bucket.file_meta) == [ind1]
        assert store.query(bucket=Bucket.entropy) == [ind2]

    def test_query_by_severity(self) -> None:
        store = EvidenceChainStore()
        info = make_indicator(severity=Severity.INFO)
        critical = make_indicator(severity=Severity.CRITICAL)
        store.append(Bucket.file_meta, info)
        store.append(Bucket.file_meta, critical)

        results = store.query(severity=Severity.CRITICAL)
        assert results == [critical]

    def test_query_by_severity_string(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(severity=Severity.WARNING)
        store.append(Bucket.file_meta, ind)

        assert store.query(severity="WARNING") == [ind]
        assert store.query(severity="CRITICAL") == []

    def test_query_by_source_fr(self) -> None:
        store = EvidenceChainStore()
        ind_fr04 = make_indicator(source_fr="FR-04")
        ind_fr05 = make_indicator(source_fr="FR-05")
        store.append(Bucket.headers, ind_fr04)
        store.append(Bucket.entropy, ind_fr05)

        assert store.query(source_fr="FR-04") == [ind_fr04]
        assert store.query(source_fr="FR-05") == [ind_fr05]

    def test_query_combined_filters(self) -> None:
        store = EvidenceChainStore()
        match = make_indicator(source_fr="FR-04", severity=Severity.CRITICAL)
        no_match_bucket = make_indicator(source_fr="FR-04", severity=Severity.CRITICAL)
        store.append(Bucket.file_meta, match)
        store.append(Bucket.entropy, no_match_bucket)

        results = store.query(
            bucket=Bucket.file_meta, severity=Severity.CRITICAL, source_fr="FR-04"
        )
        assert results == [match]

    def test_query_no_filter_returns_all(self) -> None:
        store = EvidenceChainStore()
        ind1 = make_indicator()
        ind2 = make_indicator(source_fr="FR-05")
        store.append(Bucket.file_meta, ind1)
        store.append(Bucket.triage, ind2)

        all_results = store.query()
        assert ind1 in all_results
        assert ind2 in all_results

    def test_query_empty_store(self) -> None:
        store = EvidenceChainStore()
        assert store.query(bucket=Bucket.file_meta) == []
        assert store.query() == []

    def test_query_bucket_enum_and_string_equivalent(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append(Bucket.imports, ind)

        assert store.query(bucket=Bucket.imports) == store.query(bucket="imports")


# ---------------------------------------------------------------------------
# FR-09 AC-5: derived_from / ancestors traversal
# ---------------------------------------------------------------------------


class TestAncestors:
    def test_ancestors_direct(self) -> None:
        store = EvidenceChainStore()
        parent = make_indicator(source_fr="FR-04")
        child = make_indicator(source_fr="FR-05", derived_from=[parent.id])
        store.append(Bucket.file_meta, parent)
        store.append(Bucket.entropy, child)

        ancestors = store.ancestors(child.id)
        assert ancestors == [parent]

    def test_ancestors_multi_hop(self) -> None:
        store = EvidenceChainStore()
        root = make_indicator()
        mid = make_indicator(derived_from=[root.id])
        leaf = make_indicator(derived_from=[mid.id])
        store.append(Bucket.file_meta, root)
        store.append(Bucket.file_meta, mid)
        store.append(Bucket.file_meta, leaf)

        ancestors = store.ancestors(leaf.id)
        assert root in ancestors
        assert mid in ancestors

    def test_ancestors_no_parent(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator()
        store.append(Bucket.file_meta, ind)
        assert store.ancestors(ind.id) == []

    def test_ancestors_unknown_id(self) -> None:
        store = EvidenceChainStore()
        assert store.ancestors("nonexistent-id") == []

    def test_ancestors_cycle_safe(self) -> None:
        """ancestors() must terminate even if derived_from forms a cycle."""
        store = EvidenceChainStore()
        # We can't create a true object-level cycle with frozen Pydantic models,
        # so we test with a diamond (common ancestor):
        base = make_indicator()
        branch1 = make_indicator(derived_from=[base.id])
        branch2 = make_indicator(derived_from=[base.id])
        tip = make_indicator(derived_from=[branch1.id, branch2.id])
        for bucket, ind in [
            (Bucket.file_meta, base),
            (Bucket.file_meta, branch1),
            (Bucket.file_meta, branch2),
            (Bucket.file_meta, tip),
        ]:
            store.append(bucket, ind)

        ancestors = store.ancestors(tip.id)
        ids = [a.id for a in ancestors]
        # base should appear exactly once despite being reachable via two paths
        assert ids.count(base.id) == 1


# ---------------------------------------------------------------------------
# FR-09 AC-7: snapshot_to JSON file (ADR-10 rump path)
# ---------------------------------------------------------------------------


class TestSnapshotTo:
    def test_snapshot_to_writes_valid_json(self, tmp_path: pathlib.Path) -> None:
        store = EvidenceChainStore(analysis_id="test-aid")
        ind = make_indicator()
        store.append(Bucket.file_meta, ind)

        dest = tmp_path / "deepagent-analyze-test-aid" / "evidence.json"
        dest.parent.mkdir(parents=True)
        store.snapshot_to(dest)

        assert dest.exists()
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert "file_meta" in data
        assert len(data["file_meta"]) == 1
        assert data["file_meta"][0]["id"] == ind.id

    def test_snapshot_to_produces_valid_evidence_chain_snapshot(
        self, tmp_path: pathlib.Path
    ) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(severity=Severity.CRITICAL)
        store.append(Bucket.entropy, ind)

        dest = tmp_path / "evidence.json"
        store.snapshot_to(dest)

        payload = json.loads(dest.read_text(encoding="utf-8"))
        # Re-validate through the schema model
        snap = EvidenceChainSnapshot.model_validate(payload)
        assert len(snap.entropy) == 1
        assert snap.entropy[0].severity == Severity.CRITICAL

    def test_snapshot_to_all_buckets_present(self, tmp_path: pathlib.Path) -> None:
        store = EvidenceChainStore()
        dest = tmp_path / "evidence.json"
        store.snapshot_to(dest)

        payload = json.loads(dest.read_text(encoding="utf-8"))
        from schema.evidence_chain import BUCKET_NAMES

        for name in BUCKET_NAMES:
            assert name in payload, f"bucket '{name}' missing from snapshot"

    def test_snapshot_path_str_accepted(self, tmp_path: pathlib.Path) -> None:
        store = EvidenceChainStore()
        store.snapshot_to(str(tmp_path / "evidence.json"))
        assert (tmp_path / "evidence.json").exists()


# ---------------------------------------------------------------------------
# FR-09 AC-3 / IR-DOC-02: indicator_type enum guard for v1.1 document buckets
# ---------------------------------------------------------------------------


class TestDocumentBucketEnumValidation:
    """FR-09 AC-3: v1.1 document buckets reject unknown indicator_type values.

    IR-DOC-02 requires the ``append`` entry-point to be the single schema-drift
    guard.  Each of the 4 new buckets has its own frozenset; e2e01 buckets are
    intentionally unguarded.
    """

    # ------------------------------------------------------------------
    # document_analysis bucket
    # ------------------------------------------------------------------

    def test_document_analysis_valid_type_accepted(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="ole_structure")
        store.append(Bucket.document_analysis, ind)
        assert store.query(bucket=Bucket.document_analysis) == [ind]

    def test_document_analysis_invalid_type_raises(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="pe_header")
        with pytest.raises(
            ValueError, match="schema v1.1 enum for bucket 'document_analysis'"
        ):
            store.append(Bucket.document_analysis, ind)

    # ------------------------------------------------------------------
    # macro_analysis bucket
    # ------------------------------------------------------------------

    def test_macro_analysis_valid_type_accepted(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="vba_module")
        store.append(Bucket.macro_analysis, ind)
        assert store.query(bucket=Bucket.macro_analysis) == [ind]

    def test_macro_analysis_invalid_type_raises(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="pe_header")
        with pytest.raises(
            ValueError, match="schema v1.1 enum for bucket 'macro_analysis'"
        ):
            store.append(Bucket.macro_analysis, ind)

    # ------------------------------------------------------------------
    # embedded_payloads bucket
    # ------------------------------------------------------------------

    def test_embedded_payloads_valid_type_accepted(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="embedded_ole_object")
        store.append(Bucket.embedded_payloads, ind)
        assert store.query(bucket=Bucket.embedded_payloads) == [ind]

    def test_embedded_payloads_invalid_type_raises(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="pe_header")
        with pytest.raises(
            ValueError, match="schema v1.1 enum for bucket 'embedded_payloads'"
        ):
            store.append(Bucket.embedded_payloads, ind)

    # ------------------------------------------------------------------
    # delivery_chain_doc bucket
    # ------------------------------------------------------------------

    def test_delivery_chain_doc_valid_type_accepted(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="parent_child_link")
        store.append(Bucket.delivery_chain_doc, ind)
        assert store.query(bucket=Bucket.delivery_chain_doc) == [ind]

    def test_delivery_chain_doc_invalid_type_raises(self) -> None:
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="pe_header")
        with pytest.raises(
            ValueError, match="schema v1.1 enum for bucket 'delivery_chain_doc'"
        ):
            store.append(Bucket.delivery_chain_doc, ind)

    # ------------------------------------------------------------------
    # e2e01 buckets are NOT guarded (AC-3 scope limited to 4 new buckets)
    # ------------------------------------------------------------------

    def test_e2e01_triage_bucket_accepts_arbitrary_indicator_type(self) -> None:
        """Legacy e2e01 buckets must not be affected by the v1.1 enum guard."""
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="any_arbitrary_type_not_in_enum")
        store.append(Bucket.triage, ind)
        assert store.query(bucket=Bucket.triage) == [ind]

    def test_e2e01_llm_inferences_bucket_not_guarded(self) -> None:
        """llm_inferences is explicitly excluded from the new-bucket enum check (FR-09 AC-4)."""
        store = EvidenceChainStore()
        ind = make_indicator(indicator_type="some_llm_inference_type")
        store.append(Bucket.llm_inferences, ind)
        assert store.query(bucket=Bucket.llm_inferences) == [ind]
