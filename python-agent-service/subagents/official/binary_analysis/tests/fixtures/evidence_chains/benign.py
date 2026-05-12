"""BENIGN evidence-chain fixture (FR-13 AC-1 / AC-2 lower band).

Contains only structural facts that do not match any scoring rule:
- file_meta anchor (kind=fact, INFO)
- entropy observation at INFO severity (does NOT trigger R-ENTROPY-HIGH
  because the rule requires WARNING/CRITICAL)
- benign import observation without the ``imports_sparse`` indicator_type

Expected :func:`score_snapshot` output:
    rule_score == 0
    verdict_label == BENIGN
"""

from __future__ import annotations

from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Severity
from tests.fixtures.evidence_chains._helpers import add_fact, new_store


def build(analysis_id: str = "benign-analysis") -> EvidenceChainStore:
    """Return a populated store that should score 0 / BENIGN."""
    store = new_store(analysis_id=analysis_id)
    add_fact(
        store,
        Bucket.entropy,
        indicator_type="entropy_section",
        severity=Severity.INFO,
        data={"section": ".text", "entropy": 5.1},
    )
    add_fact(
        store,
        Bucket.imports,
        indicator_type="imports_enumerated",
        severity=Severity.INFO,
        data={"imported_dlls": ["KERNEL32.dll", "USER32.dll"], "count": 42},
    )
    return store
