"""Shared helpers for the constructed evidence-chain fixtures."""

from __future__ import annotations

from typing import Any

from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Indicator, Severity


def new_store(analysis_id: str = "test-analysis") -> EvidenceChainStore:
    """Return a fresh :class:`EvidenceChainStore` seeded with a file_meta anchor.

    Many inference-kind Indicators require at least one ``evidence_ref``; the
    anchor gives builders a stable ID to point at.  The anchor itself is
    emitted with ``kind='fact'`` so it does not consume any rule weight.
    """
    store = EvidenceChainStore(analysis_id=analysis_id)
    anchor = Indicator(
        source_fr="FR-01",
        indicator_type="file_meta",
        severity=Severity.INFO,
        kind="fact",
        data={"fixture_anchor": True},
    )
    store.append(Bucket.file_meta, anchor)
    return store


def add_fact(
    store: EvidenceChainStore,
    bucket: Bucket,
    *,
    indicator_type: str,
    severity: Severity,
    source_fr: str = "FR-13-test",
    confidence: Confidence | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    """Append a ``fact``-kind Indicator to ``bucket`` and return its ID."""
    indicator = Indicator(
        source_fr=source_fr,
        indicator_type=indicator_type,
        severity=severity,
        confidence=confidence,
        kind="fact",
        data=data or {},
    )
    store.append(bucket, indicator)
    return indicator.id


def add_inference(
    store: EvidenceChainStore,
    bucket: Bucket,
    *,
    indicator_type: str,
    severity: Severity,
    confidence: Confidence,
    evidence_refs: list[str],
    source_fr: str = "FR-13-test",
    data: dict[str, Any] | None = None,
) -> str:
    """Append an ``inference``-kind Indicator with required refs set."""
    indicator = Indicator(
        source_fr=source_fr,
        indicator_type=indicator_type,
        severity=severity,
        confidence=confidence,
        kind="inference",
        evidence_refs=evidence_refs,
        data=data or {},
    )
    store.append(bucket, indicator)
    return indicator.id


def anchor_id(store: EvidenceChainStore) -> str:
    """Return the first indicator ID in the ``file_meta`` bucket."""
    snap = store.snapshot()
    return snap.file_meta[0].id
