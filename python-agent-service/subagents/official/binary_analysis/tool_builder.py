"""Canonical BinaryAnalyst LangChain tool list (ADR-13)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from evidence_chain.store import EvidenceChainStore
from evidence_chain.tool import EvidenceChainTool
from sandbox.session_tool import SandboxSessionTool
from tools.bash_tool import BashTool
from tools.decision_gate import DecisionGateTool
from tools.document_extract import DocExtractTool
from tools.file_identify import FileIdentifyTool
from tools.file_read_tool import FileReadTool
from tools.python_exec_tool import PythonExecTool
from tools.report_gen import ReportGenTool
from tools.scoring import ScoringTool

if TYPE_CHECKING:  # pragma: no cover
    from langchain_core.tools import BaseTool

    from sandbox.client import SandboxClient

__all__ = ["build_binary_analyst_tools"]


def build_binary_analyst_tools(
    *,
    store: EvidenceChainStore,
    sandbox_client: SandboxClient | Any,
    rules_path: Path | None = None,
    embedded_payload_handler: Any = None,
    sample_path_resolver: Any = None,
) -> list[BaseTool]:
    """Assemble the canonical 10-tool list for the BinaryAnalyst Agent.

    Tools are ordered to match DESIGN.md §4.1 L2/L3 layering so the
    Agent's introspection of ``tools`` is deterministic:

    1. ``file_identify``    — FR-01 entry gate.
    2. ``evidence_chain``   — FR-09 append-only evidence store.
    3. ``scoring``          — FR-13 rule engine (verdict authority, ADR-04).
    4. ``decision_gate``    — FR-14 escalation recommendation.
    5. ``report_gen``       — FR-15 dual-format report.
    6. ``bash``             — primitive whitelisted CLI execution.
    7. ``python_exec``      — primitive Python snippet execution.
    8. ``file_read``        — primitive artefact read-back.
    9. ``sandbox_session``  — primitive sandbox lifecycle management.
    10. ``document_extract`` — FR-03 document parsing / macro extraction
        (ADR-DOC-10; MUST NOT be called on PE/ELF/Mach-O samples).

    Args:
        store: Shared per-analysis :class:`EvidenceChainStore`.  Every
            store-writing tool (``file_identify``, ``evidence_chain``,
            ``scoring``, ``decision_gate``, ``report_gen``,
            ``document_extract``) receives the same instance so FR-09
            append-only semantics hold.
        sandbox_client: Concrete backend implementing
            :class:`~sandbox.client.SandboxClient`
            (C4 subprocess fallback or C16 E2B backend).
        rules_path: Override for the ``scoring_rules.yaml`` location
            passed to :class:`ScoringTool`.  ``None`` uses the shipped
            default.
        embedded_payload_handler: Optional FR-30 callback injected into
            ``file_identify`` PE carving and ``document_extract`` payload
            materialization.
        sample_path_resolver: Optional app-side resolver that maps SecManus
            `/workspace/...` or `/uploads/...` paths to authorized host upload
            files before sandbox upload. Standalone paths leave this as ``None``.

    Returns:
        A length-10 list of :class:`langchain_core.tools.BaseTool`
        instances in canonical order.
    """
    return [
        FileIdentifyTool(
            sandbox_client=sandbox_client,
            store=store,
            embedded_payload_handler=embedded_payload_handler,
            sample_path_resolver=sample_path_resolver,
        ),
        EvidenceChainTool(store=store),
        ScoringTool(store=store, rules_path=rules_path),
        DecisionGateTool(store=store),
        ReportGenTool(store=store),
        BashTool(sandbox_client=sandbox_client),
        PythonExecTool(sandbox_client=sandbox_client),
        FileReadTool(sandbox_client=sandbox_client),
        SandboxSessionTool(client=sandbox_client),
        DocExtractTool(
            sandbox_client=sandbox_client,
            store=store,
            embedded_payload_handler=embedded_payload_handler,
        ),
    ]
