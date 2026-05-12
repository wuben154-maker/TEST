"""Tests for __interrupt__ detection and re-run in adapters.

Covers:
  - Compiled adapter: detects __interrupt__, calls
    langgraph_interrupt(), re-runs with reply
  - Original adapter: detects __interrupt__, yields
    clarification SSE event, stops
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt


# ------------------------------------------------------------------
# Compiled adapter tests
# ------------------------------------------------------------------

_COMPILED = "app.agents.research.open_deep_research_compiled"


def _cfg() -> dict[str, Any]:
    return {"configurable": {"thread_id": "test-session"}}


class _FakeGraph:
    """Fake graph whose astream yields canned events."""

    def __init__(
        self, call_sequences: list[list[tuple]],
    ):
        self._sequences = call_sequences
        self._call_idx = 0
        self.captured_inputs: list[dict] = []

    async def astream(self, inputs: dict, **kw: Any):
        self.captured_inputs.append(inputs)
        idx = min(
            self._call_idx, len(self._sequences) - 1,
        )
        seq = self._sequences[idx]
        self._call_idx += 1
        for item in seq:
            yield item


@pytest.mark.asyncio
async def test_compiled_detects_interrupt_and_reruns():
    """Compiled adapter detects __interrupt__ and re-runs."""
    payload = {
        "interruptKind": "user_input_v1",
        "requestId": "req-1",
        "kind": "text",
        "prompt": "What do you want to research?",
    }

    run1 = [
        ((), "updates", {
            "__interrupt__": (
                Interrupt(value=payload, id="intr-1"),
            ),
        }),
    ]
    run2 = [
        ((), "updates", {
            "final_report_generation": {
                "final_report": "# Done",
                "messages": [AIMessage(content="# Done")],
            },
        }),
    ]

    fake = _FakeGraph([run1, run2])
    resume = {"response": "I want to research AI safety"}

    with (
        patch(f"{_COMPILED}.original_research_graph", fake),
        patch(
            f"{_COMPILED}.langgraph_interrupt",
            return_value=resume,
        ) as mock_intr,
    ):
        from app.agents.research.open_deep_research_compiled import (
            _run_open_deep_research_subagent,
        )

        result = await _run_open_deep_research_subagent(
            state={
                "messages": [
                    HumanMessage(content="research AI"),
                ],
            },
            config=_cfg(),
        )

    mock_intr.assert_called_once_with(payload)

    assert fake._call_idx == 2, (
        "astream should be called twice"
    )

    rerun_msgs = fake.captured_inputs[1]["messages"]
    assert any(
        isinstance(m, HumanMessage)
        and "AI safety" in m.content
        for m in rerun_msgs
    ), "Re-run should include user reply"

    assert "messages" in result
    assert len(result["messages"]) > 0


@pytest.mark.asyncio
async def test_compiled_interrupt_propagates_graph_interrupt():
    """When langgraph_interrupt raises GraphInterrupt (first invocation),
    the exception must propagate to the parent graph instead of being
    swallowed by the except-Exception handler as research-error."""
    payload = {
        "interruptKind": "user_input_v1",
        "requestId": "req-propagate",
        "kind": "text",
        "prompt": "Clarify your scope?",
    }

    run1 = [
        ((), "updates", {
            "__interrupt__": (
                Interrupt(value=payload, id="intr-prop"),
            ),
        }),
    ]

    fake = _FakeGraph([run1])

    gi = GraphInterrupt(
        (Interrupt(value=payload, id="intr-prop"),)
    )

    with (
        patch(f"{_COMPILED}.original_research_graph", fake),
        patch(
            f"{_COMPILED}.langgraph_interrupt",
            side_effect=gi,
        ),
    ):
        from app.agents.research.open_deep_research_compiled import (
            _run_open_deep_research_subagent,
        )

        with pytest.raises(GraphInterrupt):
            await _run_open_deep_research_subagent(
                state={
                    "messages": [
                        HumanMessage(content="test propagation"),
                    ],
                },
                config=_cfg(),
            )


@pytest.mark.asyncio
async def test_compiled_no_interrupt_single_run():
    """Without __interrupt__, adapter runs once."""
    events = [
        ((), "updates", {
            "final_report_generation": {
                "final_report": "# Report",
                "messages": [
                    AIMessage(content="# Report"),
                ],
            },
        }),
    ]

    fake = _FakeGraph([events])

    with (
        patch(
            f"{_COMPILED}.original_research_graph", fake,
        ),
        patch(
            f"{_COMPILED}.langgraph_interrupt",
        ) as mock_intr,
    ):
        from app.agents.research.open_deep_research_compiled import (
            _run_open_deep_research_subagent,
        )

        result = await _run_open_deep_research_subagent(
            state={
                "messages": [
                    HumanMessage(content="topic"),
                ],
            },
            config=_cfg(),
        )

    mock_intr.assert_not_called()
    assert fake._call_idx == 1
    assert "messages" in result


# ------------------------------------------------------------------
# Original adapter tests
# ------------------------------------------------------------------

_ORIGINAL = (
    "app.agents.research"
    ".open_deep_research_original_adapter"
)


@pytest.mark.asyncio
async def test_original_detects_interrupt():
    """Original adapter yields clarification event."""
    payload = {
        "interruptKind": "user_input_v1",
        "requestId": "req-2",
        "kind": "text",
        "prompt": "Narrow your research scope?",
    }

    async def mock_astream(*a: Any, **kw: Any):
        yield {"clarify_with_user": {"messages": []}}
        yield {
            "__interrupt__": (
                Interrupt(value=payload, id="intr-2"),
            ),
        }

    mock_graph = MagicMock()
    mock_graph.astream = mock_astream

    with patch(
        f"{_ORIGINAL}.original_research_graph",
        mock_graph,
    ):
        from app.agents.research import (
            open_deep_research_original_adapter as mod,
        )

        events: list[dict] = []
        async for ev in mod.stream_open_deep_research_original(
            "test query", "sess-1",
        ):
            events.append(ev)

    clarifs = [
        e for e in events
        if e.get("type") == "research_clarification_required"
    ]
    assert len(clarifs) == 1
    assert "narrow" in clarifs[0]["content"].lower()


@pytest.mark.asyncio
async def test_original_no_interrupt_emits_conclusion():
    """Without interrupt, emits conclusion."""

    async def mock_astream(*a: Any, **kw: Any):
        yield {
            "final_report_generation": {
                "final_report": "Result here.",
                "messages": [
                    AIMessage(content="Result here."),
                ],
            },
        }

    mock_graph = MagicMock()
    mock_graph.astream = mock_astream

    with patch(
        f"{_ORIGINAL}.original_research_graph",
        mock_graph,
    ):
        from app.agents.research import (
            open_deep_research_original_adapter as mod,
        )

        events: list[dict] = []
        async for ev in mod.stream_open_deep_research_original(
            "test query", "sess-2",
        ):
            events.append(ev)

    conclusions = [
        e for e in events
        if e.get("type") == "conclusion"
    ]
    assert len(conclusions) >= 1

    interrupts = [
        e for e in events
        if e.get("type") == "research_clarification_required"
    ]
    assert len(interrupts) == 0
