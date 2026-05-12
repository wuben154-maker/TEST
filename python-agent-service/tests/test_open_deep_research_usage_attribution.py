"""Deep-research subagent usage attribution — regression tests.

Covers: `docs/Process/deep-research-subagent-usage-attribution/design.md`.

Gap being closed: the streaming `messages` path in
`_run_open_deep_research_subagent` used to call `research_llm_emit.close()`
without forwarding `AIMessage.usage_metadata`, so every `llm_invoke_end`
from the deep-research subgraph arrived at the frontend without a `usage`
field. The frontend reducer short-circuits on missing `usage`, which is
why the context-usage popover showed "No subagent activity yet" even
while the ring itself lit up (main agent usage comes from the lifecycle
callback handler and was unaffected).

These tests lock in the two-sided contract:
  * when the upstream chunk carries `usage_metadata`, the matching
    `llm_invoke_end` MUST include a normalized `usage` dict;
  * when no chunk carried `usage_metadata` (legacy / function_calling
    nodes), `llm_invoke_end` MUST stay usage-free (no zero-pollution).
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.research.open_deep_research_compiled import (
    _run_open_deep_research_subagent,
)
from app.parsers.final_message_split import (
    SUBAGENT_FULL_HEADING,
    SUBAGENT_WRAPUP_HEADING,
)


def _final_report_content() -> str:
    long_body = "LONGREPORT" * 60
    return (
        f"{SUBAGENT_WRAPUP_HEADING}\n\nShort wrap.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\n{long_body}"
    )


def test_research_streaming_close_forwards_usage():
    """A streaming chunk whose ``usage_metadata`` is populated must produce a
    matching ``llm_invoke_end`` that carries the normalized ``usage`` dict.

    Without this wiring, the context-usage popover cannot attribute any
    tokens to the deep-research subagent (main ring still lights up, but
    ``bySubagent`` stays empty — matching the bug report "No subagent
    activity yet").
    """

    report = _final_report_content()

    async def _gen(*_args, **_kwargs):
        yield (
            (),
            "messages",
            (
                AIMessage(
                    content=report,
                    id="final-chunk-1",
                    usage_metadata={
                        "input_tokens": 1234,
                        "output_tokens": 567,
                        "total_tokens": 1801,
                    },
                ),
                {"langgraph_node": "final_report_generation"},
            ),
        )
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": report,
                    "messages": [AIMessage(content=report)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="research query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "t-usage-forward",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    ends_with_usage = [
        e
        for e in pushed
        if e.get("type") == "llm_invoke_end" and isinstance(e.get("usage"), dict)
    ]
    assert ends_with_usage, (
        "Expected at least one llm_invoke_end carrying a `usage` dict. "
        f"Saw {[e.get('type') for e in pushed if e.get('type') and e['type'].startswith('llm_invoke')]}"
    )
    # `usage` is normalized by app.parsers.llm_invoke_sse._coerce_usage
    # into camelCase inputTokens/outputTokens.
    assert any(
        e["usage"].get("inputTokens") == 1234
        and e["usage"].get("outputTokens") == 567
        for e in ends_with_usage
    ), (
        "Normalized usage payload missing or mis-mapped. "
        f"Got: {[e['usage'] for e in ends_with_usage]}"
    )


def test_research_streaming_close_without_usage_stays_usage_free():
    """When upstream never reports ``usage_metadata`` (common with
    function_calling structured output), ``llm_invoke_end`` MUST NOT
    invent a zero-usage payload. Back-compat with the pre-fix contract
    so the frontend reducer keeps skipping these events.
    """

    report = _final_report_content()

    async def _gen(*_args, **_kwargs):
        yield (
            (),
            "messages",
            (
                # Intentionally no usage_metadata; note: id is still set so the
                # adapter's chunk-id tracking works normally.
                AIMessage(content=report, id="final-chunk-noupd"),
                {"langgraph_node": "final_report_generation"},
            ),
        )
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": report,
                    "messages": [AIMessage(content=report)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="research query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "t-usage-absent",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    ends = [e for e in pushed if e.get("type") == "llm_invoke_end"]
    assert ends, "Expected at least one llm_invoke_end event"
    assert all("usage" not in e for e in ends), (
        "llm_invoke_end must not carry a synthetic zero-usage payload when "
        f"upstream reported no usage_metadata. Offenders: {[e for e in ends if 'usage' in e]}"
    )
