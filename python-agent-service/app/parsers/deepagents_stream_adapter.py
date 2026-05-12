"""DeepAgents stream to SSE event adapter.

Maps official create_deep_agent astream() output to the frontend SSE event protocol.

Also provides adapt_subagent_astream_to_skill_events for real-time subagent
tool_call/tool_result streaming. Events are yielded as dict (ThinkingEvent-compatible)
to avoid SkillEvent->dict double conversion.
"""

import asyncio
import time
from typing import Any, AsyncGenerator

import structlog
from app.sse.envelope import apply_sse_envelope, tag_merged_subagent_sse
from app.sse.tool_presentation import attach_tool_presentation, should_emit_tool_output
from app.sse.tool_result_renderers import render_tool_result
from app.parsers.labels import (get_stream_adapter_label,
                                get_task_submitted_placeholders)
from app.parsers.react_turn import ReactTurnTracker, attach_turn_to_event
from app.parsers.final_message_split import (
    heuristic_digest_and_report,
    split_final_assistant_message,
    split_subagent_wrapup_and_full,
    strip_conclusion_machine_tails,
    strip_leading_preface_before_cjk_report_body,
    subagent_sse_visible_text,
)
from app.parsers.hitl_interrupt_sse import INTERRUPT_KEY, interrupts_to_sse_events
from app.billing.llm_usage_per_invoke import LlmUsagePerInvokeCallbackHandler
from app.config import get_settings
from app.context_budget.meter import ContextMeter
from app.context_budget.policy import build_context_budget_event_dict
from app.parsers.llm_invoke_callbacks import (
    LlmInvokeLifecycleCallbackHandler,
    flatten_runnable_callbacks,
)
from app.parsers.llm_invoke_sse import LlmInvokeEmitter
from app.parsers.message_content import (
    additional_kwargs_reasoning_text,
    reasoning_text_from_reasoning_block,
)
from app.parsers.path_display_redact import (
    sanitize_task_tool_input_for_display,
    sanitize_write_todos_tool_input_for_display,
)
from app.parsers.path_scrub import scrub_event
from app.parsers.stats_meta import (
    SECURITY_FINDING_TOOLS,
    build_task_stats_meta,
    collect_security_findings_from_tool_output,
)
from app.parsers.tool_status import derive_tool_status as _derive_tool_status
from langchain_core.messages import AIMessage

logger = structlog.get_logger()

# Backward-compatible names for tests and internal call sites
_apply_sse_envelope = apply_sse_envelope
_tag_merged_subagent_sse = tag_merged_subagent_sse


# Tools the main agent may use directly (IOC lookup, info search, exploration).
# Bypass warning only fires when tools used are NOT in this set.
MAIN_AGENT_ALLOWED_DIRECT_TOOLS = frozenset({
    "extract_iocs", "decode_base64", "decode_url", "lookup_threat_intel",
    "web_search", "scrape_url", "summarize_content",
    "read_file", "grep", "glob", "ls", "write_todos",
})


def _coerce_tool_call_args(raw: Any) -> dict[str, Any]:
    """Ensure tool call ``args`` is a dict.

    Providers occasionally surface ``args`` as a JSON string or other type;
    using ``.get`` on that value causes ``'str' object has no attribute 'get'``.
    """
    if isinstance(raw, dict):
        return raw
    return {}


