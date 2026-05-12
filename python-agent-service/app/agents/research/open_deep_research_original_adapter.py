"""Adapter for open_deep_research_original to SSE-style events."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator

import structlog
from app.datetime_support import now_app
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Interrupt

from app.agents.research.open_deep_research_original.deep_researcher import (
    deep_researcher as original_research_graph,
)
from app.parsers.final_message_split import subagent_sse_visible_text
from app.parsers.labels import get_intent_label, get_stream_adapter_label
from app.parsers.llm_invoke_sse import llm_invoke_triplet
from app.parsers.message_content import (
    content_blocks_to_plain_text,
    split_aimessage_thinking_and_visible,
)

logger = structlog.get_logger()


def _extract_visible_answer_text(content: Any) -> str:
    """User-visible model output: prefer Anthropic/OpenAI text blocks, not chain-of-thought.

    Use for final_report / conclusion. Avoids leaking `str(dict)` artifacts from list content.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        if parts:
            return "\n".join(parts).strip()
        return _extract_content_text(content)
    if isinstance(content, dict):
        if content.get("type") == "text":
            t = content.get("text")
            return t if isinstance(t, str) else ""
        return _extract_content_text(content)
    return _extract_content_text(content)


_extract_content_text = content_blocks_to_plain_text


def normalize_research_brief_key(text: str) -> str:
    """Normalize research brief text for deduplication (whitespace-insensitive)."""
    t = (text or "").strip().lower()
    return re.sub(r"\s+", " ", t)


def _preview_plain_text(text: str, limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: max(0, limit - 1)] + "…"


def format_research_tool_output_for_sse(
    content: Any,
    *,
    tool_name: str,
    ui_language: str = "zh",
    limit: int = 4000,
) -> str:
    """Plain-text tool output for SSE; never expose raw list repr for ConductResearch."""
    think_lbl = get_stream_adapter_label("research_sse_prefix_thinking", ui_language)
    if tool_name == "ConductResearch" and isinstance(content, list):
        text_blocks: list[str] = []
        thinking_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                typ = item.get("type")
                if typ == "thinking":
                    th = item.get("thinking")
                    if isinstance(th, str) and th.strip():
                        thinking_parts.append(th.strip())
                elif typ == "text":
                    tx = item.get("text")
                    if isinstance(tx, str) and tx.strip():
                        text_blocks.append(tx.strip())
            elif isinstance(item, str) and item.strip():
                text_blocks.append(item.strip())
        body = "\n\n".join(text_blocks).strip()
        thinking_joined = " ".join(thinking_parts).strip()
        if body and thinking_joined:
            main = _preview_plain_text(body, max(500, limit - 400))
            note = _preview_plain_text(thinking_joined, 400)
            return f"{main}\n\n{think_lbl}\n{note}"
        if body:
            return _preview_plain_text(body, limit)
        if thinking_joined:
            return _preview_plain_text(f"{think_lbl}\n{thinking_joined}", limit)
        return ""

    raw = _extract_content_text(content)
    if tool_name == "ConductResearch":
        raw = subagent_sse_visible_text(raw) or raw
    return _preview_plain_text(raw, limit)


@dataclass
class DeepResearchStreamExtractContext:
    """Mutable state across deep-research stream chunks."""

    ui_language: str = "zh"
    brief_norm_from_write: str | None = None
    #: Canonical deep-research UI phases already emitted (see open_deep_research_compiled).
    emitted_research_phase_ids: set[str] = field(default_factory=set)
    #: Dedup keys for leading-edge phase milestones, e.g. ``clarify:running``, ``plan:success``.
    research_phase_markers_done: set[str] = field(default_factory=set)
    #: tool_call SSE ids already pushed (messages-stream early emit vs updates dedupe).
    emitted_tool_call_sse_ids: set[str] = field(default_factory=set)


