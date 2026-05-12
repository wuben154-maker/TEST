"""COMBO fixture for FR-13 AC-6 multi-source correlation.

Triggers exactly the three member rules of COMBO-PACKED-DROPPER:
- R-ENTROPY-HIGH     (25)
- R-IMPORTS-SPARSE   (15)
- R-ANTIDEBUG-STRING (20)

Sum of singles == 60.  Combo bonus == 25.  Expected total == 85.

Used by :mod:`tests.unit_tests.tools.test_scoring` to assert that the
combined weight strictly exceeds the sum of the member rules in isolation
(FR-13 AC-6 red-line).
"""

from __future__ import annotations

from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Severity
from tests.fixtures.evidence_chains._helpers import add_fact, new_store


def build(analysis_id: str = "combo-analysis") -> EvidenceChainStore:
    """Return a store triggering exactly the three combo-member rules."""
    store = new_store(analysis_id=analysis_id)
    add_fact(
        store,
        Bucket.entropy,
        indicator_type="entropy_section",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"section": ".text", "entropy": 7.65},
    )
    add_fact(
        store,
        Bucket.imports,
        indicator_type="imports_sparse",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"import_count": 5},
    )
    add_fact(
        store,
        Bucket.strings_iocs,
        indicator_type="anti_debug_string",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"string": "IsDebuggerPresent"},
    )
    return store