def _extract_text(content: Any) -> str:
    """Normalize content to plain text (for ToolMessage, etc.).

    Anthropic returns either a bare string or a list of content blocks
    (e.g. [{'type': 'text', 'text': '...', 'extras': {'signature': '...'}}]).
    The 'extras.signature' field is an internal Anthropic prompt-caching token
    that must never be exposed to callers.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts)
    return str(content) if content else ""


def _sse_tool_output(tool_name: str, output_text: str) -> str:
    """Conditionally omit heavy tool output from SSE by configured tool name.

    When emission is allowed, the raw tool text is handed to
    :func:`render_tool_result`, which dispatches to a subagent-owned
    per-tool renderer when one is registered and otherwise falls back to the
    generic humanizer. Non-JSON input flows through unchanged.

    **Error bypass:** when the tool payload is a plain DeepAgents-style
    ``"Error: ..."`` string, the output is always emitted (even for tools with
    ``emit_output=False`` such as ``read_file``) so the UI + user can see
    *why* the call failed. Without this, failing ``read_file`` calls would
    render as empty error cards and the user could not tell a missing-file
    error from an auth/path error.
    """
    raw = output_text or ""
    stripped = raw.strip().lower()
    is_plain_error = (
        stripped.startswith("error:") or stripped.startswith("error ")
    )
    if not should_emit_tool_output(tool_name) and not is_plain_error:
        return ""
    return render_tool_result(tool_name, raw)


def _sse_task_tool_output_visible(output_text: str) -> str:
    """task() return may include ``SM_SUBAGENT_FULL_REPORT``; SSE shows WRAPUP/heuristic only."""
    raw = (output_text or "").strip()
    if not raw:
        return ""
    return subagent_sse_visible_text(raw) or raw


def _sse_task_tool_output_deep_research(output_text: str) -> str:
    """Deep-research task output for SSE tool_result.

    Parsed via ``split_subagent_wrapup_and_full`` (body-first: full report above WRAPUP,
    or classic WRAPUP/FULL). Only the WRAPUP preview is shown. Safety fallback: if
    anchors are absent the full text is returned instead of the heuristic first-paragraph
    truncation.
    """
    raw = (output_text or "").strip()
    if not raw:
        return ""
    wrapup, _full = split_subagent_wrapup_and_full(raw)
    if wrapup is not None and wrapup.strip():
        return wrapup.strip()
    return raw


def _normalize_subagent_type_id(raw: str) -> str:
    return str(raw or "").strip().lower().replace("_", "-")


def _all_task_outputs_are_deep_research(
    subagent_types: list[str],
    outputs: list[str],
) -> bool:
    """True when every non-empty task() result in this run used ``subagent_type`` deep-research."""
    if not outputs or len(subagent_types) != len(outputs):
        return False
    return all(_normalize_subagent_type_id(s) == "deep-research" for s in subagent_types)


def _extract_thinking_and_text(msg: AIMessage) -> tuple[str, str]:
    """Extract thinking/reasoning and final text from AIMessage.

    Supports multi-provider thinking output:
    - Anthropic: content blocks with type "thinking" | "text"
    - OpenAI / OpenRouter: additional_kwargs + LangChain blocks ``type: reasoning``
      (nested ``reasoning_text``) or Gemini ``thought`` parts
    - Google Gemini: content parts with thought=True | thought=False (Gemini 2.5/3.x)
    """
    thinking_parts: list[str] = []
    text_parts: list[str] = []

    # 1. OpenAI-style + OpenRouter ``reasoning`` alias (see ``additional_kwargs_reasoning_text``).
    additional = getattr(msg, "additional_kwargs", None) or {}
    if isinstance(additional, dict):
        rk = additional_kwargs_reasoning_text(additional)
        if rk:
            thinking_parts.append(rk)

    # 2. Content blocks (Anthropic / Gemini)
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            # Anthropic: type "thinking" | "text"
            if block.get("type") == "thinking":
                thinking_parts.append(str(block.get("thinking", "")))
            elif block.get("type") == "reasoning":
                rr = reasoning_text_from_reasoning_block(block)
                if rr:
                    thinking_parts.append(rr)
            elif block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            # Gemini: thought flag on parts (no type field)
            elif block.get("thought") is True:
                thinking_parts.append(str(block.get("text", "")))
            elif "text" in block:
                text_parts.append(str(block.get("text", "")))
            # Fallback: any block with string-like content (unknown provider formats)
            elif isinstance(block.get("content"), str):
                text_parts.append(str(block.get("content", "")))

    # Fallback: extract any string from list blocks (unknown provider formats)
    if not thinking_parts and not text_parts and isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                for key in ("text", "content", "summary"):
                    v = block.get(key)
                    if isinstance(v, str) and v.strip():
                        text_parts.append(v)
                        break

    return ("".join(thinking_parts), "".join(text_parts))


def _extract_thinking_from_chunk(chunk: Any) -> str:
    """Extract thinking from AIMessageChunk for token-level streaming.

    AIMessageChunk inherits from AIMessage; reuse _extract_thinking_and_text.
    """
    if chunk is None:
        return ""
    if hasattr(chunk, "content") or hasattr(chunk, "additional_kwargs"):
        thinking, _ = _extract_thinking_and_text(chunk)
        return thinking or ""
    return ""


def _normalize_messages(raw_messages: Any) -> list[Any]:
    """Normalize LangGraph node 'messages' payload to a plain list.

    Some middleware nodes may emit special wrapper types (e.g. Overwrite)
    that are not sized (no __len__). This adapter only needs iterable items.
    """
    if raw_messages is None:
        return []
    if isinstance(raw_messages, list):
        return raw_messages
    if isinstance(raw_messages, tuple):
        return list(raw_messages)
    wrapped = getattr(raw_messages, "value", None)
    if isinstance(wrapped, list):
        return wrapped
    try:
        return list(raw_messages)
    except Exception:
        return []


def _message_signature(msg: AIMessage) -> str:
    """Build a stable signature for deduplication (id or content hash)."""
    mid = getattr(msg, "id", None)
    if mid and isinstance(mid, str):
        return f"id:{mid}"
    _thinking, _text = _extract_thinking_and_text(msg)
    combined = (_thinking or "") + "\n" + (_text or "")
    if combined.strip():
        return f"content:{hash(combined[:500])}"
    tool_calls = getattr(msg, "tool_calls", None) or []
    if tool_calls:
        # Fallback for tool-only AIMessage (empty text/thinking).
        return f"tool_calls:{hash(str(tool_calls)[:500])}"
    return ""


async def adapt_astream_to_sse(
    agent: Any,
    initial_state: dict[str, Any],
    config: dict[str, Any],
    *,
    stream_mode: str | list[str] = "updates",
    language: str = "en",
    seen_message_signatures: frozenset[str] | None = None,
    use_messages_stream: bool = True,
    stream_input: Any | None = None,
    stream_request_id: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Adapt agent.astream() output to SSE event format.

    Maps LangGraph stream events to ThinkingEvent-compatible dicts:
    - agent node AIMessage (tool_calls) -> tool_call
    - chain-of-thought / visible tokens -> ``llm_invoke_*`` + ``llm_delta`` (``channel``)
    - messages mode AIMessageChunk -> incremental ``llm_delta`` (reasoning channel)
    - tools node ToolMessage -> tool_result
    - stream end -> conclusion (from final state), step (analysis-complete), done

    Args:
        agent: CompiledStateGraph from create_deep_agent (has astream, ainvoke).
        initial_state: Initial state dict for the agent.
        config: LangGraph config (e.g., {"configurable": {"thread_id": "..."}}).
        stream_mode: LangGraph stream mode; use ["messages", "updates"] for token streaming.
        language: Language for localized step labels.
        use_messages_stream: If True, use messages+updates for real-time reasoning stream.
        stream_input: When set (e.g. ``Command(resume=...)``), passed to ``astream`` instead
            of ``initial_state`` for HITL resume runs.
    """
    seen_tool_calls: dict[str, dict[str, Any]] = {}
    tools_used: set[str] = set()
    task_outputs: list[str] = []
    task_output_subagent_types: list[str] = []
    # Structured findings accumulated from security tool results, fed into the
    # `conclusion.meta.security` payload (see stats_meta.py).
    security_findings_raw: list[dict[str, Any]] = []
    saw_task_tool = False
    saw_any_tool_activity = False
    saw_reasoning = False
    saw_first_tool_call = False  # Only emit reasoning before first tool_call (intent phase)
    emitted_reasoning_from_messages = False  # Skip updates reasoning if already streamed from messages
    latest_ai_text = ""
    latest_reasoning_text = ""
    finalize_reason = "none"
    # Checkpoint AI messages (pre-request): skip entirely — stale tool_calls must not replay.
    # In-stream duplicate of the same signature: skip duplicate reasoning but still emit tool_call
    # once per tool_call id (see emitted_tool_call_sse_ids).
    checkpoint_message_sigs = frozenset(seen_message_signatures or ())
    _seen_message_sigs: set[str] = set(checkpoint_message_sigs)
    _seen_reasoning_sigs: set[str] = set(seen_message_signatures or ())
    _seen_answer_sigs: set[str] = set()
    emitted_tool_call_sse_ids: set[str] = set()
    emitted_task_running_step_ids: set[str] = set()
    # tool_call ids from checkpoint AIMessages (pre-resume).  Their ToolMessages
    # arrive in-stream (the subagent resumes and completes) but the adapter must
    # not emit phantom step running / step success / task_complete events because
    # no fresh AIMessage tool_call was emitted in *this* stream.
    _checkpoint_tool_call_ids: set[str] = set()
    # Track only current-run task() calls and their non-empty results.
    fresh_task_call_ids: set[str] = set()
    task_result_call_ids: set[str] = set()
    total_stream_chunks = 0
    node_event_counts: dict[str, int] = {}
    total_agent_messages = 0
    total_ai_messages = 0
    empty_ai_messages = 0
    # Track previous todos to detect status transitions from write_todos calls
    _prev_todos: list[dict] = []
    _seq: list[int] = [0]
    main_turn = ReactTurnTracker()
    paused_for_hitl = False
    hitl_resume_meta: dict[str, Any] = {}

    def _emit(ev: dict[str, Any]) -> dict[str, Any]:
        attach_turn_to_event(ev, main_turn)
        attach_tool_presentation(ev)
        # Final step before the event reaches the UI: strip internal owner /
        # store / skill path fragments and replace them with user-friendly
        # labels (workspace/, Memory:, System Skill:, Parameters).
        ev = scrub_event(ev)
        return apply_sse_envelope(ev, _seq)

    # llm_invoke_start/end from LangChain callbacks; llm_delta invokeId from ContextVar
    # (see LlmInvokeLifecycleCallbackHandler + LlmInvokeEmitter). Lifecycle dicts are
    # put_nowait on the same event-loop thread as astream (LangChain default); merged with
    # graph chunks via asyncio.wait so ends are not deferred to end-of-iteration batches.
    # After each llm_emit yield we drain the queue with get_nowait to interleave any
    # lifecycle events that arrived during synchronous callback completion.
    llm_lifecycle_q: asyncio.Queue = asyncio.Queue(maxsize=2048)
    context_meter = ContextMeter()

    def _enqueue_lifecycle(ev: dict[str, Any]) -> None:
        try:
            llm_lifecycle_q.put_nowait(ev)
        except asyncio.QueueFull:
            logger.warning("llm_lifecycle_queue_full_drop", event_type=ev.get("type"))

    llm_lifecycle_handler = LlmInvokeLifecycleCallbackHandler(
        emit_start=_enqueue_lifecycle,
        emit_end=_enqueue_lifecycle,
        context_meter=context_meter,
    )
    # Dedupe llm_invoke_end when we synthesize one before close() and on_llm_end still fires later.
    _llm_invoke_end_emitted_ids: set[str] = set()
    # Synthetic ends enqueued but not yet drained (prevents double _ensure before merge reads the queue).
    _llm_invoke_end_scheduled_ids: set[str] = set()

    def _lifecycle_client_events(
        ev: dict[str, Any],
        *,
        include_context_budget: bool,
    ) -> list[dict[str, Any]]:
        """Apply SSE envelope; optionally append ``context_budget`` after ``llm_invoke_end``.

        Drops duplicate ``llm_invoke_end`` (same ``invokeId``). Subagent merged SSE
        must set ``include_context_budget=False`` so the main-graph tier line stays clean.
        """
        if ev.get("type") != "llm_invoke_end":
            return [_emit(ev)]
        iid = str(ev.get("invokeId") or ev.get("id") or "")
        if iid and iid in _llm_invoke_end_emitted_ids:
            _llm_invoke_end_scheduled_ids.discard(iid)
            return []
        if iid:
            _llm_invoke_end_emitted_ids.add(iid)
            _llm_invoke_end_scheduled_ids.discard(iid)
        out: list[dict[str, Any]] = [_emit(ev)]
        if include_context_budget:
            budget = build_context_budget_event_dict(
                llm_invoke_end=ev,
                settings=get_settings(),
            )
            if budget is not None:
                out.append(_emit(budget))
        return out

    def _lifecycle_client_event_tagged_subagent(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Tag merged subagent SSE then apply the same ``llm_invoke_end`` dedupe as lifecycle queue."""
        return _lifecycle_client_events(
            tag_merged_subagent_sse(raw),
            include_context_budget=False,
        )

    # Track cutoff indices for summarization events already emitted so we do not
    # double-emit when the `_summarization_event` state key flows through multiple
    # consecutive `updates` chunks with the same payload.
    _emitted_summarization_cutoffs: set[int] = set()

    def _ensure_llm_invoke_end_for_id(iid: str) -> None:
        """Queue ``llm_invoke_end`` for this ``invokeId`` if not already emitted (main graph).

        Used when: LangGraph omits ``on_llm_end``, ContextVar UUID fallback (not in handler map),
        or ``LlmInvokeEmitter`` realigns to a new invoke id before ``close()`` runs.
        """
        if not iid or iid in _llm_invoke_end_emitted_ids or iid in _llm_invoke_end_scheduled_ids:
            return
        _llm_invoke_end_scheduled_ids.add(iid)
        llm_lifecycle_handler.release_stack_for_synthetic_llm_invoke_end(iid)
        # Synthetic end has no LLM response to extract usage from; emit zero usage so
        # the contract stays consistent with on_llm_end/on_llm_error.
        ts = int(time.time() * 1000)
        _enqueue_lifecycle(
            {
                "type": "llm_invoke_end",
                "id": iid,
                "invokeId": iid,
                "timestamp": ts,
                "usage": {"inputTokens": 0, "outputTokens": 0},
            }
        )

    llm_emit = LlmInvokeEmitter(
        _emit,
        emit_boundaries=False,
        on_orphan_realign=_ensure_llm_invoke_end_for_id,
    )

    def _enqueue_synthetic_llm_invoke_end_before_close() -> None:
        """Queue ``llm_invoke_end`` for the open emitter session when ``close()`` would not emit."""
        if not llm_emit.is_open or not llm_emit.invoke_id:
            return
        _ensure_llm_invoke_end_for_id(llm_emit.invoke_id)

    async def _drain_llm_lifecycle_nowait() -> AsyncGenerator[dict[str, Any], None]:
        while True:
            try:
                raw = llm_lifecycle_q.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(raw, dict):
                for out in _lifecycle_client_events(raw, include_context_budget=True):
                    yield out

    # Emit initial step so UI shows content immediately (not blank until first agent event)
    yield _emit(
        {
            "type": "step",
            "id": "analysis-start",
            "label": get_stream_adapter_label("stream_analysis_start", language),
            "status": "running",
        }
    )

    # Include "custom" so LangGraph yields stream_writer() calls from atask() as
    # real-time {"type": "custom", "data": <event>} chunks while the task tool
    # is executing.  Without "custom" those writes are silently dropped.
    effective_stream_mode: str | list[str] = (
        ["messages", "updates", "custom"] if use_messages_stream else (stream_mode or "updates")
    )
    astream_kwargs: dict[str, Any] = {"stream_mode": effective_stream_mode}
    try:
        import langgraph
        if hasattr(langgraph, "__version__") and langgraph.__version__ >= "1.1":
            astream_kwargs["version"] = "v2"
    except Exception:
        pass

    # Bridge open_deep_research internal astream events into this SSE (via task tool config).
    _stream_cfg = dict(config.get("configurable") or {})
    _existing_q = _stream_cfg.get("subagent_sse_event_queue")
    if isinstance(_existing_q, asyncio.Queue):
        subagent_sse_q = _existing_q
    else:
        subagent_sse_q = asyncio.Queue(maxsize=512)
        _stream_cfg["subagent_sse_event_queue"] = subagent_sse_q
    # Ensure merged subagent SSE (e.g. open_deep_research phases) uses the
    # same UI language as the parent stream unless caller explicitly overrides it.
    _stream_cfg.setdefault("sse_ui_language", language)
    _stream_cfg["_context_meter"] = context_meter
    stream_config: dict[str, Any] = {**config, "configurable": _stream_cfg}
    _cb = flatten_runnable_callbacks(stream_config.get("callbacks"))
    if not any(isinstance(h, LlmUsagePerInvokeCallbackHandler) for h in _cb):
        _cb.append(LlmUsagePerInvokeCallbackHandler())
    _cb.append(llm_lifecycle_handler)
    stream_config["callbacks"] = _cb

    astream_input: Any = stream_input if stream_input is not None else initial_state

    async def _merge_astream_and_lifecycle() -> AsyncGenerator[tuple[str, Any], None]:
        """Merge main graph chunks, LLM lifecycle, and subagent SSE queue in real time.

        When the subagent uses ``subagent_sse_event_queue`` (no ``stream_writer``),
        events must not wait for the next main-graph chunk — otherwise the UI sees
        ConductResearch (e.g. tool_call) only after the deep-research task finishes.
        """
        aiter = agent.astream(astream_input, stream_config, **astream_kwargs).__aiter__()

        async def _next_chunk() -> Any:
            return await aiter.__anext__()

        t_chunk: asyncio.Task[Any] | None = asyncio.create_task(_next_chunk())
        t_life: asyncio.Task[Any] | None = asyncio.create_task(llm_lifecycle_q.get())
        t_sub: asyncio.Task[Any] | None = asyncio.create_task(subagent_sse_q.get())

        try:
            while t_chunk is not None:
                wait_set = {t for t in (t_chunk, t_life, t_sub) if t is not None}
                done, _pending = await asyncio.wait(
                    wait_set,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # Subagent SSE first so tool_call/tool_result order stays ahead of
                # unrelated main-graph chunks when multiple finish in the same tick.
                if t_sub is not None and t_sub in done:
                    try:
                        item = t_sub.result()
                    except asyncio.CancelledError:
                        raise
                    except Exception as ex:  # pragma: no cover
                        logger.warning("subagent_sse_q_get_failed", error=str(ex))
                        item = None
                    t_sub = None
                    if item is not None:
                        yield ("subagent_sse", item)
                        t_sub = asyncio.create_task(subagent_sse_q.get())
                if t_life is not None and t_life in done:
                    try:
                        ev = t_life.result()
                    except asyncio.CancelledError:
                        raise
                    except Exception as ex:  # pragma: no cover
                        logger.warning("lifecycle_q_get_failed", error=str(ex))
                        ev = None
                    if isinstance(ev, dict):
                        yield ("lifecycle", ev)
                    t_life = asyncio.create_task(llm_lifecycle_q.get())
                if t_chunk is not None and t_chunk in done:
                    try:
                        event = t_chunk.result()
                    except StopAsyncIteration:
                        # Drain queued subagent events before cancelling the pending waiter.
                        while True:
                            try:
                                q_item = subagent_sse_q.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                            if q_item is None:
                                break
                            yield ("subagent_sse", q_item)
                        if t_sub is not None and not t_sub.done():
                            t_sub.cancel()
                            try:
                                await t_sub
                            except (asyncio.CancelledError, Exception):
                                pass
                            t_sub = None
                        if t_life is not None and not t_life.done():
                            t_life.cancel()
                            try:
                                await t_life
                            except asyncio.CancelledError:
                                pass
                        # llm_invoke_end often completes t_life in the same tick as stream
                        # exhaustion; if we only cancel pending waiters, a *done* t_life still
                        # holds the event and get_nowait() cannot see it — must yield or re-queue.
                        if t_life is not None and t_life.done():
                            try:
                                _ev = t_life.result()
                                if isinstance(_ev, dict):
                                    yield ("lifecycle", _ev)
                            except (asyncio.CancelledError, Exception):
                                pass
                        t_life = None
                        t_chunk = None
                        while True:
                            try:
                                ev = llm_lifecycle_q.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                            if isinstance(ev, dict):
                                yield ("lifecycle", ev)
                        yield ("stop", None)
                        return
                    yield ("chunk", event)
                    t_chunk = asyncio.create_task(_next_chunk())
        finally:
            if t_sub is not None and not t_sub.done():
                t_sub.cancel()
                try:
                    await t_sub
                except (asyncio.CancelledError, Exception):
                    pass
            if t_chunk is not None and not t_chunk.done():
                t_chunk.cancel()
                try:
                    await t_chunk
                except (asyncio.CancelledError, Exception):
                    pass
            if t_life is not None:
                if t_life.done():
                    try:
                        _left = t_life.result()
                        if isinstance(_left, dict):
                            try:
                                llm_lifecycle_q.put_nowait(_left)
                            except asyncio.QueueFull:
                                logger.warning(
                                    "llm_lifecycle_requeue_full_drop",
                                    event_type=_left.get("type"),
                                )
                    except (asyncio.CancelledError, Exception):
                        pass
                else:
                    t_life.cancel()
                    try:
                        await t_life
                    except (asyncio.CancelledError, Exception):
                        pass

    async def _drain_subagent_sse_queue_tail() -> AsyncGenerator[dict[str, Any], None]:
        """Best-effort drain after merge exits (e.g. exception path)."""
        while True:
            try:
                item = subagent_sse_q.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                break
            for _tagged in _lifecycle_client_event_tagged_subagent(item):
                yield _tagged

    try:
        async for _kind, _payload in _merge_astream_and_lifecycle():
            if _kind == "lifecycle":
                if isinstance(_payload, dict):
                    for _out in _lifecycle_client_events(
                        _payload, include_context_budget=True
                    ):
                        yield _out
                continue
            if _kind == "subagent_sse":
                if isinstance(_payload, dict):
                    for _t in _lifecycle_client_event_tagged_subagent(_payload):
                        yield _t
                continue
            if _kind == "stop":
                break
            event = _payload
            total_stream_chunks += 1

            # Handle v2 format: {"type": "messages"|"updates"|"custom", "data": ...}
            if isinstance(event, dict) and "type" in event and "data" in event:
                chunk_type = event.get("type")
                chunk_data = event.get("data")
                if chunk_type == "messages" and chunk_data:
                    msg_chunk, _metadata = chunk_data if isinstance(chunk_data, (tuple, list)) and len(chunk_data) >= 2 else (chunk_data, {})
                    thinking = _extract_thinking_from_chunk(msg_chunk)
                    if thinking:
                        latest_reasoning_text = (latest_reasoning_text or "") + thinking
                        saw_reasoning = True
                        emitted_reasoning_from_messages = True
                        for _ev in llm_emit.delta("reasoning", thinking):
                            yield _ev
                            async for _le in _drain_llm_lifecycle_nowait():
                                yield _le
                elif chunk_type == "custom" and isinstance(chunk_data, dict):
                    # Real-time subagent event written via runtime.stream_writer in
                    # atask().  Delivered here while the task() tool is still running,
                    # bypassing the side-queue flush-after-tool-ends timing issue.
                    for _ce in _lifecycle_client_event_tagged_subagent(chunk_data):
                        yield _ce
                elif chunk_type == "updates" and isinstance(chunk_data, dict):
                    event = chunk_data
                else:
                    continue
            # Handle v1 format: (mode, data) tuple when stream_mode is list
            elif isinstance(event, (tuple, list)) and len(event) >= 2:
                mode, data = event[0], event[1]
                if mode == "messages" and data:
                    msg_chunk, _metadata = data if isinstance(data, (tuple, list)) and len(data) >= 2 else (data, {})
                    thinking = _extract_thinking_from_chunk(msg_chunk)
                    if thinking:
                        latest_reasoning_text = (latest_reasoning_text or "") + thinking
                        saw_reasoning = True
                        emitted_reasoning_from_messages = True
                        for _ev in llm_emit.delta("reasoning", thinking):
                            yield _ev
                            async for _le in _drain_llm_lifecycle_nowait():
                                yield _le
                elif mode == "custom" and isinstance(data, dict):
                    # v1 format custom event (same semantics as v2 "custom" above).
                    for _ce in _lifecycle_client_event_tagged_subagent(data):
                        yield _ce
                elif mode == "updates" and isinstance(data, dict):
                    event = data
                else:
                    continue
            else:
                event = event if isinstance(event, dict) else {}

            if not isinstance(event, dict):
                continue

            # LangGraph HITL: updates chunk may be { "__interrupt__": (Interrupt, ...) }
            if INTERRUPT_KEY in event:
                evs, meta = interrupts_to_sse_events(
                    event[INTERRUPT_KEY],
                    _emit,
                    stream_request_id=stream_request_id,
                )
                for ev in evs:
                    yield ev
                paused_for_hitl = True
                hitl_resume_meta = meta
                break

            hitl_break_astream = False
            for node_name, node_output in event.items():
                if node_name == INTERRUPT_KEY:
                    evs, meta = interrupts_to_sse_events(
                        node_output,
                        _emit,
                        stream_request_id=stream_request_id,
                    )
                    for ev in evs:
                        yield ev
                    paused_for_hitl = True
                    hitl_resume_meta = meta
                    hitl_break_astream = True
                    break
                node_event_counts[node_name] = node_event_counts.get(node_name, 0) + 1
                # Summarization middleware surfaces `_summarization_event` via Command updates.
                # Emit a single `context_summarized` SSE per unique cutoff so the UI can
                # display a toast and pulse the context-usage badge.
                if isinstance(node_output, dict) and "_summarization_event" in node_output:
                    _sum_evt = node_output.get("_summarization_event")
                    if isinstance(_sum_evt, dict):
                        _cutoff = _sum_evt.get("cutoff_index")
                        if isinstance(_cutoff, int) and _cutoff not in _emitted_summarization_cutoffs:
                            _emitted_summarization_cutoffs.add(_cutoff)
                            _ts_now = int(time.time() * 1000)
                            yield _emit(
                                {
                                    "type": "context_summarized",
                                    "timestamp": _ts_now,
                                    "cutoffIndex": _cutoff,
                                }
                            )
                if (
                    isinstance(node_output, dict)
                    and "messages" in node_output
                    and node_name != "tools"
                ):
                    messages = (
                        _normalize_messages(node_output.get("messages", []))
                        if isinstance(node_output, dict)
                        else []
                    )
                    total_agent_messages += len(messages)
                    for msg in messages:
                        if isinstance(msg, AIMessage):
                            total_ai_messages += 1
                            msg_sig = _message_signature(msg)
                            if msg_sig and msg_sig in checkpoint_message_sigs:
                                # Stale checkpoint AI message — do not replay tool_calls or tokens.
                                # Still register tool_call metadata so the tools-node handler
                                # recognises the ToolMessage and skips synthetic tool_call /
                                # phantom step-running / step-success events.
                                for _ck_tc in (msg.tool_calls or []):
                                    if not isinstance(_ck_tc, dict):
                                        continue
                                    _ck_id = _ck_tc.get("id", "")
                                    if _ck_id:
                                        seen_tool_calls[_ck_id] = {
                                            "name": _ck_tc.get("name", ""),
                                            "args": _coerce_tool_call_args(
                                                _ck_tc.get("args")
                                            ),
                                        }
                                        emitted_tool_call_sse_ids.add(_ck_id)
                                        _checkpoint_tool_call_ids.add(_ck_id)
                                continue
                            duplicate_in_stream = bool(msg_sig and msg_sig in _seen_message_sigs)
                            if not duplicate_in_stream and msg_sig:
                                _seen_message_sigs.add(msg_sig)
                            if msg.tool_calls:
                                if not duplicate_in_stream:
                                    _thinking, _text = _extract_thinking_and_text(msg)
                                    if _text:
                                        latest_ai_text = _text
                                    # Chain-of-thought only (never emit final answer text as reasoning).
                                    # After tools, still emit thinking when updates path provides it and
                                    # messages mode has not already streamed reasoning for this graph.
                                    if _thinking and not emitted_reasoning_from_messages:
                                        _sig = _message_signature(msg)
                                        if _sig and _sig not in _seen_reasoning_sigs:
                                            _seen_reasoning_sigs.add(_sig)
                                            latest_reasoning_text = _thinking
                                            saw_reasoning = True
                                            for _ev in llm_emit.delta("reasoning", _thinking):
                                                yield _ev
                                                async for _le in _drain_llm_lifecycle_nowait():
                                                    yield _le
                                    # Visible text tokens are only streamed before the first tool call.
                                    # Final synthesis text is carried by task_summary/conclusion.
                                    if _text and str(_text).strip() and not saw_first_tool_call:
                                        _ms = _message_signature(msg)
                                        _asig = f"{_ms}:answer" if _ms else f"answer-{hash(str(_text)[:200])}"
                                        if _asig not in _seen_answer_sigs:
                                            _seen_answer_sigs.add(_asig)
                                            for _ev in llm_emit.delta("text", str(_text).strip()):
                                                yield _ev
                                                async for _le in _drain_llm_lifecycle_nowait():
                                                    yield _le
                                _enqueue_synthetic_llm_invoke_end_before_close()
                                for _ev in llm_emit.close():
                                    yield _ev
                                async for _le in _drain_llm_lifecycle_nowait():
                                    yield _le
                                for tc in msg.tool_calls:
                                    if not isinstance(tc, dict):
                                        continue
                                    tc_id = tc.get("id", "")
                                    tc_name = tc.get("name", "")
                                    tc_args = _coerce_tool_call_args(tc.get("args"))
                                    if tc_id and tc_id in emitted_tool_call_sse_ids:
                                        continue
                                    if tc_id:
                                        prev = seen_tool_calls.get(tc_id)
                                        if isinstance(prev, dict):
                                            old_a = prev.get("args") if isinstance(prev.get("args"), dict) else {}
                                            merged_args = {**dict(old_a), **tc_args}
                                            seen_tool_calls[tc_id] = {
                                                "name": tc_name or prev.get("name") or "",
                                                "args": merged_args,
                                            }
                                        else:
                                            seen_tool_calls[tc_id] = {
                                                "name": tc_name,
                                                "args": tc_args,
                                            }
                                    if tc_name:
                                        tools_used.add(tc_name)

                                    if tc_name == "write_todos":
                                        # Task list UI: consume tool_call + task_start/task_complete only
                                        # (no duplicate task_plan SSE; same mapping as write_todos_plan).
                                        raw_todos = tc_args.get("todos", []) or tc_args.get("tasks", []) or []
                                        _status_map = {
                                            "pending": "pending",
                                            "in_progress": "running",
                                            "completed": "success",
                                        }
                                        _prev_by_idx = {
                                            str(i): t for i, t in enumerate(_prev_todos)
                                        }
                                        planned_tasks: list[dict[str, Any]] = []
                                        for idx, todo in enumerate(raw_todos):
                                            if not isinstance(todo, dict):
                                                continue
                                            _tid = todo.get("id")
                                            todo_id = str(_tid) if _tid not in (None, "") else str(idx)
                                            task_text = str(
                                                todo.get("content") or todo.get("task") or todo.get("title") or ""
                                            )
                                            raw_status = todo.get("status", "pending")
                                            fe_status = _status_map.get(raw_status, "pending")
                                            planned_tasks.append({
                                                "id": todo_id,
                                                "title": task_text,
                                                "description": task_text,
                                                "taskType": "security",
                                                "priority": idx + 1,
                                                "status": fe_status,
                                                "durationMs": 0,
                                                "steps": [],
                                            })
                                            old_raw = _prev_by_idx.get(todo_id, {}).get("status", "pending")
                                            if old_raw != "in_progress" and raw_status == "in_progress":
                                                yield _emit({"type": "task_start", "id": todo_id})
                                            elif old_raw != "completed" and raw_status == "completed":
                                                yield _emit(
                                                    {
                                                        "type": "task_complete",
                                                        "id": todo_id,
                                                        "status": "success",
                                                    }
                                                )
                                        _prev_todos = list(raw_todos)

                                    if tc_name == "task":
                                        saw_task_tool = True
                                        if tc_id:
                                            fresh_task_call_ids.add(tc_id)
                                    saw_any_tool_activity = True
                                    saw_first_tool_call = True  # Intent phase ended
                                    # tool_call first so clients can anchor delegate UI after the call row
                                    tool_input_for_sse = tc_args
                                    if tc_name == "write_todos":
                                        tool_input_for_sse = (
                                            sanitize_write_todos_tool_input_for_display(tc_args)
                                        )
                                    elif tc_name == "task":
                                        tool_input_for_sse = sanitize_task_tool_input_for_display(
                                            tc_args
                                        )
                                    yield _emit(
                                        {
                                            "type": "tool_call",
                                            "id": tc_id,
                                            "toolName": tc_name,
                                            "toolInput": tool_input_for_sse,
                                            "status": "running",
                                        }
                                    )
                                    if tc_name == "task":
                                        # task_start after tool_call (even if agent skipped write_todos in_progress)
                                        _first_pending_id = None
                                        for _idx, _t in enumerate(_prev_todos):
                                            if isinstance(_t, dict) and _t.get("status") == "pending":
                                                _tid = _t.get("id")
                                                _first_pending_id = str(_tid) if _tid not in (None, "") else str(_idx)
                                                break
                                        if _first_pending_id is not None:
                                            yield _emit({"type": "task_start", "id": _first_pending_id})
                                        if tc_id and tc_id not in emitted_task_running_step_ids:
                                            subagent_type = tc_args.get("subagent_type", "subagent")
                                            analyzing_label = get_stream_adapter_label(
                                                "stream_subagent_analyzing", language
                                            )
                                            yield _emit(
                                                {
                                                    "type": "step",
                                                    "id": f"task-running-{tc_id}",
                                                    "label": f"{subagent_type} {analyzing_label}",
                                                    "status": "running",
                                                    "detail": subagent_type,
                                                }
                                            )
                                            emitted_task_running_step_ids.add(tc_id)
                                    if tc_id:
                                        emitted_tool_call_sse_ids.add(tc_id)
                            else:
                                # Pure text/thinking response (no tool calls)
                                if duplicate_in_stream:
                                    _enqueue_synthetic_llm_invoke_end_before_close()
                                    for _ev in llm_emit.close():
                                        yield _ev
                                    async for _le in _drain_llm_lifecycle_nowait():
                                        yield _le
                                    continue
                                _thinking, _text = _extract_thinking_and_text(msg)
                                if _text:
                                    latest_ai_text = _text
                                # Emit chain-of-thought whenever present; never emit _text as reasoning.
                                if not emitted_reasoning_from_messages:
                                    _sig = _message_signature(msg)
                                    if _sig and _sig not in _seen_reasoning_sigs:
                                        _seen_reasoning_sigs.add(_sig)
                                        if not _thinking and not _text:
                                            empty_ai_messages += 1
                                        if _thinking:
                                            latest_reasoning_text = _thinking
                                            saw_reasoning = True
                                            for _ev in llm_emit.delta("reasoning", _thinking):
                                                yield _ev
                                                async for _le in _drain_llm_lifecycle_nowait():
                                                    yield _le
                                _enqueue_synthetic_llm_invoke_end_before_close()
                                for _ev in llm_emit.close():
                                    yield _ev
                                async for _le in _drain_llm_lifecycle_nowait():
                                    yield _le

                elif isinstance(node_output, dict) and "messages" in node_output:
                    messages = (
                        _normalize_messages(node_output.get("messages", []))
                        if isinstance(node_output, dict)
                        else []
                    )
                    for msg in messages:
                        if hasattr(msg, "content"):
                            tool_call_id = getattr(msg, "tool_call_id", "")
                            # deepagents' _return_command_with_state_update creates ToolMessage
                            # without setting `name`.  Use seen_tool_calls as fallback so we can
                            # still identify task() results and populate task_outputs correctly.
                            tool_name = getattr(msg, "name", None) or (
                                seen_tool_calls.get(tool_call_id, {}).get("name")
                                if tool_call_id
                                else None
                            ) or ""
                            if tool_call_id and tool_call_id not in seen_tool_calls:
                                _enqueue_synthetic_llm_invoke_end_before_close()
                                for _ev in llm_emit.close():
                                    yield _ev
                                async for _le in _drain_llm_lifecycle_nowait():
                                    yield _le
                                yield _emit(
                                    {
                                        "type": "tool_call",
                                        "id": tool_call_id,
                                        "toolName": tool_name,
                                        "toolInput": {},
                                        "status": "running",
                                    }
                                )
                                seen_tool_calls[tool_call_id] = {
                                    "name": tool_name,
                                    "args": {},
                                }
                                if (
                                    tool_name == "task"
                                    and tool_call_id
                                    and tool_call_id not in emitted_task_running_step_ids
                                ):
                                    tc_args = _coerce_tool_call_args(
                                        seen_tool_calls[tool_call_id].get("args")
                                    )
                                    subagent_type = tc_args.get("subagent_type", "subagent")
                                    analyzing_label = get_stream_adapter_label(
                                        "stream_subagent_analyzing", language
                                    )
                                    yield _emit(
                                        {
                                            "type": "step",
                                            "id": f"task-running-{tool_call_id}",
                                            "label": f"{subagent_type} {analyzing_label}",
                                            "status": "running",
                                            "detail": subagent_type,
                                        }
                                    )
                                    emitted_task_running_step_ids.add(tool_call_id)
                                    fresh_task_call_ids.add(tool_call_id)
                                if tool_call_id:
                                    emitted_tool_call_sse_ids.add(tool_call_id)
                                saw_any_tool_activity = True
                            if tool_name:
                                tools_used.add(tool_name)
                            normalized_output = _extract_text(msg.content)
                            if tool_name in SECURITY_FINDING_TOOLS and isinstance(
                                normalized_output, str
                            ):
                                security_findings_raw.extend(
                                    collect_security_findings_from_tool_output(
                                        normalized_output
                                    )
                                )
                            if tool_name == "task":
                                saw_task_tool = True
                            saw_any_tool_activity = True

                            # task tool result: mark the running step as complete.
                            # Skip for checkpoint tool_call_ids (resume path) — no fresh
                            # step-running was emitted, so emitting step-success here would
                            # create a phantom 7ms running→success pair.
                            if tool_name == "task" and tool_call_id not in _checkpoint_tool_call_ids:
                                tc_info = seen_tool_calls.get(tool_call_id, {})
                                subagent_type = _coerce_tool_call_args(
                                    tc_info.get("args") if isinstance(tc_info, dict) else None
                                ).get("subagent_type", "subagent")
                                complete_label = get_stream_adapter_label(
                                    "stream_subagent_complete", language
                                )
                                yield _emit(
                                    {
                                        "type": "step",
                                        "id": f"task-running-{tool_call_id}",
                                        "label": f"{subagent_type} {complete_label}",
                                        "status": "success",
                                    }
                                )
                                # Emit task_complete so UI updates task status.
                                # Match the first in_progress todo id from write_todos so the
                                # frontend can pair this completion with the correct task row.
                                _task_id: str | None = None
                                for _tidx, _t in enumerate(_prev_todos):
                                    if isinstance(_t, dict) and _t.get("status") == "in_progress":
                                        _raw_tid = _t.get("id")
                                        _task_id = str(_raw_tid) if _raw_tid not in (None, "") else str(_tidx)
                                        break
                                if _task_id is None:
                                    _task_id = str(len(task_outputs))
                                yield _emit(
                                    {
                                        "type": "task_complete",
                                        "id": _task_id,
                                        "status": "success",
                                    }
                                )

                            if (
                                tool_name == "task"
                                and isinstance(normalized_output, str)
                                and normalized_output.strip()
                            ):
                                task_outputs.append(normalized_output.strip())
                                _tc_meta = seen_tool_calls.get(tool_call_id, {}) if tool_call_id else {}
                                _args = (
                                    _coerce_tool_call_args(_tc_meta.get("args"))
                                    if isinstance(_tc_meta, dict)
                                    else {}
                                )
                                _st = (
                                    str(_args.get("subagent_type", "") or "subagent").strip()
                                    or "subagent"
                                )
                                task_output_subagent_types.append(_st)
                                if tool_call_id:
                                    task_result_call_ids.add(tool_call_id)
                            if tool_name == "task":
                                _tc_sub_type = _normalize_subagent_type_id(
                                    _coerce_tool_call_args(
                                        seen_tool_calls.get(tool_call_id, {}).get("args")
                                    ).get("subagent_type", "")
                                )
                                if _tc_sub_type == "deep-research":
                                    _out_for_sse = _sse_task_tool_output_deep_research(normalized_output)
                                else:
                                    _out_for_sse = _sse_task_tool_output_visible(normalized_output)
                            else:
                                _out_for_sse = normalized_output
                            yield _emit(
                                {
                                    "type": "tool_result",
                                    "id": tool_call_id,
                                    "toolName": tool_name,
                                    "toolOutput": _sse_tool_output(tool_name, _out_for_sse),
                                    "status": _derive_tool_status(normalized_output),
                                }
                            )

            if hitl_break_astream:
                break

    finally:
        async for _extra in _drain_subagent_sse_queue_tail():
            yield _extra
        async for _le in _drain_llm_lifecycle_nowait():
            yield _le

    _enqueue_synthetic_llm_invoke_end_before_close()
    for _ev in llm_emit.close():
        yield _ev
    # Drain must run AFTER enqueue+close, not inside the close() loop body
    # (close() returns [] when emit_boundaries=False, skipping any inner drain).
    async for _le in _drain_llm_lifecycle_nowait():
        yield _le

    if paused_for_hitl:
        yield _emit(
            {
                "type": "step",
                "id": "hitl-waiting",
                "label": get_stream_adapter_label("stream_hitl_waiting", language),
                "status": "waiting",
                "detail": "Human input required before the agent can continue.",
            }
        )
        yield _emit(
            {
                "type": "done",
                "id": "done",
                "awaitingHuman": True,
                "hitl": hitl_resume_meta,
            }
        )
        return

    # Conclusion must come from this stream only.
    # Do not read checkpoint state here, otherwise we can leak previous request output.
    final_response = latest_ai_text or None

    # Final AIMessage should contain ## SM_FULL_REPORT + ## SM_TASK_DIGEST (report-first;
    # legacy digest-first also accepted).  See MASTER_AGENT.md.
    # task_summary / conclusion are split from that single message (no extra LLM).
    if task_outputs and not final_response:
        final_response = "\n\n".join(task_outputs)

    def _conclusion_stats_meta(report_md: str) -> dict[str, Any] | None:
        """Derive `conclusion.meta` from accumulated run state. Never raises."""
        return build_task_stats_meta(
            subagent_types=task_output_subagent_types,
            tools_used=tools_used,
            task_outputs=task_outputs,
            report_markdown=report_md or "",
            security_findings_raw=security_findings_raw,
            language=language,
        )

    # Do NOT emit reasoning with final_response as fallback - that would show
    # synthesis/execution result in Reasoning Process. Conclusion carries final content.

    unresolved_fresh_task_ids = fresh_task_call_ids - task_result_call_ids
    has_unresolved_fresh_task = bool(unresolved_fresh_task_ids)

    if final_response and task_outputs:
        finalize_reason = "conclusion_with_task_outputs"
        all_deep_research_tasks = _all_task_outputs_are_deep_research(
            task_output_subagent_types,
            task_outputs,
        )
        # open_deep_research (task deep-research): user-visible answer already lives in the
        # subgraph; do not re-split the main model's follow-up synthesis (avoids duplicate
        # digest vs WRAPUP). Conclusion is derived only from task ToolMessage bodies.
        raw_final = (
            "\n\n".join(task_outputs)
            if all_deep_research_tasks
            else str(final_response)
        )
        digest, report = split_final_assistant_message(raw_final)
        if digest is not None and report is not None:
            summary_text = digest
            conclusion_body = report
        else:
            wrapup, full_sub = split_subagent_wrapup_and_full(raw_final)
            if wrapup is not None and full_sub is not None:
                # Subagent anchors: timeline toolOutput stays WRAPUP-only via _sse_task_tool_output_visible;
                # conclusion must carry FULL_REPORT body for workspace / persistence (not the short wrapup).
                summary_text = ""
                conclusion_body = full_sub
                logger.info(
                    "subagent_full_report_conclusion",
                    task_outputs_count=len(task_outputs),
                    wrapup_len=len(wrapup),
                    full_len=len(full_sub),
                )
            else:
                logger.info(
                    "digest_parse_miss",
                    task_outputs_count=len(task_outputs),
                    latest_ai_text_len=len(raw_final),
                )
                summary_text, conclusion_body = heuristic_digest_and_report(raw_final)
                logger.info(
                    "final_digest_heuristic_used",
                    digest_len=len(summary_text),
                    conclusion_len=len(conclusion_body),
                )
        if all_deep_research_tasks:
            summary_text = ""
        if summary_text.strip():
            yield _emit(
                {
                    "type": "task_summary",
                    "id": "task-summary",
                    "summary": summary_text.strip(),
                }
            )
        conc_raw = (conclusion_body.strip() if conclusion_body else raw_final.strip())
        _conc_event: dict[str, Any] = {
            "type": "conclusion",
            "id": "conclusion",
            "content": strip_leading_preface_before_cjk_report_body(
                strip_conclusion_machine_tails(conc_raw)
            ),
        }
        _meta = _conclusion_stats_meta(conc_raw)
        if _meta:
            _conc_event["meta"] = _meta
        yield _emit(_conc_event)
    elif final_response and not task_outputs:
        normalized_final = str(final_response).strip().lower()
        task_placeholder = any(
            ph in normalized_final for ph in get_task_submitted_placeholders()
        )
        if not (has_unresolved_fresh_task or task_placeholder):
            finalize_reason = "conclusion_without_tasks"
            _raw_final_text = str(final_response).strip()
            _conc_event = {
                "type": "conclusion",
                "id": "conclusion",
                "content": strip_leading_preface_before_cjk_report_body(
                    strip_conclusion_machine_tails(_raw_final_text)
                ),
            }
            _meta = _conclusion_stats_meta(_raw_final_text)
            if _meta:
                _conc_event["meta"] = _meta
            yield _emit(_conc_event)
        else:
            finalize_reason = "missing_subagent_result_placeholder"
            yield _emit(
                {
                    "type": "error",
                    "id": "missing-subagent-result",
                    "label": get_stream_adapter_label("stream_missing_subagent_outputs", language),
                    "status": "error",
                    "detail": get_stream_adapter_label("stream_missing_subagent_detail", language),
                }
            )
    elif saw_reasoning and latest_reasoning_text:
        finalize_reason = "reasoning_fallback_conclusion"
        # Fallback for providers that only stream reasoning/text events but no explicit
        # terminal AI message. Keeps UX from ending with "interrupted" placeholder.
        _reasoning_text = str(latest_reasoning_text).strip()
        _conc_event = {
            "type": "conclusion",
            "id": "conclusion",
            "content": strip_leading_preface_before_cjk_report_body(
                strip_conclusion_machine_tails(_reasoning_text)
            ),
        }
        _meta = _conclusion_stats_meta(_reasoning_text)
        if _meta:
            _conc_event["meta"] = _meta
        yield _emit(_conc_event)
    elif has_unresolved_fresh_task:
        finalize_reason = "missing_subagent_result_no_output"
        # A task() call happened but we have no final response and no usable task outputs.
        yield _emit(
            {
                "type": "error",
                "id": "missing-subagent-result",
                "label": get_stream_adapter_label("stream_missing_subagent_outputs", language),
                "status": "error",
                "detail": get_stream_adapter_label("stream_missing_subagent_detail", language),
            }
        )
    elif saw_any_tool_activity:
        finalize_reason = "tool_activity_without_terminal_output"
        # Tools executed but we still have no terminal response.
        # Emit explicit error so frontend does not fall back to generic "interrupted".
        yield _emit(
            {
                "type": "error",
                "id": "no-terminal-content",
                "label": "Analysis did not produce terminal content",
                "status": "error",
                "detail": (
                    "Tool activity was observed, but no final response was produced."
                ),
            }
        )
    else:
        finalize_reason = "no_terminal_content"

    logger.info(
        "Adapter finalize",
        finalize_reason=finalize_reason,
        total_stream_chunks=total_stream_chunks,
        node_event_counts=node_event_counts,
        total_agent_messages=total_agent_messages,
        total_ai_messages=total_ai_messages,
        empty_ai_messages=empty_ai_messages,
        saw_task_tool=saw_task_tool,
        saw_any_tool_activity=saw_any_tool_activity,
        saw_reasoning=saw_reasoning,
        fresh_task_calls=len(fresh_task_call_ids),
        task_result_calls=len(task_result_call_ids),
        unresolved_fresh_task_calls=len(unresolved_fresh_task_ids),
        task_outputs_count=len(task_outputs),
        latest_ai_text_len=len(latest_ai_text or ""),
        latest_reasoning_len=len(latest_reasoning_text or ""),
    )

    # Sub-agent bypass guard: main agent used tools but never delegated via task().
    # Skip when only allowed-direct tools were used (IOC lookup, info search, exploration).
    if saw_any_tool_activity and not saw_task_tool:
        if not tools_used.issubset(MAIN_AGENT_ALLOWED_DIRECT_TOOLS):
            yield _emit(
                {
                    "type": "warning",
                    "id": "subagent-bypass-detected",
                    "internal": True,
                    "label": get_stream_adapter_label("stream_subagent_bypass_label", language),
                    "detail": get_stream_adapter_label("stream_subagent_bypass_detail", language),
                }
            )

    # Auto-complete write_todos items still in pending/in_progress.
    # In deep-research shortcut the main agent skips the final LLM call,
    # so write_todos is never called again with "completed" status.
    for _tidx, _t in enumerate(_prev_todos):
        if not isinstance(_t, dict):
            continue
        _ts = str(_t.get("status", "")).strip().lower()
        if _ts in ("completed", "success"):
            continue
        _raw_tid = _t.get("id")
        _tid = str(_raw_tid) if _raw_tid not in (None, "") else str(_tidx)
        yield _emit(
            {
                "type": "task_complete",
                "id": _tid,
                "status": "success",
            }
        )

    yield _emit(
        {
            "type": "step",
            "id": "analysis-complete",
            "label": get_stream_adapter_label("stream_analysis_complete", language),
            "status": "success",
        }
    )

    yield _emit({"type": "done", "id": "done"})


def _skill_event_dict(
    event_type: str,
    *,
    step_id: str = "",
    label: str = "",
    status: str = "running",
    detail: str = "",
    tool_name: str = "",
    tool_input: dict | None = None,
    tool_output: str = "",
    subagent_name: str = "",
    phase: str = "subagent",
    is_synthetic: bool = False,
    observed_path: str = "",
    quality: str = "",
    reason_code: str = "",
) -> dict[str, Any]:
    """Build canonical SSE event dict (ThinkingEvent-compatible)."""
    ts = int(time.time() * 1000)
    sid = step_id or f"step-{ts}"
    return {
        "type": event_type,
        "id": sid,
        "label": label,
        "status": status,
        "detail": detail,
        "toolName": tool_name,
        "toolInput": tool_input or {},
        "toolOutput": tool_output,
        "subagentName": subagent_name,
        "phase": phase,
        "isSynthetic": is_synthetic,
        "observedPath": observed_path,
        "quality": quality,
        "reasonCode": reason_code,
        "timestamp": ts,
    }


async def adapt_subagent_astream_to_skill_events(
    subagent: Any,
    initial_state: dict[str, Any],
    config: dict[str, Any],
    *,
    skill_name: str = "",
    subagent_name: str = "",
    stream_mode: str = "updates",
    language: str = "en",
    sse_seq_counter: list[int] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Adapt subagent.astream() to SSE event dict stream for real-time tool visibility.

    Maps subagent agent/tools nodes to tool_call, tool_result, skill_complete events.
    Yields dict (ThinkingEvent-compatible) to avoid intermediate SkillEvent conversion.

    The final response is captured from the last non-tool-call AIMessage seen
    during the astream loop, eliminating the need for a second ainvoke() call
    that would execute the sub-agent a second time.

    Args:
        subagent: Compiled agent runnable with astream.
        initial_state: Initial state for subagent.
        config: LangGraph config.
        stream_mode: LangGraph stream mode.
        language: Language for localized labels (default: 'en').
        sse_seq_counter: When set (same mutable list as ``adapt_astream_to_sse`` uses),
            each yielded event is passed through ``_tag_merged_subagent_sse`` and
            ``_apply_sse_envelope`` so task-tool subruns share schemaVersion/seq/scope
            with the main SSE stream.

    Yields:
        Event dicts (tool_call, tool_result, skill_complete).
    """
    final_response = ""
    seen_tool_calls: dict[str, dict[str, Any]] = {}
    sub_turn = ReactTurnTracker()

    def _emit_subagent(ev: dict[str, Any]) -> dict[str, Any]:
        attach_turn_to_event(ev, sub_turn)
        attach_tool_presentation(ev)
        # Scrub internal paths before merge tagging + envelope application.
        # This guarantees tests reading the standalone stream (sse_seq_counter
        # is None) also see user-facing "workspace/..." style paths.
        ev = scrub_event(ev)
        if sse_seq_counter is None:
            return ev
        return apply_sse_envelope(tag_merged_subagent_sse(ev), sse_seq_counter)

    async for event in subagent.astream(
        initial_state, config, stream_mode=stream_mode
    ):
        if not isinstance(event, dict):
            continue
        for node_name, node_output in event.items():
            if node_name == "agent":
                messages = (
                    node_output.get("messages", [])
                    if isinstance(node_output, dict)
                    else []
                )
                for msg in messages:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for tc in msg.tool_calls:
                            if not isinstance(tc, dict):
                                continue
                            tc_id = tc.get("id", "")
                            tc_name = tc.get("name", "")
                            tc_args = _coerce_tool_call_args(tc.get("args"))
                            if tc_id:
                                prev = seen_tool_calls.get(tc_id)
                                if isinstance(prev, dict):
                                    old_a = prev.get("args") if isinstance(prev.get("args"), dict) else {}
                                    merged_args = {**dict(old_a), **tc_args}
                                    seen_tool_calls[tc_id] = {
                                        "name": tc_name or prev.get("name") or "",
                                        "args": merged_args,
                                    }
                                else:
                                    seen_tool_calls[tc_id] = {
                                        "name": tc_name,
                                        "args": tc_args,
                                    }
                            yield _emit_subagent(
                                _skill_event_dict(
                                    "tool_call",
                                    label=subagent_name or skill_name,
                                    tool_name=tc_name,
                                    tool_input=tc_args,
                                    step_id=tc_id,
                                    subagent_name=subagent_name,
                                )
                            )
                    elif isinstance(msg, AIMessage):
                        # Non-tool-call AI message = final response from sub-agent
                        _, text_str = _extract_thinking_and_text(msg)
                        if text_str:
                            final_response = text_str

            elif node_name == "tools":
                messages = (
                    node_output.get("messages", [])
                    if isinstance(node_output, dict)
                    else []
                )
                for msg in messages:
                    if hasattr(msg, "content"):
                        tool_call_id = getattr(msg, "tool_call_id", "")
                        # deepagents' _return_command_with_state_update creates ToolMessage
                        # without setting `name`.  Use seen_tool_calls as fallback.
                        tool_name = getattr(msg, "name", None) or (
                            seen_tool_calls.get(tool_call_id, {}).get("name")
                            if tool_call_id
                            else None
                        ) or ""
                        if tool_call_id and tool_call_id not in seen_tool_calls:
                            yield _emit_subagent(
                                _skill_event_dict(
                                    "tool_call",
                                    label=subagent_name or skill_name,
                                    tool_name=tool_name,
                                    tool_input={},
                                    step_id=tool_call_id,
                                    subagent_name=subagent_name,
                                    is_synthetic=True,
                                )
                            )
                            seen_tool_calls[tool_call_id] = {
                                "name": tool_name,
                                "args": {},
                            }
                        output_text = _extract_text(msg.content)
                        tool_input = (
                            _coerce_tool_call_args(
                                seen_tool_calls.get(tool_call_id, {}).get("args")
                            )
                            if tool_call_id
                            else {}
                        )
                        observed_path = ""
                        if isinstance(tool_input, dict):
                            observed_path = (
                                str(
                                    tool_input.get("path")
                                    or tool_input.get("file_path")
                                    or ""
                                ).strip()
                            )
                        yield _emit_subagent(
                            _skill_event_dict(
                                "tool_result",
                                label=subagent_name or skill_name,
                                status="success",
                                tool_name=tool_name,
                                tool_input=tool_input if isinstance(tool_input, dict) else {},
                                tool_output=_sse_tool_output(tool_name, output_text),
                                step_id=tool_call_id,
                                subagent_name=subagent_name,
                                observed_path=observed_path,
                            )
                        )

    if skill_name:
        suffix = get_stream_adapter_label("stream_skill_completed_suffix", language)
        label = f"{skill_name} {suffix}"
    else:
        label = get_stream_adapter_label("stream_skill_completed", language)
    visible_detail = subagent_sse_visible_text(final_response) if final_response else ""
    detail = visible_detail.strip() or get_stream_adapter_label(
        "stream_task_completed_fallback", language
    )
    yield _emit_subagent(
        _skill_event_dict(
            "skill_complete",
            label=label,
            status="success",
            detail=detail,
            subagent_name=subagent_name,
        )
    )
