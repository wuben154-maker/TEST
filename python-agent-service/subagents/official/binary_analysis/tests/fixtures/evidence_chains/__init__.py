"""Constructed evidence-chain fixtures for ScoringTool tests (C11 / FR-13).

The five builder functions in this package return freshly populated
:class:`~evidence_chain.store.EvidenceChainStore` instances
that exercise specific FR-13 acceptance criteria:

- :func:`benign.build`          — no rules fire, expected BENIGN verdict
- :func:`suspicious.build`      — partial rule hits, expected SUSPICIOUS
- :func:`malicious.build`       — full combo fires, expected MALICIOUS
- :func:`combo.build`           — exactly the three COMBO member rules fire,
  used to assert combo bonus weight exceeds the sum of singles (AC-6)
- :func:`low_confidence.build`  — rule hits but every contributing
  Indicator carries ``confidence=LOW``, used to assert AC-8 downgrade
"""

from tests.fixtures.evidence_chains import (
    benign,
    combo,
    low_confidence,
    malicious,
    suspicious,
)

__all__ = [
    "benign",
    "combo",
    "low_confidence",
    "malicious",
    "suspicious",
]
