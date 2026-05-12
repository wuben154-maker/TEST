"""Middleware that injects the FR-15 report target + host/sandbox boundary.

Context:

* :func:`binary_analysis.api._build_initial_prompt` tells the CLI agent a
  concrete host directory for ``report_gen.output_dir``. The LangGraph
  dev / UI entrypoint (:mod:`langgraph_entry`) does not
  run through that helper — the first user message is whatever the
  analyst types in deep-agents-ui, which never mentions ``output_dir``.
* Without that hint the LLM tends to reuse the sandbox-path convention
  it saw for sample / artefact access (``/workspace/<analysis_id>/…``)
  and passes a **sandbox** path to :class:`ReportGenTool`. But
  :class:`ReportGenTool` writes via :mod:`pathlib` on the **host**, and
  :class:`FileReadTool` only downloads from the sandbox — so the
  follow-up ``file_read`` on the freshly-written report raises
  :class:`e2b.exceptions.FileNotFoundException`.

This middleware plugs that gap for the dev path only. On every
invocation it prepares a per-thread host directory
(``<host_reports_root>/<thread_id>/``) and appends a single
:class:`SystemMessage` that:

1. Tells the agent the exact host path to pass as
   ``report_gen.output_dir``.
2. Spells out the **host vs sandbox** I/O boundary so the agent stops
   calling ``file_read`` on host-owned artefacts. The returned
   ``markdown_content`` carries the rendered report body for any
   user-visible appendix.

The middleware is idempotent — the hint is emitted once per
``(thread_id, process)`` tuple and never duplicated on subsequent
rounds.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import SystemMessage

if TYPE_CHECKING:  # pragma: no cover
    from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class ReportBootstrapMiddleware(AgentMiddleware):
    """Inject ``report_gen.output_dir`` + host/sandbox boundary hint.

    Args:
        host_reports_root: Directory that will host the per-thread
            report output sub-directories. Created on init if missing;
            each LangGraph ``thread_id`` gets its own
            ``<host_reports_root>/<thread_id>/`` sub-directory created
            lazily so concurrent sessions cannot collide.
        thread_id_fallback: Directory name used when the runtime does
            not expose a ``thread_id`` (typically only during tests).
    """

    def __init__(
        self,
        *,
        host_reports_root: Path,
        thread_id_fallback: str = "anonymous",
    ) -> None:
        super().__init__()
        self._root = Path(host_reports_root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._fallback = thread_id_fallback
        # Track threads that have already received the hint so the
        # system message is not re-injected on every agent round.
        self._announced: set[str] = set()

    @staticmethod
    def _thread_id(runtime: Runtime[Any]) -> str | None:
        """Best-effort pull of the LangGraph thread_id from the runtime."""
        ctx = getattr(runtime, "config", None) or {}
        configurable = ctx.get("configurable") if isinstance(ctx, dict) else None
        if isinstance(configurable, dict):
            tid = configurable.get("thread_id")
            if isinstance(tid, str) and tid:
                return tid
        return None

    def _resolve_target_dir(self, thread_id: str) -> Path:
        target = self._root / thread_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    def before_agent(
        self,
        state: AgentState,  # noqa: ARG002 — state unused; kept for signature parity
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Emit the report-bootstrap hint once per thread."""
        thread_id = self._thread_id(runtime) or self._fallback
        if thread_id in self._announced:
            return None

        target_dir = self._resolve_target_dir(thread_id)
        self._announced.add(thread_id)

        hint = (
            "[REPORT_BOOTSTRAP]\n"
            "FR-15 report target (host-side):\n"
            f"- analysis_id: `{thread_id}`\n"
            f"- report_gen.output_dir: `{target_dir}`\n\n"
            "## Host vs Sandbox I/O boundary (IMPORTANT)\n"
            "- The following tools operate inside the **sandbox** and "
            "accept sandbox paths under `/workspace/<analysis_id>/…`:\n"
            "  `bash`, `python_exec`, `file_read`, `file_identify`.\n"
            "- The following tool operates on the **host** filesystem "
            "and accepts host paths:\n"
            "  `report_gen.output_dir` (pass exactly the path above).\n"
            "- Never pass a `/workspace/...` sandbox path to "
            "`report_gen.output_dir`; never call `file_read` on the "
            "returned `json_path` / `md_path` — those live on the host, "
            "not in the sandbox, and `file_read` will raise "
            "`FileNotFoundException`.\n"
            "- `report_gen` returns `{json_path, md_path, sha256, "
            "schema_version, markdown_content, cleanup_performed}`. "
            "When producing the final user-visible report, include the "
            "brief conclusion first, then append `## 附录：详细报告` "
            "using `markdown_content`; do not stop at the file name "
            "alone.\n\n"
            "When you finish the FR-13 → FR-14 → FR-15 sequence, invoke "
            "`report_gen` with exactly `analysis_id` and `output_dir` "
            "from this message."
        )
        return {"messages": [SystemMessage(content=hint)]}


__all__ = ["ReportBootstrapMiddleware"]