def _extract_trace_events(update: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tool/reasoning events from graph updates."""
    events: list[dict[str, Any]] = []

    for node_name, node_output in update.items():
        if not isinstance(node_output, dict):
            continue

        message_lists: list[list[Any]] = []
        for key in ("messages", "supervisor_messages", "researcher_messages"):
            value = node_output.get(key)
            if isinstance(value, list):
                message_lists.append(value)

        for messages in message_lists:
            for msg in messages:
                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            events.append(
                                {
                                    "type": "tool_call",
                                    "id": tc.get("id", ""),
                                    "toolName": tc.get("name", ""),
                                    "toolInput": tc.get("args", {}),
                                    "status": "running",
                                }
                            )
                    else:
                        content_text = _extract_content_text(msg.content)
                        if content_text:
                            # Propagate AIMessage.usage_metadata so the realtime
                            # context-usage indicator (frontend) can fill the
                            # ring on research runs too.
                            events.extend(
                                llm_invoke_triplet(
                                    "reasoning",
                                    content_text,
                                    usage=getattr(msg, "usage_metadata", None),
                                )
                            )
                elif isinstance(msg, ToolMessage):
                    events.append(
                        {
                            "type": "tool_result",
                            "id": getattr(msg, "tool_call_id", ""),
                            "toolName": getattr(msg, "name", ""),
                            "toolOutput": _extract_content_text(msg.content),
                            "status": "success",
                        }
                    )

    return events


def _classify_round_role(step: str) -> str:
    """Classify token usage step into main/sub agent role."""
    step_lower = (step or "").lower()
    if step_lower.startswith(("researcher_loop_", "compress_research_")):
        return "sub"
    return "main"


def _build_research_trace_report(
    *,
    ui_language: str,
    token_events: list[dict[str, Any]],
    reasoning_snippets: list[str],
) -> str:
    """Build a single markdown appendix for rounds, latency, and token usage."""
    rounds = max(len(token_events), len(reasoning_snippets))
    if rounds == 0:
        lines: list[str] = [
            "",
            "",
            f"## {get_stream_adapter_label('research_trace_title', ui_language)}",
            "",
            f"| {get_stream_adapter_label('research_trace_col_round', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_agent', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_step', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_action', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_insight', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_elapsed', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_prompt', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_completion', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_col_total', ui_language)} |",
            "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            f"| 1 | {get_stream_adapter_label('research_trace_agent_main', ui_language)}"
            f" | - | {get_stream_adapter_label('research_trace_action_fallback', ui_language)}"
            f" | {get_stream_adapter_label('research_trace_no_internal_data', ui_language)}"
            " | N/A | N/A | N/A | N/A |",
            "",
            f"- {get_stream_adapter_label('research_trace_total_prompt', ui_language)}: N/A",
            f"- {get_stream_adapter_label('research_trace_total_completion', ui_language)}: N/A",
            f"- {get_stream_adapter_label('research_trace_total_tokens', ui_language)}: N/A",
        ]
        return "\n".join(lines)

    lines: list[str] = [
        "",
        "",
        f"## {get_stream_adapter_label('research_trace_title', ui_language)}",
        "",
        f"| {get_stream_adapter_label('research_trace_col_round', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_agent', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_step', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_action', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_insight', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_elapsed', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_prompt', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_completion', ui_language)}"
        f" | {get_stream_adapter_label('research_trace_col_total', ui_language)} |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]

    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    has_prompt = False
    has_completion = False
    has_total = False

    for idx in range(1, rounds + 1):
        item = token_events[idx - 1] if idx - 1 < len(token_events) else {}
        step = str(item.get("step", "") or "")
        action = str(item.get("action", "") or "")
        role = _classify_round_role(step)
        if not step and idx - 1 < len(reasoning_snippets):
            step = f"reasoning_round_{idx}"
        if not action:
            action = get_stream_adapter_label("research_trace_action_fallback", ui_language)
        role_label = get_stream_adapter_label(
            "research_trace_agent_sub" if role == "sub" else "research_trace_agent_main",
            ui_language,
        )

        prompt = item.get("prompt_tokens")
        completion = item.get("completion_tokens")
        total = item.get("total_tokens")
        elapsed_ms = item.get("elapsed_ms")

        if isinstance(prompt, int):
            total_prompt += prompt
            has_prompt = True
        if isinstance(completion, int):
            total_completion += completion
            has_completion = True
        if isinstance(total, int):
            total_tokens += total
            has_total = True

        insight = ""
        if idx - 1 < len(reasoning_snippets):
            insight = reasoning_snippets[idx - 1]
        insight = insight.strip().replace("\n", " ")
        if len(insight) > 120:
            insight = insight[:117] + "..."

        lines.append(
            f"| {idx}"
            f" | {role_label}"
            f" | {step or '-'}"
            f" | {action.replace('|', '/') or '-'}"
            f" | {insight or '-'}"
            f" | {elapsed_ms if isinstance(elapsed_ms, int) else 'N/A'}"
            f" | {prompt if isinstance(prompt, int) else 'N/A'}"
            f" | {completion if isinstance(completion, int) else 'N/A'}"
            f" | {total if isinstance(total, int) else 'N/A'} |"
        )

    lines.extend(
        [
            "",
            f"- {get_stream_adapter_label('research_trace_total_prompt', ui_language)}: {total_prompt if has_prompt else 'N/A'}",
            f"- {get_stream_adapter_label('research_trace_total_completion', ui_language)}: {total_completion if has_completion else 'N/A'}",
            f"- {get_stream_adapter_label('research_trace_total_tokens', ui_language)}: {total_tokens if has_total else 'N/A'}",
        ]
    )
    return "\n".join(lines)


def _compose_research_conclusion(*, ui_language: str, trace_report: str, final_text: str) -> str:
    """Compose final conclusion with logs first and final result at the end."""
    normalized_trace = (trace_report or "").strip()
    normalized_final = (final_text or "").strip()
    if not normalized_final:
        normalized_final = get_stream_adapter_label("research_final_result_missing", ui_language)

    final_section = (
        f"## {get_stream_adapter_label('research_final_result_title', ui_language)}"
        f"\n\n{normalized_final}"
    )
    if normalized_trace:
        return f"{normalized_trace}\n\n{final_section}"
    return final_section


def _extract_final_result_content(content: str, ui_language: str) -> str:
    """Extract final-result section body from composed research conclusion."""
    text = (content or "").strip()
    if not text:
        return ""
    candidates = [
        get_stream_adapter_label("research_final_result_title", ui_language),
        "Final Result",
        "最终结果",
    ]
    for title in candidates:
        heading = f"## {title}".strip()
        idx = text.rfind(heading)
        if idx != -1:
            extracted = text[idx + len(heading):].strip()
            if extracted:
                return extracted
    return text




def _write_research_run_log(
    *,
    query: str,
    session_id: str,
    ui_language: str,
    started_at: datetime,
    status: str,
    error: str,
    final_text: str,
    trace_report: str,
    token_events: list[dict[str, Any]],
    reasoning_snippets: list[str],
    model_config: dict[str, Any] | None = None,
) -> None:
    """Emit research run data as a structlog event (replaces file-based logging).

    Kept as a named function for backward compatibility with ``open_deep_research_compiled``.
    """
    ended_at = now_app()
    elapsed_ms = int((ended_at - started_at).total_seconds() * 1000)
    total_prompt = sum(e.get("prompt_tokens") or 0 for e in token_events)
    total_completion = sum(e.get("completion_tokens") or 0 for e in token_events)
    total_tokens = sum(e.get("total_tokens") or 0 for e in token_events)

    logger.info(
        "research_run_complete",
        session_id=session_id,
        status=status,
        error=error or None,
        elapsed_ms=elapsed_ms,
        query_preview=query[:120] if query else "",
        final_text_len=len(final_text or ""),
        token_event_count=len(token_events),
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_tokens,
        reasoning_snippet_count=len(reasoning_snippets),
        model_config=model_config or None,
    )


def _extract_model_config_for_log(config: dict[str, Any] | None) -> dict[str, Any]:
    """Extract resolved model names from Configuration for logging."""
    try:
        from app.agents.research.open_deep_research_original.configuration import Configuration

        cfg = Configuration.from_runnable_config(config or {})
        return {
            "research_model": cfg.research_model,
            "summarization_model": cfg.summarization_model,
            "compression_model": cfg.compression_model,
            "final_report_model": cfg.final_report_model,
        }
    except Exception:
        return {}




async def stream_open_deep_research_original(
    text: str,
    session_id: str,
    ui_language: str = "zh",
) -> AsyncGenerator[dict[str, Any], None]:
    """Run open_deep_research graph and adapt output to frontend events."""
    started_at = now_app()
    final_text = ""
    clarification_question = ""
    reached_research_execution = False
    config = {"configurable": {"thread_id": session_id}}
    reasoning_snippets: list[str] = []
    trace_report = ""
    run_status = "success"
    run_error = ""

    try:
        async for update in original_research_graph.astream(
            {"messages": [HumanMessage(content=text)]},
            config=config,
            stream_mode="updates",
        ):
            if not isinstance(update, dict):
                continue

            # ── HITL: detect __interrupt__ from clarify_with_user ──
            _intr_data = update.get("__interrupt__")
            if _intr_data is not None:
                intr_list = list(_intr_data) if isinstance(_intr_data, (list, tuple)) else [_intr_data]
                for intr_obj in intr_list:
                    if isinstance(intr_obj, Interrupt):
                        payload = intr_obj.value if isinstance(intr_obj.value, dict) else {}
                        prompt = str(payload.get("prompt", "") or "").strip()
                        if prompt:
                            clarification_question = prompt
                        logger.info(
                            "research_subgraph_interrupted",
                            interrupt_id=intr_obj.id,
                        )
                break

            if any(
                node in update
                for node in (
                    "write_research_brief",
                    "research_supervisor",
                    "final_report_generation",
                )
            ):
                reached_research_execution = True

            trace_events = _extract_trace_events(update)
            for event in trace_events:
                if event.get("type") in {"tool_call", "tool_result", "reasoning"}:
                    yield event
                if event.get("type") == "reasoning":
                    snippet = str(event.get("content", "") or "").strip()
                    if snippet:
                        reasoning_snippets.append(snippet)

                if event.get("field") == "clarification":
                    clarification_value = str(event.get("content", "") or "").strip()
                    if clarification_value:
                        clarification_question = clarification_value
                elif event.get("field") == "final_report":
                    final_report_text = str(event.get("content", "") or "").strip()
                    if final_report_text:
                        final_text = final_report_text

            clarify_node = update.get("clarify_with_user")
            if isinstance(clarify_node, dict):
                clarify_messages = clarify_node.get("messages")
                if isinstance(clarify_messages, list):
                    for msg in clarify_messages:
                        if isinstance(msg, dict):
                            content_text = _extract_content_text(msg.get("content"))
                        else:
                            content_text = _extract_content_text(getattr(msg, "content", ""))
                        if content_text.strip():
                            clarification_question = content_text.strip()

        if clarification_question and not reached_research_execution:
            yield {
                "type": "research_clarification_required",
                "id": "research-clarification-required",
                "content": clarification_question,
                "internal": True,
            }
        elif final_text:
            token_events_raw = config.get("configurable", {}).get("token_usage_events", [])
            token_events = token_events_raw if isinstance(token_events_raw, list) else []
            trace_report = _build_research_trace_report(
                ui_language=ui_language,
                token_events=token_events,
                reasoning_snippets=reasoning_snippets,
            )
            output_content = _compose_research_conclusion(
                ui_language=ui_language,
                trace_report=trace_report,
                final_text=final_text,
            )
            final_text = _extract_final_result_content(output_content, ui_language)
            yield {"type": "conclusion", "id": "conclusion", "content": final_text}
        else:
            logger.warning(
                "research_graph_no_final_report",
                session_id=session_id,
            )
            run_status = "error"
            run_error = "no_final_output"
            token_events_raw = config.get("configurable", {}).get("token_usage_events", [])
            token_events = token_events_raw if isinstance(token_events_raw, list) else []
            trace_report = _build_research_trace_report(
                ui_language=ui_language,
                token_events=token_events,
                reasoning_snippets=reasoning_snippets,
            )
            output_content = _compose_research_conclusion(
                ui_language=ui_language,
                trace_report=trace_report,
                final_text="",
            )
            final_text = _extract_final_result_content(output_content, ui_language)
            yield {"type": "conclusion", "id": "conclusion", "content": final_text}
            yield {
                "type": "error",
                "id": "open-deep-research-no-output",
                "status": "error",
                "detail": get_intent_label("stream_error_unknown", ui_language),
            }

    except Exception as exc:
        run_status = "error"
        run_error = str(exc)
        token_events_raw = config.get("configurable", {}).get("token_usage_events", [])
        token_events = token_events_raw if isinstance(token_events_raw, list) else []
        trace_report = _build_research_trace_report(
            ui_language=ui_language,
            token_events=token_events,
            reasoning_snippets=reasoning_snippets,
        )
        output_content = _compose_research_conclusion(
            ui_language=ui_language,
            trace_report=trace_report,
            final_text=str(exc),
        )
        final_text = _extract_final_result_content(output_content, ui_language)
        logger.error(
            "research_graph_failed",
            session_id=session_id,
            error=str(exc),
            exc_info=True,
        )
        yield {"type": "conclusion", "id": "conclusion", "content": final_text}
        yield {
            "type": "error",
            "id": "open-deep-research-original-error",
            "status": "error",
            "detail": str(exc),
        }
    finally:
        token_events_raw = config.get("configurable", {}).get("token_usage_events", [])
        token_events = token_events_raw if isinstance(token_events_raw, list) else []
        ended_at = now_app()
        elapsed_ms = int((ended_at - started_at).total_seconds() * 1000)
        model_config = _extract_model_config_for_log(config)

        total_prompt = sum(e.get("prompt_tokens") or 0 for e in token_events)
        total_completion = sum(e.get("completion_tokens") or 0 for e in token_events)
        total_tokens = sum(e.get("total_tokens") or 0 for e in token_events)

        logger.info(
            "research_run_complete",
            session_id=session_id,
            status=run_status,
            error=run_error or None,
            elapsed_ms=elapsed_ms,
            query_preview=text[:120] if text else "",
            final_text_len=len(final_text or ""),
            token_event_count=len(token_events),
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_tokens,
            reasoning_snippet_count=len(reasoning_snippets),
            model_config=model_config or None,
        )
        yield {
            "type": "step",
            "id": "analysis-complete",
            "label": get_stream_adapter_label("stream_analysis_complete", ui_language),
            "status": "success",
        }
        yield {"type": "done", "id": "done"}

