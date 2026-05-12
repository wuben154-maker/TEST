"""Unit tests for :class:`UploadMaterializerMiddleware`."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from upload_materializer import UploadMaterializerMiddleware


@dataclass
class _FakeRuntime:
    """Minimal ``Runtime`` stand-in exposing just ``config``."""

    config: dict[str, Any] = field(default_factory=dict)


def _runtime(thread_id: str | None = "thread-abc") -> _FakeRuntime:
    if thread_id is None:
        return _FakeRuntime(config={})
    return _FakeRuntime(config={"configurable": {"thread_id": thread_id}})


def test_materialises_base64_upload_to_thread_scoped_dir(
    tmp_path: Path,
) -> None:
    root = tmp_path / "uploads"
    middleware = UploadMaterializerMiddleware(host_upload_root=root)

    payload = b"MZ\x90\x00hello"
    state = {
        "files": {"uploaded/calc.exe": base64.standard_b64encode(payload).decode()}
    }

    update = middleware.before_agent(state, _runtime("thread-xyz"))
    assert update is not None
    host_file = root / "thread-xyz" / "calc.exe"
    assert host_file.read_bytes() == payload

    message = update["messages"][0]
    # The agent must see the host path, not the virtual /uploaded/ key.
    assert str(host_file) in message.content
    assert "/uploaded/calc.exe" in message.content


def test_materialisation_is_idempotent_across_steps(tmp_path: Path) -> None:
    """``before_agent`` re-runs on every step; only fresh uploads emit hints."""
    middleware = UploadMaterializerMiddleware(host_upload_root=tmp_path)
    payload = base64.standard_b64encode(b"bytes").decode()
    state = {"files": {"uploaded/sample.bin": payload}}

    first = middleware.before_agent(state, _runtime())
    second = middleware.before_agent(state, _runtime())

    assert first is not None
    assert second is None


def test_new_upload_after_first_step_emits_fresh_hint(tmp_path: Path) -> None:
    middleware = UploadMaterializerMiddleware(host_upload_root=tmp_path)
    encoded = base64.standard_b64encode(b"data").decode()

    middleware.before_agent({"files": {"uploaded/first.bin": encoded}}, _runtime())
    update = middleware.before_agent(
        {
            "files": {
                "uploaded/first.bin": encoded,
                "uploaded/second.bin": encoded,
            }
        },
        _runtime(),
    )
    assert update is not None
    assert "second.bin" in update["messages"][0].content
    # The already-materialised upload must not be re-announced.
    assert "first.bin" not in update["messages"][0].content


def test_non_upload_state_files_are_ignored(tmp_path: Path) -> None:
    middleware = UploadMaterializerMiddleware(host_upload_root=tmp_path)
    state = {
        "files": {
            "/notes.md": "not an upload",
            "uploaded/ok.bin": base64.standard_b64encode(b"x").decode(),
        }
    }
    update = middleware.before_agent(state, _runtime())
    assert update is not None
    # Only the uploaded/ entry should be materialised.
    materialised = {p.name for p in (tmp_path / "thread-abc").iterdir() if p.is_file()}
    assert materialised == {"ok.bin"}


def test_missing_state_files_returns_none(tmp_path: Path) -> None:
    middleware = UploadMaterializerMiddleware(host_upload_root=tmp_path)
    assert middleware.before_agent({}, _runtime()) is None
    assert middleware.before_agent({"files": {}}, _runtime()) is None


def test_invalid_base64_is_skipped_not_raised(tmp_path: Path) -> None:
    middleware = UploadMaterializerMiddleware(host_upload_root=tmp_path)
    state = {"files": {"uploaded/plain.txt": "not base64 !!! obviously"}}
    update = middleware.before_agent(state, _runtime())
    # Nothing to announce, but also no exception.
    assert update is None
    # Marked as seen so future steps do not retry.
    state2 = {"files": {"uploaded/plain.txt": "not base64 !!! obviously"}}
    assert middleware.before_agent(state2, _runtime()) is None


@pytest.mark.parametrize(
    "unsafe_key",
    [
        "uploaded/../escape.bin",
        "uploaded/sub/path.bin",
        "uploaded/",
    ],
)
def test_unsafe_filenames_are_rejected(tmp_path: Path, unsafe_key: str) -> None:
    middleware = UploadMaterializerMiddleware(host_upload_root=tmp_path)
    state = {
        "files": {
            unsafe_key: base64.standard_b64encode(b"oops").decode(),
        }
    }
    update = middleware.before_agent(state, _runtime())
    assert update is None
    # Host root stays empty except for the thread-scoped dir itself.
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written == []


def test_falls_back_to_default_thread_id_when_missing(tmp_path: Path) -> None:
    middleware = UploadMaterializerMiddleware(
        host_upload_root=tmp_path, thread_id_fallback="local-dev"
    )
    state = {"files": {"uploaded/x.bin": base64.standard_b64encode(b"x").decode()}}

    update = middleware.before_agent(state, _runtime(thread_id=None))
    assert update is not None
    assert (tmp_path / "local-dev" / "x.bin").read_bytes() == b"x"
