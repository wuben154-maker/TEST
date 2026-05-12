"""Assemble the BinaryAnalyst system prompt from ``agent.md``.

``agent.md`` is loaded as a **single continuous template** and passed
through ``str.format`` with five named placeholders:

- ``open_tag`` / ``close_tag`` (from :mod:`prompts.sanitize`)
- ``max_rounds`` / ``token_budget`` / ``threshold_pct`` (from the e2e01
  budget constants below).

All other ``{`` / ``}`` in the markdown — including document-routing set
literals such as ``{{P0, P1, P2}}`` — must be doubled (``{{`` / ``}}``)
so they survive ``str.format`` as literal braces.

The earlier base/patch split (``<!-- system_prompt:document_mode_patch -->``
marker plus ``DOCUMENT_MODE_PROMPT_PATCH`` constant) was removed: the
document-routing rules now live inline in ``§1`` of ``agent.md``, and the
prompt is exposed as a single :data:`BINARY_ANALYST_SYSTEM_PROMPT`.

The e2e01 budget constants pair with :class:`~budget_guards.TokenBudgetGuard`
/ :class:`~budget_guards.RoundBudgetGuard`.  Document-mode defaults
(``DOC_*``) and :data:`TOKEN_BUDGET_HARD_CAP` are defined here for
:func:`~analyst_graph.build_binary_analyst_agent` and recursion
budget (ADR-DOC-03).
"""

from __future__ import annotations

from pathlib import Path

from prompts.sanitize import CLOSE_TAG, OPEN_TAG

# ---------------------------------------------------------------------------
# Binary analysis mode defaults (e2e01 — frozen; do NOT change)
# ---------------------------------------------------------------------------

DEFAULT_MAX_ROUNDS: int = 10
"""NFR-07 default for binary analysis (e2e01): maximum LLM rounds per session."""

DEFAULT_TOKEN_BUDGET: int = 50_000
"""NFR-05 default for binary analysis (e2e01): aggregate token ceiling per session."""

CONVERGENCE_THRESHOLD_RATIO: float = 0.8
"""FR-08 AC-9: fraction of the budget at which the LLM must force-converge."""

# ---------------------------------------------------------------------------
# Document analysis mode defaults (e2e02 — FR-08 AC-2/3, C7)
# ---------------------------------------------------------------------------

DOC_DEFAULT_MAX_ROUNDS: int = 15
"""NFR-07 default for document analysis (e2e02): maximum LLM rounds per session.

Relaxed from the binary-mode default of 10 to accommodate multi-stage
document extraction, VBA simulation, and embedded-payload recursion.
"""

DOC_DEFAULT_TOKEN_BUDGET: int = 80_000
"""NFR-05 default for document analysis (e2e02): aggregate token ceiling.

Relaxed from the binary-mode default of 50_000 to accommodate document
parsing, macro simulation, and multi-round LLM analysis (FR-08 AC-2).
"""

TOKEN_BUDGET_HARD_CAP: int = 120_000
"""FR-08 AC-6: absolute token hard cap for recursive document analysis.

When a depth-2 recursion scenario exhausts the default 80k budget before
the child sample has finished, the system may extend once to this ceiling
(ADR-DOC-03 方案 C — "保子砍父" recursion budget).  Exceeding this cap
triggers a ``BUDGET_EXCEEDED`` short-circuit with
``reason="recursion_budget"`` (FR-08 AC-7).
"""

# ---------------------------------------------------------------------------
# agent.md load: single template, str.format with five placeholders
# ---------------------------------------------------------------------------

_AGENT_MD_PATH: Path = Path(__file__).resolve().parent / "agent.md"

_PROMPT_TEMPLATE: str = _AGENT_MD_PATH.read_text(encoding="utf-8").rstrip("\n")

BINARY_ANALYST_SYSTEM_PROMPT: str = _PROMPT_TEMPLATE.format(
    open_tag=OPEN_TAG,
    close_tag=CLOSE_TAG,
    max_rounds=DEFAULT_MAX_ROUNDS,
    token_budget=DEFAULT_TOKEN_BUDGET,
    threshold_pct=int(CONVERGENCE_THRESHOLD_RATIO * 100),
)
"""Frozen BinaryAnalyst system prompt (agent.md after str.format substitution)."""

__all__ = [
    "BINARY_ANALYST_SYSTEM_PROMPT",
    "CONVERGENCE_THRESHOLD_RATIO",
    "DEFAULT_MAX_ROUNDS",
    "DEFAULT_TOKEN_BUDGET",
    "DOC_DEFAULT_MAX_ROUNDS",
    "DOC_DEFAULT_TOKEN_BUDGET",
    "TOKEN_BUDGET_HARD_CAP",
]
