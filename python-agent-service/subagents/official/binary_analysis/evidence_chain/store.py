"""Append-only in-memory evidence-chain store (FR-09, ADR-02).

All analysis facts and inferences are written to this store via :meth:`append`.
The store enforces the append-only contract required by FR-09 AC-8: once an
Indicator is written its ID is immutable and may never be overwritten, updated,
or deleted.

Callers obtain a read-only view of the accumulated evidence via
:meth:`snapshot`, which returns a frozen :class:`EvidenceChainSnapshot`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from errors import StateCorruption
from schema.evidence_chain import (
    Bucket,
    EvidenceChainSnapshot,
    canonical_bucket_str,
)
from schema.indicator import Indicator, Severity
from schema.indicator_types_v1_1 import (
    DELIVERY_CHAIN_DOC_TYPES,
    DOC_ANALYSIS_TYPES,
    EMBEDDED_PAYLOADS_TYPES,
    MACRO_ANALYSIS_TYPES,
)

# Mapping from v1.1.0 document bucket names → allowed indicator_type frozensets.
# e2e01 buckets are intentionally absent — they are not enum-validated (FR-09 AC-3).
_DOC_BUCKET_ENUM: dict[str, frozenset[str]] = {
    Bucket.document_analysis.value: DOC_ANALYSIS_TYPES,
    Bucket.macro_analysis.value: MACRO_ANALYSIS_TYPES,
    Bucket.embedded_payloads.value: EMBEDDED_PAYLOADS_TYPES,
    Bucket.delivery_chain_doc.value: DELIVERY_CHAIN_DOC_TYPES,
}


class EvidenceChainStore:
    """Append-only in-memory store for evidence-chain Indicators.

    One instance per analysis session.  Thread-safety is not guaranteed; the
    store assumes single-threaded access within a synchronous analysis loop.

    Args:
        analysis_id: The UUID for the current analysis session (used when
            writing snapshot files under the ADR-10 tmpdir convention).
    """

    def __init__(self, analysis_id: str = "") -> None:
        self._analysis_id = analysis_id
        self._buckets: dict[str, list[Indicator]] = {b.value: [] for b in Bucket}
        self._ids: set[str] = set()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, bucket: Bucket | str, indicator: Indicator) -> None:
        """Append an Indicator to the given bucket (append-only contract).

        Args:
            bucket: Target bucket.  Accepts both :class:`Bucket` enum members
                and their string values.
            indicator: The Indicator to store.  Its ``id`` must be unique across
                all buckets in this store.

        Raises:
            StateCorruption: If an Indicator with the same ``id`` already exists
                in any bucket (FR-09 AC-8, ADR-02 append-only red-line).
            ValueError: If ``bucket`` is not a valid :class:`Bucket` value.
        """
        key = (
            bucket.value if isinstance(bucket, Bucket) else canonical_bucket_str(bucket)
        )
        if key not in self._buckets:
            msg = f"unknown bucket '{key}'"
            raise ValueError(msg)
        if indicator.id in self._ids:
            msg = f"Indicator id '{indicator.id}' already exists — append-only contract violated (FR-09 AC-8)"
            raise StateCorruption(
                msg, details={"indicator_id": indicator.id, "bucket": key}
            )
        allowed_types = _DOC_BUCKET_ENUM.get(key)
        if allowed_types is not None and indicator.indicator_type not in allowed_types:
            msg = (
                f"indicator_type not in schema v1.1 enum for bucket {key!r}: "
                f"got {indicator.indicator_type!r}"
            )
            raise ValueError(msg)
        self._buckets[key].append(indicator)
        self._ids.add(indicator.id)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        bucket: Bucket | str | None = None,
        severity: Severity | str | None = None,
        source_fr: str | None = None,
    ) -> list[Indicator]:
        """Return Indicators matching all supplied filter criteria (FR-09 AC-4).

        All filters are combined with logical AND.  Omitting a filter means
        "match any value" for that dimension.

        Args:
            bucket: Restrict results to a single bucket.
            severity: Restrict results to a specific severity level.
            source_fr: Restrict results to Indicators produced by the given FR
                identifier (e.g. ``"FR-04"``).

        Returns:
            Ordered list of matching Indicators (ordered by insertion time
            within each bucket).
        """
        if bucket is not None:
            key = (
                bucket.value
                if isinstance(bucket, Bucket)
                else canonical_bucket_str(bucket)
            )
            candidates: list[Indicator] = list(self._buckets.get(key, []))
        else:
            candidates = [ind for inds in self._buckets.values() for ind in inds]

        sev_str = severity.value if isinstance(severity, Severity) else severity
        if sev_str is not None:
            candidates = [i for i in candidates if i.severity.value == sev_str]
        if source_fr is not None:
            candidates = [i for i in candidates if i.source_fr == source_fr]
        return candidates

    def ancestors(self, indicator_id: str) -> list[Indicator]:
        """Recursively collect all Indicators reachable via ``derived_from`` (FR-09 AC-5, IR-12).

        Performs a breadth-first traversal of the ``derived_from`` graph
        starting from the Indicator identified by ``indicator_id``.  The
        originating Indicator itself is **not** included in the result.

        Args:
            indicator_id: ID of the Indicator whose ancestry to resolve.

        Returns:
            Flat list of ancestor Indicators in BFS order (closest ancestors
            first).  Empty list if ``indicator_id`` has no ``derived_from``
            references or does not exist.
        """
        index = self._build_index()
        result: list[Indicator] = []
        visited: set[str] = {indicator_id}
        queue: list[str] = (
            list(index[indicator_id].derived_from) if indicator_id in index else []
        )
        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            if current_id in index:
                result.append(index[current_id])
                queue.extend(
                    ref for ref in index[current_id].derived_from if ref not in visited
                )
        return result

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> EvidenceChainSnapshot:
        """Return a frozen read-only snapshot of the current evidence chain (FR-09 AC-8).

        The returned :class:`EvidenceChainSnapshot` is immutable
        (``model_config = {"frozen": True}``).  Callers MUST NOT mutate it.

        Returns:
            A frozen snapshot of all buckets at the moment of the call.
        """
        return EvidenceChainSnapshot(
            **{key: list(indicators) for key, indicators in self._buckets.items()}
        )

    def snapshot_to(self, path: Path | str) -> None:
        """Serialise the evidence chain to a JSON file (FR-09 AC-7, ADR-10).

        The file is written atomically via a temporary write-then-rename to
        avoid partial reads by concurrent consumers.

        Per ADR-10 the expected path convention is::

            <tmp_root>/deepagent-analyze-<analysis_id>/evidence.json

        This method does not enforce the naming convention; it is the
        caller's responsibility to supply the correct path.

        Args:
            path: Destination file path.  Parent directories must already exist.
        """
        snap = self.snapshot()
        dest = Path(path)
        payload: dict[str, Any] = snap.model_dump(mode="json")
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(dest)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_index(self) -> dict[str, Indicator]:
        """Build a flat id → Indicator lookup across all buckets."""
        return {ind.id: ind for inds in self._buckets.values() for ind in inds}
