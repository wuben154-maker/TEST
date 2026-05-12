"""Audit tracing for onion-style email investigations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

ToolStatus = Literal["ok", "unavailable", "timeout", "error", "skipped"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class DecisionTrace:
    timestamp: str
    decision: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolTrace:
    timestamp: str
    tool_name: str
    target: dict[str, Any]
    status: ToolStatus
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BudgetTrace:
    timestamp: str
    tool_calls_left: int
    tool_calls_used: int
    note: str = ""


@dataclass(slots=True)
class AuditTrace:
    decisions: list[DecisionTrace] = field(default_factory=list)
    tool_calls: list[ToolTrace] = field(default_factory=list)
    budgets: list[BudgetTrace] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def record_decision(
        self, decision: str, *, reason: str, details: dict[str, Any] | None = None
    ) -> None:
        self.decisions.append(
            DecisionTrace(
                timestamp=_utc_now_iso(),
                decision=decision,
                reason=reason,
                details=details or {},
            )
        )

    def record_tool_call(
        self,
        tool_name: str,
        *,
        target: dict[str, Any],
        status: ToolStatus,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.tool_calls.append(
            ToolTrace(
                timestamp=_utc_now_iso(),
                tool_name=tool_name,
                target=target,
                status=status,
                summary=summary,
                details=details or {},
            )
        )

    def record_budget(
        self, *, tool_calls_left: int, tool_calls_used: int, note: str = ""
    ) -> None:
        self.budgets.append(
            BudgetTrace(
                timestamp=_utc_now_iso(),
                tool_calls_left=tool_calls_left,
                tool_calls_used=tool_calls_used,
                note=note,
            )
        )

    def add_limitation(self, limitation: str) -> None:
        lim = (limitation or "").strip()
        if lim and lim not in self.limitations:
            self.limitations.append(lim)

    def export_limitations_as_technical_proofs(self) -> list[dict[str, Any]]:
        return sorted(
            [
                {
                    "component": "BODY",
                    "status": "WARNING",
                    "detail": f"Limitation: {lim}",
                }
                for lim in self.limitations
            ],
            key=lambda x: x["detail"],
        )

    def export_investigation_log(self, *, max_lines: int = 30) -> list[str]:
        lines: list[str] = []
        for d in self.decisions:
            lines.append(f"[{d.timestamp}] DECISION {d.decision}: {d.reason}")
        for t in self.tool_calls:
            lines.append(f"[{t.timestamp}] TOOL {t.tool_name} ({t.status}): {t.summary}")
        for b in self.budgets:
            lines.append(
                f"[{b.timestamp}] BUDGET used={b.tool_calls_used} left={b.tool_calls_left} {b.note}".rstrip()
            )
        if len(lines) > max_lines:
            return lines[:max_lines] + [f"...({len(lines) - max_lines} more)"]
        return lines

