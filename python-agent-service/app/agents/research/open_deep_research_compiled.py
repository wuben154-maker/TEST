"""CompiledSubAgent wrapper for open_deep_research graph."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Mapping

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda

from app._vendor.deepagents.middleware.subagents import CompiledSubAgent
from app.middleware.user_input_unwrap import unwrap_structured_user_prompt
from langgraph.errors import GraphBubbleUp
from langgraph.types import Interrupt, interrupt as langgraph_interrupt
from app.parsers.react_turn import ReactTurnTracker, attach_turn_to_event
from app.parsers.llm_invoke_sse import LlmInvokeEmitter
from app.parsers.llm_invoke_callbacks import (
    LlmInvokeLifecycleCallbackHandler,
    flatten_runnable_callbacks,
)
from app.agents.research.open_deep_research_original.deep_researcher import (
    deep_researcher as original_research_graph,
)
from app.agents.research.open_deep_research_original_adapter import (
    DeepResearchStreamExtractContext,
    _build_research_trace_report,
    _compose_research_conclusion,
    _extract_final_result_content,
    _extract_content_text,
    _extract_model_config_for_log,
    _write_research_run_log,
    format_research_tool_output_for_sse,
    normalize_research_brief_key,
    split_aimessage_thinking_and_visible,
)
from app.parsers.message_content import (
    aimessage_to_handoff_plain_text,
    content_blocks_to_plain_text,
    normalize_llm_visible_content,
)
from app.parsers.final_message_split import (
    SUBAGENT_WRAPUP_HEADING,
    _strip_stats_payload_tail,
)
from app.parsers.labels import get_stream_adapter_label
from app.parsers.llm_invoke_sse import llm_invoke_triplet

logger = structlog.get_logger()

# Four user-visible deep-research milestones (fixed order); see docs/SSE_EVENT_CATALOG.md §8.
_RESEARCH_PHASE_ORDER: tuple[str, ...] = (
    "deep_research_clarify",
    "deep_research_plan",
    "deep_research_collect",
    "deep_research_report",
)
_RESEARCH_PHASE_LABEL_KEYS: dict[str, str] = {
    "deep_research_clarify": "research_sse_phase_clarify",
    "deep_research_plan": "research_sse_phase_brief",
    "deep_research_collect": "research_sse_phase_collect",
    "deep_research_report": "research_sse_phase_final",
}
# Main-graph node completion -> (phase to mark success, next phase to mark running).
# Milestones are prepended before per-node debug rows in the same update so ordering is:
# clarify (pre-start) -> clarify_with_user -> plan (before write_research_brief) ->
# collect (before research_supervisor / nested compress_research) ->
# report (before final_report_generation).
_MAIN_GRAPH_PHASE_EDGES: dict[str, tuple[str | None, str | None]] = {
    "clarify_with_user": ("deep_research_clarify", "deep_research_plan"),
    "write_research_brief": ("deep_research_plan", "deep_research_collect"),
    "research_supervisor": ("deep_research_collect", "deep_research_report"),
    "final_report_generation": ("deep_research_report", None),
}

_PHASE_LABEL_KEYS: dict[str, str] = {
    "clarify_with_user": "research_sse_phase_clarify",
    "write_research_brief": "research_sse_phase_brief",
    "research_supervisor": "research_sse_phase_collect",
    "supervisor": "research_sse_phase_collect",
    "supervisor_tools": "research_sse_phase_collect",
    "researcher": "research_sse_phase_collect",
    "researcher_tools": "research_sse_phase_collect",
    "compress_research": "research_sse_phase_collect",
    "final_report_generation": "research_sse_phase_final",
}

_DRAFT_PHASE_NODES: frozenset[str] = frozenset(
    {
        "research_supervisor",
        "supervisor",
        "supervisor_tools",
        "researcher",
        "researcher_tools",
        "compress_research",
    }
)
_FINAL_PHASE_NODES: frozenset[str] = frozenset({"final_report_generation"})

# Nodes whose LLM token deltas, thinking, visible text, debug steps, tool_result,
# and non-ConductResearch tool_calls are suppressed from SSE.  Only ConductResearch
# tool_call / tool_result events pass through so the UI can show the work list.
# Includes researcher-level nodes because astream(subgraphs=True) penetrates through
# ainvoke() and exposes researcher internal events (web_search, LLM deltas, etc.).
_SUPERVISOR_SILENT_NODES: frozenset[str] = frozenset(
    {
        "supervisor",
        "supervisor_tools",
        "researcher",
        "researcher_tools",
        "compress_research",
    }
)

_REASONING_THINKING_CAP = 4000
_REASONING_VISIBLE_CAP = 12000
_HUMAN_DETAIL_CAP = 500
_WRAPUP_MAX_CHARS = 800


def _extract_research_wrapup(full_report: str) -> str:
    """Derive a concise WRAPUP from the research report (no LLM).

    Takes leading paragraph(s) up to ``_WRAPUP_MAX_CHARS``, breaking at a
    paragraph boundary when possible.  Returned text becomes the
    ``## SM_SUBAGENT_WRAPUP`` section so ``subagent_sse_visible_text``
    shows a meaningful preview instead of the entire body.
    """
    stripped = full_report.strip()
    if not stripped:
        return ""
    if len(stripped) <= _WRAPUP_MAX_CHARS:
        return stripped
    cutoff = stripped[:_WRAPUP_MAX_CHARS]
    last_para = cutoff.rfind("\n\n")
    if last_para > _WRAPUP_MAX_CHARS // 3:
        return cutoff[:last_para].rstrip()
    return cutoff.rstrip() + "\n..."


def _extract_visible_raw(msg: AIMessage) -> str:
    """Extract visible text from an AIMessage chunk **without stripping**.

    ``split_aimessage_thinking_and_visible`` strips each chunk, which destroys
    newlines at chunk boundaries.  When chunks are concatenated for later anchor
    parsing (``split_subagent_wrapup_and_full``), the lost newlines cause heading
    lines to merge with surrounding content and exact-match detection to fail.
    """
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "thinking" or block.get("thought") is True:
                continue
            text = block.get("text")
            if text is not None:
                parts.append(str(text))
        return "".join(parts)
    return str(content) if content else ""


def _emit_research_wrapup_sse_only(
    final_report_visible_buf: list[str],
    *,
    research_turn: ReactTurnTracker,
    push: Callable[[dict[str, Any]], None],
    llm_emitter: LlmInvokeEmitter | None = None,
) -> None:
    """Flush buffered final-report visible tokens as one SSE text invoke.

    When ``llm_emitter`` is provided, content is emitted through it so the
    ``llm_invoke_start`` already pushed on the first streaming token pairs
    correctly with this content and the subsequent ``llm_invoke_end`` from
    ``close()``.  Falls back to ``llm_invoke_triplet`` (standalone
    start→delta→end) when no emitter is given.

    When body-first or classic subagent anchors are present, only the WRAPUP section is
    emitted (keeps full report out of the SSE stream).  When anchors
    are absent (e.g. deep-research output without explicit anchors), the full text is used
    (capped to ``_REASONING_VISIBLE_CAP``) instead of ``subagent_sse_visible_text`` which
    would aggressively truncate to the first paragraph — reducing a multi-section research
    report to just the title line.
    """
    from app.parsers.final_message_split import split_subagent_wrapup_and_full

    raw = "".join(final_report_visible_buf).strip()
    final_report_visible_buf.clear()
    if not raw:
        return
    wrapup, _full = split_subagent_wrapup_and_full(raw)
    vis = wrapup.strip() if wrapup is not None and wrapup.strip() else raw
    if not vis.strip():
        return
    # Match subagent_sse_visible_text: never stream machine-only stats JSON to chat.
    vis = _strip_stats_payload_tail(vis).strip()
    if not vis.strip():
        return
    capped = _cap_stream_text(vis.strip(), _REASONING_VISIBLE_CAP)
    if llm_emitter is not None:
        llm_emitter.delta("text", capped)
    else:
        for ev in llm_invoke_triplet("text", capped):
            attach_turn_to_event(ev, research_turn)
            push(ev)


def _clarify_user_visible_text(text: str) -> str:
    """Delegate to the unified normalizer in ``message_content``."""
    return normalize_llm_visible_content(text)


def _phase_step_label(node_name: str, lang: str) -> str:
    key = _PHASE_LABEL_KEYS.get(node_name, "research_sse_phase_step")
    return get_stream_adapter_label(key, lang)


def _cap_stream_text(text: str, limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: max(0, limit - 1)] + "…"


def _phase_milestone_dict(
    phase_id: str,
    status: str,
    lang: str,
    *,
    id_suffix: str,
) -> dict[str, Any]:
    idx = _RESEARCH_PHASE_ORDER.index(phase_id)
    return {
        "type": "step",
        "id": f"dr-phase-{phase_id}-{id_suffix}",
        "phaseId": phase_id,
        "phaseIndex": idx,
        "label": get_stream_adapter_label(_RESEARCH_PHASE_LABEL_KEYS[phase_id], lang),
        "status": status,
        "subagentName": "deep-research",
        "researchSubgraph": True,
    }


def _emit_phase_running(
    out: list[dict[str, Any]],
    ctx: DeepResearchStreamExtractContext,
    phase_id: str,
    lang: str,
) -> None:
    key = f"{phase_id}:running"
    if key in ctx.research_phase_markers_done:
        return
    ctx.research_phase_markers_done.add(key)
    ctx.emitted_research_phase_ids.add(phase_id)
    out.append(_phase_milestone_dict(phase_id, "running", lang, id_suffix="running"))


def _emit_phase_success(
    out: list[dict[str, Any]],
    ctx: DeepResearchStreamExtractContext,
    phase_id: str,
    lang: str,
) -> None:
    key = f"{phase_id}:success"
    if key in ctx.research_phase_markers_done:
        return
    ctx.research_phase_markers_done.add(key)
    ctx.emitted_research_phase_ids.add(phase_id)
    out.append(_phase_milestone_dict(phase_id, "success", lang, id_suffix="success"))


def _deep_research_clarify_pre_start_event(
    lang: str, ctx: DeepResearchStreamExtractContext
) -> dict[str, Any]:
    """``deep_research_clarify`` running before ``clarify_with_user`` executes (graph entry)."""
    key = "deep_research_clarify:running"
    ev = _phase_milestone_dict("deep_research_clarify", "running", lang, id_suffix="pre")
    ev["id"] = "dr-pre-clarify"
    if key not in ctx.research_phase_markers_done:
        ctx.research_phase_markers_done.add(key)
        ctx.emitted_research_phase_ids.add("deep_research_clarify")
    return ev


def _research_phase_transition_events(
    update: dict[str, Any],
    ctx: DeepResearchStreamExtractContext,
    lang: str,
) -> list[dict[str, Any]]:
    """Leading-edge phase steps: success for the phase that just finished, then running for the next.

    Uses only top-level main-graph node keys from ``stream_mode='updates'`` chunks so nested
    nodes (e.g. ``compress_research``) do not advance the four-slot UI timeline.
    """
    out: list[dict[str, Any]] = []
    for node_name, edges in _MAIN_GRAPH_PHASE_EDGES.items():
        if node_name not in update:
            continue
        done_key = f"main_graph_done:{node_name}"
        if done_key in ctx.research_phase_markers_done:
            continue
        ctx.research_phase_markers_done.add(done_key)

        success_phase, next_running = edges
        if success_phase:
            _emit_phase_success(out, ctx, success_phase, lang)
        if next_running:
            _emit_phase_running(out, ctx, next_running, lang)
    return out


def push_skipped_research_phase_milestones(
    ctx: DeepResearchStreamExtractContext,
    lang: str,
    push: Callable[[dict[str, Any]], None],
    research_turn: ReactTurnTracker,
) -> None:
    """Emit skipped milestones for phases never entered (fixed four slots)."""
    for i, phase_id in enumerate(_RESEARCH_PHASE_ORDER):
        if phase_id in ctx.emitted_research_phase_ids:
            continue
        ev: dict[str, Any] = {
            "type": "step",
            "id": f"dr-phase-{phase_id}-skipped",
            "phaseId": phase_id,
            "phaseIndex": i,
            "label": get_stream_adapter_label(_RESEARCH_PHASE_LABEL_KEYS[phase_id], lang),
            "status": "skipped",
            "subagentName": "deep-research",
            "researchSubgraph": True,
        }
        attach_turn_to_event(ev, research_turn)
        push(ev)
        ctx.emitted_research_phase_ids.add(phase_id)


def _extract_stream_events(
    update: dict[str, Any],
    ctx: DeepResearchStreamExtractContext,
    *,
    skip_llm_content: bool = False,
) -> list[dict[str, Any]]:
    """Extract canonical SSE-shaped events from graph ``stream_mode=\"updates\"`` chunks.

    Omits built-in system prompts; dedupes repeated research-brief human input; splits
    thinking vs visible text; normalizes delegation tool output. See OpenSpec change
    ``deep-research-sse-plaintext-cleanup``.

    Main-graph phase ``step`` milestones use leading edges (prepended before debug rows):
    clarify pre-start is separate; each of ``clarify_with_user`` / ``write_research_brief`` /
    ``research_supervisor`` / ``final_report_generation`` completion emits success for the
    finished phase and ``running`` for the next.

    When ``skip_llm_content=True`` the llm_invoke_start/delta/end triplets for AIMessage
    thinking/text are skipped because the caller already streamed them token-by-token via
    LlmInvokeEmitter.  tool_call/tool_result/step events are still emitted.

    Nodes in ``_SUPERVISOR_SILENT_NODES`` are fully suppressed except for
    ``ConductResearch`` tool_call events (the UI work list).
    """
    events: list[dict[str, Any]] = []
    lang = ctx.ui_language

    events.extend(_research_phase_transition_events(update, ctx, lang))

    for node_name, node_output in update.items():
        if not isinstance(node_output, dict):
            continue

        _is_silent = node_name in _SUPERVISOR_SILENT_NODES
        _has_phase_edge = node_name in _MAIN_GRAPH_PHASE_EDGES

        if not _is_silent and not _has_phase_edge:
            events.append(
                {
                    "type": "step",
                    "id": f"debug-node-{node_name}",
                    "visibility": "debug",
                    "internal": True,
                    "label": _phase_step_label(node_name, lang),
                    "node": node_name,
                    "status": "running",
                }
            )

        message_lists: list[tuple[str, list[Any]]] = []
        for key in ("messages", "supervisor_messages", "researcher_messages"):
            value = node_output.get(key)
            if isinstance(value, list):
                message_lists.append((key, value))
            elif isinstance(value, dict) and value.get("type") == "override":
                override_value = value.get("value")
                if isinstance(override_value, list):
                    message_lists.append((key, override_value))

        think_lbl = get_stream_adapter_label("research_sse_prefix_thinking", lang)
        ans_lbl = get_stream_adapter_label("research_sse_prefix_answer", lang)
        draft_lbl = get_stream_adapter_label("research_sse_prefix_draft_findings", lang)
        final_lbl = get_stream_adapter_label("research_sse_prefix_final_prep", lang)

        for msg_key, messages in message_lists:
            for msg in messages:
                if isinstance(msg, SystemMessage):
                    continue

                # Silent nodes: only ConductResearch tool_call and tool_result pass.
                if _is_silent:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for tc in msg.tool_calls:
                            td = tc if isinstance(tc, dict) else {}
                            if not td and tc is not None:
                                td = {
                                    "id": getattr(tc, "id", ""),
                                    "name": getattr(tc, "name", ""),
                                    "args": getattr(tc, "args", None) or {},
                                }
                            tc_name = str(td.get("name", "") or "")
                            if tc_name != "ConductResearch":
                                continue
                            tc_id = str(td.get("id", "") or "")
                            if tc_id and tc_id in ctx.emitted_tool_call_sse_ids:
                                continue
                            if tc_id:
                                ctx.emitted_tool_call_sse_ids.add(tc_id)
                            events.append(
                                {
                                    "type": "tool_call",
                                    "id": td.get("id", ""),
                                    "toolName": tc_name,
                                    "toolInput": td.get("args", {}) or {},
                                    "node": node_name,
                                    "status": "running",
                                }
                            )
                    elif isinstance(msg, ToolMessage):
                        tool_name = getattr(msg, "name", "") or ""
                        if tool_name == "ConductResearch":
                            out = format_research_tool_output_for_sse(
                                msg.content,
                                tool_name=tool_name,
                                ui_language=lang,
                                limit=4000,
                            )
                            events.append(
                                {
                                    "type": "tool_result",
                                    "id": getattr(msg, "tool_call_id", ""),
                                    "toolName": tool_name,
                                    "toolOutput": out,
                                    "node": node_name,
                                    "status": "success",
                                }
                            )
                    continue

                if isinstance(msg, HumanMessage):
                    content_text = _extract_content_text(msg.content)
                    if not content_text:
                        continue
                    norm = normalize_research_brief_key(content_text)
                    if ctx.brief_norm_from_write and norm == ctx.brief_norm_from_write:
                        if node_name in ("research_supervisor", "supervisor"):
                            continue
                    detail = _cap_stream_text(content_text, _HUMAN_DETAIL_CAP)
                    events.append(
                        {
                            "type": "step",
                            "id": f"debug-input-{node_name}-{msg_key}",
                            "visibility": "debug",
                            "internal": True,
                            "label": get_stream_adapter_label("research_sse_human_input", lang),
                            "node": node_name,
                            "status": "success",
                            "detail": detail,
                            "source": msg_key,
                        }
                    )
                    if node_name == "write_research_brief" and msg_key == "supervisor_messages":
                        ctx.brief_norm_from_write = norm
                    continue

                if isinstance(msg, AIMessage):
                    if not skip_llm_content:
                        thinking, visible = split_aimessage_thinking_and_visible(msg)
                        # Emit usage on **only one** triplet per message so the
                        # realtime indicator's cumulative counter doesn't double.
                        # Prefer the visible triplet (user-facing turn); fall
                        # back to reasoning if there is no visible content.
                        _msg_usage = getattr(msg, "usage_metadata", None)
                        if thinking:
                            events.extend(
                                llm_invoke_triplet(
                                    "reasoning",
                                    f"{think_lbl}\n{_cap_stream_text(thinking, _REASONING_THINKING_CAP)}",
                                    extra={"node": node_name, "source": msg_key},
                                    usage=_msg_usage if not visible else None,
                                )
                            )
                        if visible:
                            if node_name in _FINAL_PHASE_NODES:
                                body = f"{final_lbl}\n{_cap_stream_text(visible, _REASONING_VISIBLE_CAP)}"
                            elif node_name in _DRAFT_PHASE_NODES:
                                body = f"{draft_lbl}\n{_cap_stream_text(visible, _REASONING_VISIBLE_CAP)}"
                            else:
                                body = f"{ans_lbl}\n{_cap_stream_text(visible, _REASONING_VISIBLE_CAP)}"
                            events.extend(
                                llm_invoke_triplet(
                                    "text",
                                    body,
                                    extra={"node": node_name, "source": msg_key},
                                    usage=_msg_usage,
                                )
                            )

                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            td = tc if isinstance(tc, dict) else {}
                            if not td and tc is not None:
                                td = {
                                    "id": getattr(tc, "id", ""),
                                    "name": getattr(tc, "name", ""),
                                    "args": getattr(tc, "args", None) or {},
                                }
                            tc_id = str(td.get("id", "") or "")
                            if tc_id and tc_id in ctx.emitted_tool_call_sse_ids:
                                continue
                            if tc_id:
                                ctx.emitted_tool_call_sse_ids.add(tc_id)
                            events.append(
                                {
                                    "type": "tool_call",
                                    "id": td.get("id", ""),
                                    "toolName": td.get("name", ""),
                                    "toolInput": td.get("args", {}) or {},
                                    "node": node_name,
                                    "status": "running",
                                }
                            )
                    continue

                if isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, "name", "") or ""
                    out = format_research_tool_output_for_sse(
                        msg.content,
                        tool_name=tool_name or "unknown",
                        ui_language=lang,
                        limit=4000,
                    )
                    events.append(
                        {
                            "type": "tool_result",
                            "id": getattr(msg, "tool_call_id", ""),
                            "toolName": tool_name,
                            "toolOutput": out,
                            "node": node_name,
                            "status": "success",
                        }
                    )

    return events


def _extract_query_from_state(state: dict[str, Any]) -> str:
    """Extract latest human message content as subagent query."""
    messages = state.get("messages")
    if not isinstance(messages, list):
        return ""

    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return _extract_content_text(msg.content).strip()
        content = getattr(msg, "content", None)
        if content is not None:
            text = _extract_content_text(content).strip()
            if text:
                return text
    return ""


_CONTEXT_SEPARATOR = "---CONTEXT---"
_ORIGINAL_QUERY_PREFIX = "ORIGINAL_QUERY:"


def parse_layered_task_description(raw_query: str) -> tuple[str, str]:
    """Split a layered deep-research task description into (original_query, explore_context).

    The main agent formats its ``task(deep-research)`` description as::

        ORIGINAL_QUERY: <user's verbatim question>
        ---CONTEXT---
        <preliminary explore findings>

    Returns ``(original_query, explore_context)`` where *explore_context* may be
    empty if the separator is absent (backward compatible).
    """
    if _CONTEXT_SEPARATOR in raw_query:
        before, after = raw_query.split(_CONTEXT_SEPARATOR, 1)
        original = before.strip()
        context = after.strip()
    else:
        original = raw_query.strip()
        context = ""

    if original.upper().startswith(_ORIGINAL_QUERY_PREFIX.upper()):
        original = original[len(_ORIGINAL_QUERY_PREFIX):].strip()

    return original, context


def _build_layered_research_messages(raw_query: str) -> list:
    """Build the initial messages list for the research graph.

    When the task description uses the layered format, the user's original
    question becomes a ``HumanMessage`` and the explore context becomes a
    separate ``SystemMessage`` clearly marked as preliminary / unverified.
    This lets ``clarify_with_user`` judge clarity based on the *original*
    question rather than the enriched (and possibly inaccurate) version.
    """
    original, context = parse_layered_task_description(raw_query)
    if not original:
        original = raw_query.strip()

    messages: list = [HumanMessage(content=original)]

    if context:
        messages.append(
            SystemMessage(
                content=(
                    "[Preliminary context from routing agent — may contain inaccuracies. "
                    "Verify independently before relying on specific claims, CVE numbers, "
                    "or attributions.]\n\n"
                    + context
                )
            )
        )

    return messages


def _extract_final_text(result: dict[str, Any]) -> str:
    """Extract final report text from graph result.

    ``messages[-1]`` is unreliable: ``MessagesState`` appends many turns; the tail may be
    a ``ToolMessage`` or a short non-final ``AIMessage``. Prefer ``final_report`` from
    ``final_report_generation``. For list-shaped content, merge thinking + text blocks.

    Fallback: newest-first scan for the last ``AIMessage`` without ``tool_calls``.
    """
    final_report = result.get("final_report")
    if final_report:
        text = content_blocks_to_plain_text(final_report).strip()
        if text:
            return text

    messages = result.get("messages")
    if isinstance(messages, list) and messages:
        for msg in reversed(messages):
            if not isinstance(msg, AIMessage):
                continue
            if getattr(msg, "tool_calls", None):
                continue
            text = aimessage_to_handoff_plain_text(msg).strip()
            if text:
                return text

        last = messages[-1]
        text = content_blocks_to_plain_text(getattr(last, "content", "")).strip()
        if text:
            return text
    return ""


def _get_token_events(config: RunnableConfig | None) -> list[dict[str, Any]]:
    """Read collected token usage events from runnable config."""
    if not isinstance(config, dict):
        return []
    configurable = config.get("configurable", {})
    if not isinstance(configurable, dict):
        return []
    token_events = configurable.get("token_usage_events", [])
    return token_events if isinstance(token_events, list) else []


async def stream_researcher_subgraph_with_sse(
    researcher_graph: Any,
    initial_state: Mapping[str, Any],
    config: RunnableConfig | None,
    *,
    research_unit_topic: str = "",
) -> dict[str, Any]:
    """Run the per-topic researcher subgraph for ConductResearch via ``ainvoke`` only.

    Nested researcher execution used to mirror the main graph with ``astream`` and push
    tool/LLM events into ``subagent_sse_event_queue``; that produced too much SSE noise.
    The queue/writer in ``config`` are ignored here; only the final compressed output is
    returned to the supervisor (same as historical ``ainvoke`` behavior).

    ``research_unit_topic`` is kept for call-site compatibility; it is unused.
    """
    _ = research_unit_topic
    result = await researcher_graph.ainvoke(dict(initial_state), config=config)
    compressed = result.get("compressed_research")
    compressed_str = str(compressed).strip() if compressed is not None else ""

    raw_notes_val = result.get("raw_notes", [])
    if isinstance(raw_notes_val, list):
        raw_notes_out: list[Any] = list(raw_notes_val)
    elif raw_notes_val:
        raw_notes_out = [str(raw_notes_val)]
    else:
        raw_notes_out = []

    return {
        "compressed_research": compressed_str,
        "raw_notes": raw_notes_out,
    }


async def _run_open_deep_research_subagent(
    state: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Run open_deep_research graph as a CompiledSubAgent runnable.

    Uses astream() to capture intermediate events (tool_call, tool_result, reasoning).
    If config contains an 'event_queue' in configurable, events are pushed to it
    for real-time streaming to the frontend.
    """
    started_at = datetime.now()
    query = _extract_query_from_state(state)
    research_input_messages = _build_layered_research_messages(query)
    final_text = ""
    trace_report = ""
    run_status = "success"
    run_error = ""
    reasoning_snippets: list[str] = []
    result: dict[str, Any] = {}
    clarify_raw_visible: list[str] = []

    # Get event queue from config if provided (for streaming intermediate events)
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    # Merged into main SSE when adapt_astream_to_sse sets subagent_sse_event_queue
    event_queue: asyncio.Queue | None = (
        configurable.get("subagent_sse_event_queue")
        or configurable.get("event_queue")
    )
    # Path A: subagents.py injects stream_writer into configurable so we can
    # deliver events in real-time via LangGraph's ToolRuntime, bypassing the
    # asyncio.Queue relay that was the bottleneck for delayed output.
    _stream_writer = configurable.get("subagent_stream_writer")

    def _push(ev: dict) -> None:
        """Deliver one SSE event via stream_writer (real-time) or queue (fallback)."""
        if _stream_writer is not None:
            try:
                _stream_writer(ev)
            except Exception:
                pass
        elif event_queue is not None:
            try:
                event_queue.put_nowait(ev)
            except asyncio.QueueFull:
                logger.warning("Event queue full, dropping event", event_type=ev.get("type"))

    research_turn = ReactTurnTracker()

    logger.info(
        "Research subagent execution started",
        research_mode="compiled_subagent",
        query_preview=query[:120],
        has_event_queue=event_queue is not None,
        has_stream_writer=_stream_writer is not None,
    )

    _ui_lang = str(configurable.get("sse_ui_language") or "zh")
    stream_ctx = DeepResearchStreamExtractContext(ui_language=_ui_lang)
    _pre_clarify_step = _deep_research_clarify_pre_start_event(_ui_lang, stream_ctx)
    attach_turn_to_event(_pre_clarify_step, research_turn)
    _push(_pre_clarify_step)

    # LlmInvokeEmitter provides real-time start→delta→end boundaries for every LLM
    # call inside the research graph.  emit_boundaries=True means the emitter itself
    # issues llm_invoke_start on the first non-empty token and llm_invoke_end on close().
    def _emit_llm_ev(ev: dict[str, Any]) -> dict[str, Any]:
        attach_turn_to_event(ev, research_turn)
        _push(ev)
        return ev

    research_llm_emit = LlmInvokeEmitter(_emit_llm_ev, emit_boundaries=True)
    _active_chunk_id: str | None = None
    _final_report_visible_buf: list[str] = []
    _write_brief_visible_buf: list[str] = []
    # SECMANUS PATCH (deep-research-subagent-usage-attribution):
    # AIMessageChunk.usage_metadata only appears on the terminating chunk of a
    # streaming LLM call. Buffer it per chunk_id so close() can forward the
    # final usage to llm_invoke_end, letting the realtime context-usage
    # popover attribute tokens to this subagent (prior to this the end event
    # carried no `usage` field → frontend reducer short-circuited → empty
    # bySubagent bucket → "No subagent activity yet"). Mirrors the sibling
    # attribution path already present in _extract_stream_events().
    _pending_usage_by_chunk_id: dict[str, Any] = {}

    def _pop_pending_usage() -> Any | None:
        """Return usage metadata cached for ``_active_chunk_id`` (if any)."""
        if not _active_chunk_id:
            return None
        return _pending_usage_by_chunk_id.pop(_active_chunk_id, None)

    def _flush_write_brief_visible_for_sse() -> bool:
        """Flush buffered write_brief visible text. Returns True if content was emitted."""
        if not _write_brief_visible_buf:
            return False
        joined = "".join(_write_brief_visible_buf)
        _write_brief_visible_buf.clear()
        unwrapped = unwrap_structured_user_prompt(joined)
        if not (unwrapped or "").strip():
            return False
        research_llm_emit.delta(
            "text", _cap_stream_text(unwrapped, _REASONING_VISIBLE_CAP)
        )
        return True

    # Strip parent adapter's LlmInvokeLifecycleCallbackHandler from config.
    # The parent injects it for the main agent graph, but when it propagates
    # into the research graph it fires llm_invoke_start/end for every internal
    # LLM call (including researcher ainvoke), producing orphan SSE events.
    # research_llm_emit (emit_boundaries=True) is the sole boundary source here.
    _research_config = dict(config) if config else {}
    _existing_cbs = flatten_runnable_callbacks(_research_config.get("callbacks"))
    _filtered_cbs = [
        cb for cb in _existing_cbs
        if not isinstance(cb, LlmInvokeLifecycleCallbackHandler)
    ]
    if len(_filtered_cbs) != len(_existing_cbs):
        _research_config["callbacks"] = _filtered_cbs

    _HITL_MAX_CLARIFY_RERUNS = 3
    _hitl_bubble_up = False

    try:
      for _hitl_run_idx in range(_HITL_MAX_CLARIFY_RERUNS + 1):
        _hitl_interrupted = False
        _hitl_user_reply: str | None = None

        if _hitl_run_idx > 0:
            logger.info(
                "HITL clarification resolved — re-running research graph",
                run_idx=_hitl_run_idx,
                reply_len=len(research_input_messages[-1].content if research_input_messages else ""),
            )
            result = {}
            clarify_raw_visible = []
            stream_ctx = DeepResearchStreamExtractContext(ui_language=_ui_lang)
            research_llm_emit = LlmInvokeEmitter(_emit_llm_ev, emit_boundaries=True)
            _active_chunk_id = None
            _final_report_visible_buf = []
            _write_brief_visible_buf = []
            # SECMANUS PATCH: drop usage cached from the aborted first run so
            # the re-run's llm_invoke_end never inherits stale token counts.
            _pending_usage_by_chunk_id.clear()

        # stream_mode=["messages","updates"]:
        #   "messages" chunks → token-level LLM output → feed into research_llm_emit
        #   "updates" chunks  → node completion → close current invoke, emit structural events
        async for raw_event in original_research_graph.astream(
            {"messages": research_input_messages},
            config=_research_config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            # LangGraph with stream_mode=list:
            # - subgraphs=False: (mode, data) tuples
            # - subgraphs=True: (namespace, mode, data) — required so supervisor/researcher
            #   nested LLM streams and per-inner-node updates reach _push() in real time.
            # Dict-shaped chunks are accepted for forward compatibility.
            if isinstance(raw_event, tuple):
                if len(raw_event) == 3:
                    _, event_type, event_data = raw_event
                elif len(raw_event) == 2:
                    event_type, event_data = raw_event
                else:
                    continue
            elif isinstance(raw_event, dict):
                event_type = raw_event.get("type")
                event_data = raw_event.get("data")
            else:
                continue

            if event_type == "messages" and event_data is not None:
                chunk, metadata = (
                    event_data
                    if isinstance(event_data, (tuple, list)) and len(event_data) >= 2
                    else (event_data, {})
                )

                # Only AIMessage/AIMessageChunk carry LLM output and tool_calls.
                # SystemMessage (prompts) and HumanMessage (briefs) added to state
                # also appear in the messages stream but must be discarded here;
                # structural events for those are handled in the updates stream.
                if not isinstance(chunk, AIMessage):
                    continue

                node_name = (
                    str((metadata or {}).get("langgraph_node") or "")
                    if isinstance(metadata, dict)
                    else ""
                )
                chunk_id = getattr(chunk, "id", None)

                # SECMANUS PATCH: buffer usage from the terminating streaming
                # chunk keyed by chunk_id so the upcoming close() can forward
                # it on llm_invoke_end. Skipped when the chunk is silent or
                # carries no usage_metadata; last-write-wins on collisions
                # (LangChain only populates usage on the final chunk, so the
                # overwrite here matches per-call semantics).
                _chunk_usage = getattr(chunk, "usage_metadata", None)
                if chunk_id and _chunk_usage:
                    _pending_usage_by_chunk_id[chunk_id] = _chunk_usage

                _is_silent = node_name in _SUPERVISOR_SILENT_NODES

                # When the chunk ID changes a new LLM call began — close the previous invoke.
                if chunk_id and chunk_id != _active_chunk_id:
                    if _active_chunk_id is not None:
                        _flush_write_brief_visible_for_sse()
                        research_llm_emit.close(usage=_pop_pending_usage())
                    _active_chunk_id = chunk_id

                if not _is_silent:
                    thinking, visible = split_aimessage_thinking_and_visible(chunk)
                    if thinking:
                        snippet = _cap_stream_text(thinking, _REASONING_THINKING_CAP)
                        reasoning_snippets.append(snippet)
                        research_llm_emit.delta("reasoning", snippet)

                    # Buffers that are joined later for anchor parsing need raw
                    # (unstripped) content so newlines at chunk boundaries survive.
                    if node_name == "final_report_generation":
                        raw_vis = _extract_visible_raw(chunk)
                        if raw_vis:
                            _final_report_visible_buf.append(raw_vis)
                            if not research_llm_emit.is_open:
                                _iid = uuid.uuid4().hex[:12]
                                research_llm_emit.pre_open(_iid, int(time.time() * 1000))
                    elif node_name == "write_research_brief":
                        raw_vis = _extract_visible_raw(chunk)
                        if raw_vis:
                            _write_brief_visible_buf.append(raw_vis)
                    elif visible:
                        if node_name == "clarify_with_user":
                            clarify_raw_visible.append(str(visible))
                        else:
                            research_llm_emit.delta("text", _cap_stream_text(visible, _REASONING_VISIBLE_CAP))

                # Emit ConductResearch tool_call eagerly (before the matching updates
                # chunk) so the UI shows the work list while the researcher runs.
                # For silent nodes only ConductResearch passes; all others are suppressed.
                if isinstance(chunk, AIMessage) and getattr(chunk, "tool_calls", None):
                    for tc in chunk.tool_calls or []:
                        td = tc if isinstance(tc, dict) else {}
                        if not td and tc is not None:
                            td = {
                                "id": getattr(tc, "id", ""),
                                "name": getattr(tc, "name", ""),
                                "args": getattr(tc, "args", None) or {},
                            }
                        tc_name = str(td.get("name", "") or "")
                        if _is_silent and tc_name != "ConductResearch":
                            continue
                        tc_id = str(td.get("id", "") or "")
                        if not tc_id or tc_id in stream_ctx.emitted_tool_call_sse_ids:
                            continue
                        # LangChain treats tool_call_chunks with args="" as args={}
                        # on the first streaming chunk.  Skip empty-args emissions
                        # from the messages stream — the updates stream will emit
                        # the complete tool_call with real arguments later.
                        tc_args = td.get("args") or {}
                        if not tc_args:
                            continue
                        stream_ctx.emitted_tool_call_sse_ids.add(tc_id)
                        _tc_ev: dict[str, Any] = {
                            "type": "tool_call",
                            "id": tc_id,
                            "toolName": tc_name,
                            "toolInput": tc_args,
                            "node": node_name,
                            "status": "running",
                        }
                        attach_turn_to_event(_tc_ev, research_turn)
                        _push(_tc_ev)

            elif event_type == "updates" and isinstance(event_data, dict):
                # ── HITL: detect __interrupt__ from clarify_with_user ──
                _intr_data = event_data.get("__interrupt__")
                if _intr_data is not None:
                    _flush_write_brief_visible_for_sse()
                    research_llm_emit.close(usage=_pop_pending_usage())
                    _active_chunk_id = None
                    intr_list = list(_intr_data) if isinstance(_intr_data, (list, tuple)) else [_intr_data]
                    for intr_obj in intr_list:
                        if not isinstance(intr_obj, Interrupt):
                            continue
                        logger.info(
                            "Deep-research subgraph interrupted (HITL clarification)",
                            interrupt_id=intr_obj.id,
                            run_idx=_hitl_run_idx,
                        )
                        resume_val = langgraph_interrupt(intr_obj.value)
                        if isinstance(resume_val, dict):
                            _hitl_user_reply = str(
                                resume_val.get("response")
                                or resume_val.get("reply")
                                or resume_val.get("answer")
                                or ""
                            ).strip()
                        else:
                            _hitl_user_reply = str(resume_val or "").strip()
                        _hitl_interrupted = True
                        break
                    if _hitl_interrupted:
                        break
                    logger.warning(
                        "__interrupt__ in research stream without Interrupt objects",
                        data_type=type(_intr_data).__name__,
                    )
                    continue

                # Node completed — flush final-report wrapup through the open
                # emitter BEFORE close() so llm_invoke_start (eagerly pushed on
                # the first streaming token) pairs with this content.
                _brief_flushed = _flush_write_brief_visible_for_sse()
                if "final_report_generation" in event_data:
                    _emit_research_wrapup_sse_only(
                        _final_report_visible_buf,
                        research_turn=research_turn,
                        push=_push,
                        llm_emitter=research_llm_emit,
                    )
                research_llm_emit.close(usage=_pop_pending_usage())
                _active_chunk_id = None

                # Fallback: when write_research_brief uses structured output
                # via function_calling, the LLM response lives in tool_calls
                # (not content), so the streaming buffer stays empty.  Extract
                # the brief from the node update and emit it directly.
                if "write_research_brief" in event_data and not _brief_flushed:
                    _wb_data = event_data.get("write_research_brief")
                    _wb_brief = (
                        _wb_data.get("research_brief", "")
                        if isinstance(_wb_data, dict)
                        else ""
                    )
                    if isinstance(_wb_brief, str) and _wb_brief.strip():
                        for _wb_ev in llm_invoke_triplet(
                            "text",
                            _cap_stream_text(_wb_brief, _REASONING_VISIBLE_CAP),
                        ):
                            attach_turn_to_event(_wb_ev, research_turn)
                            _push(_wb_ev)

                # Flush node-specific visible buffers BEFORE phase transitions
                # so phase content appears before the next phase's "running" marker.
                if "clarify_with_user" in event_data and clarify_raw_visible:
                    clarify_text = _clarify_user_visible_text("".join(clarify_raw_visible))
                    clarify_raw_visible.clear()
                    if clarify_text:
                        for ev in llm_invoke_triplet("text", _cap_stream_text(clarify_text, _REASONING_VISIBLE_CAP)):
                            attach_turn_to_event(ev, research_turn)
                            _push(ev)

                # Emit structural events (tool_call, tool_result, step markers, phases).
                # skip_llm_content=True because llm content was already streamed above.
                stream_events = _extract_stream_events(
                    event_data, stream_ctx, skip_llm_content=True
                )
                for evt in stream_events:
                    attach_turn_to_event(evt, research_turn)
                    _push(evt)

                # Update accumulated result for final extraction.
                for _node_name, node_output in event_data.items():
                    if isinstance(node_output, dict):
                        result.update(node_output)

        # ── After astream: decide whether to re-run or finalise ──
        if _hitl_interrupted:
            if _hitl_user_reply:
                research_input_messages.append(HumanMessage(content=_hitl_user_reply))
            continue  # next iteration re-runs the research graph

        # Normal completion — exit the for loop and proceed to post-processing.
        break

      # ── Post-loop: finalise result (runs after normal break OR exhausted reruns) ──
      _flush_write_brief_visible_for_sse()
      _emit_research_wrapup_sse_only(
          _final_report_visible_buf,
          research_turn=research_turn,
          push=_push,
          llm_emitter=research_llm_emit,
      )
      research_llm_emit.close(usage=_pop_pending_usage())

      extracted_final = _extract_final_text(result).strip()
      if extracted_final:
          final_text = extracted_final

      token_events = _get_token_events(config)
      trace_report = _build_research_trace_report(
          ui_language="zh",
          token_events=token_events,
          reasoning_snippets=reasoning_snippets,
      )
      final_text = _compose_research_conclusion(
          ui_language="zh",
          trace_report=trace_report,
          final_text=final_text,
      )
      final_text = _extract_final_result_content(final_text, "zh")

      from app.parsers.final_message_split import split_subagent_wrapup_and_full

      _existing_w, _existing_f = split_subagent_wrapup_and_full(final_text)
      if _existing_w is not None and _existing_f is not None:
          anchored = final_text
      else:
          wrapup = _extract_research_wrapup(final_text)
          anchored = f"{final_text}\n\n{SUBAGENT_WRAPUP_HEADING}\n\n{wrapup}\n"

      return {
          "messages": [AIMessage(content=anchored)],
          "research_trace_report": trace_report,
          "token_usage_events": token_events,
      }

    except GraphBubbleUp:
        # LangGraph control-flow (GraphInterrupt for HITL, etc.) must propagate
        # to the parent graph so it can yield __interrupt__ to the stream adapter.
        _hitl_bubble_up = True
        raise
    except Exception as exc:
        # Ensure any dangling invoke is closed before error handling.
        _flush_write_brief_visible_for_sse()
        research_llm_emit.close(usage=_pop_pending_usage())
        run_status = "error"
        run_error = str(exc)
        token_events = _get_token_events(config)
        trace_report = _build_research_trace_report(
            ui_language="zh",
            token_events=token_events,
            reasoning_snippets=reasoning_snippets,
        )
        final_text = _compose_research_conclusion(
            ui_language="zh",
            trace_report=trace_report,
            final_text=run_error,
        )
        final_text = _extract_final_result_content(final_text, "zh")
        logger.error(
            "Compiled open_deep_research subagent failed",
            error=run_error,
            exc_info=True,
        )

        # Push error event
        _err = {
            "type": "error",
            "id": "research-error",
            "status": "error",
            "detail": run_error,
        }
        attach_turn_to_event(_err, research_turn)
        _push(_err)

        return {
            "messages": [AIMessage(content=final_text)],
            "research_trace_report": trace_report,
            "token_usage_events": token_events,
        }
    finally:
        token_events = _get_token_events(config)
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        session_id = str(configurable.get("thread_id", "") or "")

        if not _hitl_bubble_up:
            push_skipped_research_phase_milestones(
                stream_ctx,
                _ui_lang,
                _push,
                research_turn,
            )

        try:
            log_path = _write_research_run_log(
                query=query,
                session_id=session_id,
                ui_language="zh",
                started_at=started_at,
                status=run_status,
                error=run_error,
                final_text=final_text,
                trace_report=trace_report,
                token_events=token_events,
                reasoning_snippets=reasoning_snippets,
                model_config=_extract_model_config_for_log(config),
            )
            logger.info(
                "compiled open_deep_research run log path",
                session_id=session_id,
                log_path=str(log_path),
                status=run_status,
            )
        except Exception as log_exc:
            logger.warning(
                "Failed to write compiled open_deep_research run log",
                session_id=session_id,
                error=str(log_exc),
            )


def _run_open_deep_research_subagent_sync(
    state: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Sync fallback for RunnableLambda(func=...) compatibility."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run_open_deep_research_subagent(state, config))
    raise RuntimeError(
        "Synchronous CompiledSubAgent invoke is not supported inside a running event loop. "
        "Use async invocation path instead."
    )


def build_open_deep_research_compiled_subagent(description: str) -> CompiledSubAgent:
    """Build CompiledSubAgent spec for open_deep_research graph."""
    return {
        "name": "deep-research",
        "description": description,
        "runnable": RunnableLambda(
            func=_run_open_deep_research_subagent_sync,
            afunc=_run_open_deep_research_subagent,
        ),
    }


async def stream_open_deep_research_compiled(
    query: str,
    session_id: str = "",
    ui_language: str = "zh",
) -> AsyncGenerator[dict[str, Any], None]:
    """直接流式输出 open_deep_research 的所有中间事件。

    使用方式:
        async for event in stream_open_deep_research_compiled("研究问题", "session-123"):
            print(event["type"], event)

    Args:
        query: 研究查询内容
        session_id: 会话ID
        ui_language: UI语言 (默认 "zh")

    Yields:
        事件字典，包含 type 字段:
        - step: 四阶段里程碑 ``phaseId``（``deep_research_*``）；调试用 ``debug-node-*`` / ``debug-input-*`` 带 ``visibility: debug``
        - tool_call / tool_result / reasoning: 与主 SSE 相同
        - error: on failure
        不产出 ``conclusion`` / ``done``（由主 Agent 或调用方负责结束与成文）。
    """
    started_at = datetime.now()
    config: RunnableConfig = {
        "configurable": {
            "thread_id": session_id,
            "sse_ui_language": ui_language,
            "subagent_response_language": ui_language,
        }
    }
    final_text = ""
    trace_report = ""
    reasoning_snippets: list[str] = []
    result: dict[str, Any] = {}
    run_status = "success"
    run_error = ""

    logger.info(
        "Research stream started",
        research_mode="compiled_subagent_stream",
        query_preview=query[:120],
    )

    stream_ctx = DeepResearchStreamExtractContext(ui_language=ui_language)
    yield _deep_research_clarify_pre_start_event(ui_language, stream_ctx)

    research_input_messages = _build_layered_research_messages(query)

    try:
        async for update in original_research_graph.astream(
            {"messages": research_input_messages},
            config=config,
            stream_mode="updates",
        ):
            if not isinstance(update, dict):
                continue

            # 提取并直接 yield 所有中间事件
            for evt in _extract_stream_events(update, stream_ctx):
                # 收集 reasoning snippets
                if evt.get("type") == "reasoning":
                    snippet = str(evt.get("content", "") or "").strip()
                    if snippet:
                        reasoning_snippets.append(snippet)

                # 直接输出事件
                yield evt

            # 更新 result
            for _node_name, node_output in update.items():
                if isinstance(node_output, dict):
                    result.update(node_output)

        # Prefer merged graph state after the stream completes.
        extracted_final = _extract_final_text(result).strip()
        if extracted_final:
            final_text = extracted_final

        # 构建最终结论
        token_events = _get_token_events(config)
        trace_report = _build_research_trace_report(
            ui_language=ui_language,
            token_events=token_events,
            reasoning_snippets=reasoning_snippets,
        )
        final_text = _compose_research_conclusion(
            ui_language=ui_language,
            trace_report=trace_report,
            final_text=final_text,
        )
        final_text = _extract_final_result_content(final_text, ui_language)

        # Caller (e.g. main agent) owns conclusion/done; stream stops after graph work + skipped phases.

    except GraphBubbleUp:
        raise
    except Exception as exc:
        run_status = "error"
        run_error = str(exc)
        logger.error("Research stream failed", error=run_error, exc_info=True)
        yield {"type": "error", "id": "research-error", "status": "error", "detail": run_error}

    finally:
        # 写日志
        token_events = _get_token_events(config)
        try:
            _write_research_run_log(
                query=query,
                session_id=session_id,
                ui_language=ui_language,
                started_at=started_at,
                status=run_status,
                error=run_error,
                final_text=final_text,
                trace_report=trace_report,
                token_events=token_events,
                reasoning_snippets=reasoning_snippets,
                model_config=_extract_model_config_for_log(config),
            )
        except Exception:
            pass

        for i, phase_id in enumerate(_RESEARCH_PHASE_ORDER):
            if phase_id in stream_ctx.emitted_research_phase_ids:
                continue
            yield {
                "type": "step",
                "id": f"dr-phase-{phase_id}-skipped",
                "phaseId": phase_id,
                "phaseIndex": i,
                "label": get_stream_adapter_label(_RESEARCH_PHASE_LABEL_KEYS[phase_id], ui_language),
                "status": "skipped",
                "subagentName": "deep-research",
                "researchSubgraph": True,
            }
            stream_ctx.emitted_research_phase_ids.add(phase_id)
