"""ReAct cycle counter for SSE envelopes.

Each *turn* groups one Think phase (streaming reasoning chunks) and the Act phase
(tool_call / tool_result) that follows until the next Think. Multiple streaming
``reasoning`` events share the same turn until a ``tool_result`` schedules the
next cycle.

Main graph and each subagent run use a separate :class:`ReactTurnTracker` instance.
"""

from __future__ import annotations

from typing import Any


class ReactTurnTracker:
    """Monotonic ReAct turn counter for a single agent run (main or subagent)."""

    __slots__ = ("_cycle_turn", "_pending_next_cycle")

    def __init__(self) -> None:
        self._cycle_turn: int = 1
        self._pending_next_cycle: int | None = None

    def on_reasoning(self) -> int:
        """Assign turn for a reasoning chunk; applies pending cycle after tool_result."""
        if self._pending_next_cycle is not None:
            self._cycle_turn = self._pending_next_cycle
            self._pending_next_cycle = None
        return self._cycle_turn

    def on_tool_call(self) -> int:
        """Tool call belongs to the same cycle as the preceding think phase."""
        return self._cycle_turn

    def on_tool_result(self) -> int:
        """Act result for the current cycle; schedules turn+1 for the next reasoning."""
        t = self._cycle_turn
        self._pending_next_cycle = self._cycle_turn + 1
        return t

    def peek_cycle_turn(self) -> int:
        """Read current cycle without consuming pending (steps, task_plan, etc.)."""
        return self._cycle_turn

    def turn_for_terminal_output(self) -> int:
        """Conclusion / task_summary / final messages after the last act."""
        if self._pending_next_cycle is not None:
            return self._pending_next_cycle
        return self._cycle_turn


def attach_turn_to_event(ev: dict[str, Any], tracker: ReactTurnTracker) -> None:
    """Mutate ``ev`` with ``turn`` if missing. Idempotent if ``turn`` already set."""
    if ev.get("turn") is not None:
        return
    t = ev.get("type")
    if t == "reasoning":
        ev["turn"] = tracker.on_reasoning()
    elif t == "llm_delta":
        ch = ev.get("channel")
        if ch == "reasoning":
            ev["turn"] = tracker.on_reasoning()
        else:
            ev["turn"] = tracker.peek_cycle_turn()
    elif t in ("llm_invoke_start", "llm_invoke_end"):
        ev["turn"] = tracker.peek_cycle_turn()
    elif t == "tool_call":
        ev["turn"] = tracker.on_tool_call()
    elif t == "tool_result":
        ev["turn"] = tracker.on_tool_result()
    elif t in ("conclusion", "task_summary"):
        ev["turn"] = tracker.turn_for_terminal_output()
    elif t == "done":
        ev["turn"] = tracker.peek_cycle_turn()
    else:
        ev["turn"] = tracker.peek_cycle_turn()
