from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app._vendor.deepagents.backends.protocol import ReadResult
from app._vendor.deepagents.middleware import filesystem as filesystem_middleware
from app._vendor.deepagents.middleware.filesystem import FilesystemMiddleware


class _FakeBackend:
    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return ReadResult(file_data={"content": "hello\n", "encoding": "utf-8"})


def _read_file_tool() -> Any:
    middleware = FilesystemMiddleware(backend=_FakeBackend())
    return next(tool for tool in middleware.tools if tool.name == "read_file")


def test_read_file_emits_telemetry_for_subagent_skill(monkeypatch: Any) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    def _info(event: str, **kwargs: Any) -> None:
        events.append((event, kwargs))

    monkeypatch.setattr(filesystem_middleware, "logger", SimpleNamespace(info=_info))

    tool = _read_file_tool()
    runtime = SimpleNamespace(tool_call_id="tc-skill-read")

    out = tool.func(
        file_path="/subagent-skills/binary-analysis/document-analysis-e2e-orchestrator/SKILL.md",
        runtime=runtime,
        offset=0,
        limit=10,
    )

    assert "hello" in out
    assert events == [
        (
            "skill_file_read",
            {
                "path": "/subagent-skills/binary-analysis/document-analysis-e2e-orchestrator/SKILL.md",
                "offset": 0,
                "limit": 10,
                "status": "success",
                "error": None,
                "tool_call_id": "tc-skill-read",
                "subagent_id": "binary-analysis",
                "skill_name": "document-analysis-e2e-orchestrator",
            },
        )
    ]


def test_read_file_skips_telemetry_for_non_skill_path(monkeypatch: Any) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    def _info(event: str, **kwargs: Any) -> None:
        events.append((event, kwargs))

    monkeypatch.setattr(filesystem_middleware, "logger", SimpleNamespace(info=_info))

    tool = _read_file_tool()
    runtime = SimpleNamespace(tool_call_id="tc-normal-read")

    out = tool.func(file_path="/workspace/notes.md", runtime=runtime, offset=0, limit=10)

    assert "hello" in out
    assert events == []
