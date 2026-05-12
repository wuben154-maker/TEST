"""Evidence-chain store and LangChain tool (C3).

Public API::

    from evidence_chain import EvidenceChainStore, EvidenceChainTool

``EvidenceChainStore`` — append-only in-memory store (FR-09 AC-8).
``EvidenceChainTool``  — LangChain BaseTool wrapper for Agent consumption (C3-AC5).
"""

from evidence_chain.store import EvidenceChainStore
from evidence_chain.tool import EvidenceChainTool

__all__ = ["EvidenceChainStore", "EvidenceChainTool"]
