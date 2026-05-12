"""Unit tests for request/session isolation guards."""

import asyncio
from collections import defaultdict

import pytest

from app.agents import deep_agent


class _DummyAgent:
    def __init__(self, timeline: list[tuple[str, str, float]]) -> None:
        self.timeline = timeline

    async def analyze_stream(
        self,
        text: str,
        files: list[dict] | None = None,
        request_id: str = "",
        ui_language: str = "zh",
        input_language: str = "auto",
        client_timezone: str | None = None,
    ):
        self.timeline.append(
            ("start", request_id, asyncio.get_running_loop().time())
        )
        await asyncio.sleep(0.03)
        yield {
            "type": "step",
            "id": f"step-{request_id}",
            "requestId": request_id,
        }
        self.timeline.append(
            ("end", request_id, asyncio.get_running_loop().time())
        )


@pytest.mark.asyncio
async def test_same_session_requests_are_serialized(monkeypatch):
    timeline: list[tuple[str, str, float]] = []
    dummy = _DummyAgent(timeline)
    monkeypatch.setattr(deep_agent, "get_deep_agent", lambda *a, **kw: dummy)

    async def _collect(req_id: str):
        return [
            event
            async for event in deep_agent.stream_analyze_request(
                text="analyze",
                files=None,
                session_id="same-session",
                request_id=req_id,
            )
        ]

    events_a, events_b = await asyncio.gather(
        _collect("req-A"),
        _collect("req-B"),
    )

    by_req: dict[str, dict[str, float]] = defaultdict(dict)
    for phase, req, ts in timeline:
        by_req[req][phase] = ts

    assert {"req-A", "req-B"} == set(by_req.keys())
    a = by_req["req-A"]
    b = by_req["req-B"]
    no_overlap = (a["end"] <= b["start"]) or (b["end"] <= a["start"])
    assert no_overlap, (
        f"Expected serialized execution, got overlap: {timeline}"
    )
    assert events_a[0].get("requestId") == "req-A"
    assert events_b[0].get("requestId") == "req-B"
