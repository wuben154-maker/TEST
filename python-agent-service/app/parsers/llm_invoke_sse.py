"""Emit llm_invoke_start / llm_delta / llm_invoke_end for per-LLM-call timing and streaming.

``channel`` on deltas: ``reasoning`` (chain-of-thought) or ``text`` (user-visible tokens).

When ``emit_boundaries`` is True (self-contained paths like research subagent), start is
emitted lazily on the first non-empty delta and close() emits end.
When False (main deepagents adapter), ``llm_invoke_start`` / ``llm_invoke_end`` come from
:class:`LlmInvokeLifecycleCallbackHandler` on every LLM call (including tool-decision
rounds with no visible output); ``llm_delta`` uses ``current_llm_invoke_id_for_delta()``
so ``invokeId`` matches the active callback run.
Paths without lifecycle callbacks (e.g. some subagent mirrors) fall back to a local id.
``close()`` ends the invoke when ``emit_boundaries`` is True; otherwise it only clears state.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from app.parsers.llm_invoke_callbacks import current_llm_invoke_id_for_delta

EmitFn = Callable[[dict[str, Any]], dict[str, Any]]
OrphanEndFn = Callable[[str], None]


def _coerce_usage(usage: Any) -> dict[str, int] | None:
    """Normalize a LangChain-style usage dict into the SSE ``usage`` contract.

    Accepts ``AIMessage.usage_metadata`` (``input_tokens``/``output_tokens``) or
    an already-normalized ``{"inputTokens", "outputTokens"}``. Returns ``None``
    when neither shape is present — the caller will then omit the field and the
    frontend reducer will simply skip the event (legacy contract).
    """
    if not isinstance(usage, dict):
        return None
    try:
        input_t = int(
            usage.get("inputTokens")
            or usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or 0
        )
        output_t = int(
            usage.get("outputTokens")
            or usage.get("output_tokens")
            or usage.get("completion_tokens")
            or 0
        )
    except (TypeError, ValueError):
        return None
    if input_t == 0 and output_t == 0:
        # No meaningful numbers — skip rather than pollute the indicator with zeros.
        return None
    return {"inputTokens": max(0, input_t), "outputTokens": max(0, output_t)}


def llm_invoke_triplet(
    channel: str,
    content: str,
    *,
    extra: dict[str, Any] | None = None,
    usage: Any | None = None,
    model_id: str | None = None,
) -> list[dict[str, Any]]:
    """Emit ``llm_invoke_start`` + ``llm_delta`` + ``llm_invoke_end`` for one non-streaming blob.

    Used by research / task_planner paths that emit a full message at once (no token stream).
    Returns an empty list when ``content`` is empty or whitespace-only.

    ``usage`` (optional): ``AIMessage.usage_metadata`` or
    ``{"inputTokens", "outputTokens"}``. When provided and non-zero, stamped on
    ``llm_invoke_end`` so the realtime context-usage indicator can light up for
    paths that do not go through ``LlmInvokeLifecycleCallbackHandler``.
    """
    raw = content if isinstance(content, str) else ""
    if not raw.strip():
        return []
    ch = "reasoning" if channel == "reasoning" else "text"
    iid = uuid.uuid4().hex[:12]
    base = dict(extra or {})
    t_start = int(time.time() * 1000)
    t_end = int(time.time() * 1000)
    start_ev: dict[str, Any] = {
        **base,
        "type": "llm_invoke_start",
        "id": iid,
        "invokeId": iid,
        "timestamp": t_start,
    }
    if model_id:
        start_ev["modelId"] = model_id
    end_ev: dict[str, Any] = {
        **base,
        "type": "llm_invoke_end",
        "id": iid,
        "invokeId": iid,
        "timestamp": t_end,
    }
    normalized = _coerce_usage(usage)
    if normalized is not None:
        end_ev["usage"] = normalized
    return [
        start_ev,
        {
            **base,
            "type": "llm_delta",
            "id": iid,
            "invokeId": iid,
            "channel": ch,
            "content": raw,
        },
        end_ev,
    ]


class LlmInvokeEmitter:
    """Buffers one open LLM invoke; yields canonical SSE dicts through ``emit_fn``."""

    __slots__ = ("_emit", "_open", "_invoke_id", "_emit_boundaries", "_on_orphan_realign", "_pre_opened")

    def __init__(
        self,
        emit_fn: EmitFn,
        *,
        emit_boundaries: bool = True,
        on_orphan_realign: OrphanEndFn | None = None,
    ) -> None:
        self._emit = emit_fn
        self._open = False
        self._invoke_id: str | None = None
        self._emit_boundaries = emit_boundaries
        self._on_orphan_realign = on_orphan_realign
        self._pre_opened = False

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def invoke_id(self) -> str | None:
        return self._invoke_id

    def pre_open(self, invoke_id: str, timestamp_ms: int) -> list[dict[str, Any]]:
        """Eagerly open an invoke and emit ``llm_invoke_start`` immediately.

        Called from ``on_chat_model_start`` callbacks to push the start event
        through ``stream_writer`` in real-time — before ``astream`` yields the
        completed ``AIMessage``.  When ``delta()`` is later called for the same
        invoke it sees ``_open=True`` and skips the duplicate start emission.
        """
        if self._open:
            self.close()
        self._invoke_id = invoke_id
        self._open = True
        self._pre_opened = True
        out: list[dict[str, Any]] = []
        if self._emit_boundaries:
            out.append(
                self._emit(
                    {
                        "type": "llm_invoke_start",
                        "id": invoke_id,
                        "invokeId": invoke_id,
                        "timestamp": timestamp_ms,
                    }
                )
            )
        return out

    def close(
        self,
        *,
        usage: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Emit ``llm_invoke_end`` if an invoke is open; always clears state.

        ``usage`` (optional): ``AIMessage.usage_metadata`` or
        ``{"inputTokens", "outputTokens"}``. When provided and non-zero the
        end event carries ``usage`` so the realtime context-usage indicator
        lights up for paths that do not install
        ``LlmInvokeLifecycleCallbackHandler`` (subagents, research emitter,
        etc.).  ``_coerce_usage`` drops missing/zero shapes so the event stays
        backward-compatible.
        """
        if not self._open or not self._invoke_id:
            self._open = False
            self._invoke_id = None
            self._pre_opened = False
            return []
        iid = self._invoke_id
        self._open = False
        self._invoke_id = None
        self._pre_opened = False
        if not self._emit_boundaries:
            return []
        end_ev: dict[str, Any] = {
            "type": "llm_invoke_end",
            "id": iid,
            "invokeId": iid,
            "timestamp": int(time.time() * 1000),
        }
        normalized = _coerce_usage(usage)
        if normalized is not None:
            end_ev["usage"] = normalized
        return [self._emit(end_ev)]

    def delta(self, channel: str, content: str) -> list[dict[str, Any]]:
        """Append one delta; opens invoke on first non-empty content when using local UUID mode."""
        raw = content if isinstance(content, str) else ""
        if not raw.strip():
            return []
        ch = "reasoning" if channel == "reasoning" else "text"
        out: list[dict[str, Any]] = []
        # Callback lifecycle can finish (on_llm_end pops ContextVar) before the adapter
        # runs llm_emit.close(). A new on_chat_model_start may then push a different id while
        # this emitter still thinks the previous session is open — realign to the active run.
        if self._open:
            ext = current_llm_invoke_id_for_delta()
            if ext is not None and self._invoke_id is not None and ext != self._invoke_id:
                old_iid = self._invoke_id
                cb = self._on_orphan_realign
                if cb is not None:
                    cb(old_iid)
                self._open = False
                self._invoke_id = None
        if not self._open:
            ext = current_llm_invoke_id_for_delta()
            self._invoke_id = ext if ext else uuid.uuid4().hex[:12]
            self._open = True
            iid = self._invoke_id
            if self._emit_boundaries:
                out.append(
                    self._emit(
                        {
                            "type": "llm_invoke_start",
                            "id": iid,
                            "invokeId": iid,
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                )
        else:
            assert self._invoke_id is not None
            iid = self._invoke_id
        if self._emit_boundaries:
            assert self._invoke_id is not None
        out.append(
            self._emit(
                {
                    "type": "llm_delta",
                    "id": iid,
                    "invokeId": iid,
                    "channel": ch,
                    "content": raw,
                }
            )
        )
        return out
