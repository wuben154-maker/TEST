"""Unit tests for SReadFile helpers and tool."""

from __future__ import annotations

from typing import Any
from types import SimpleNamespace

from app.tools.sread_file import (
    _canonical_virtual_path,
    _decode_text_with_fallbacks,
    _looks_binary_by_sniff,
    sread_file,
)


def test_canonical_virtual_path() -> None:
    assert _canonical_virtual_path("/workspace/a.php") == "/workspace/a.php"
    assert _canonical_virtual_path("/Workspace/a.php") == "/workspace/a.php"
    assert _canonical_virtual_path("workspace/a.php") == "/workspace/a.php"
    assert _canonical_virtual_path("Workspace/a.php") == "/workspace/a.php"
    assert _canonical_virtual_path("uploads/x") == "/uploads/x"
    assert _canonical_virtual_path("/Uploads/x") == "/uploads/x"
    assert _canonical_virtual_path("relative-only.txt") is None


def test_decode_utf8_and_gbk() -> None:
    text, enc, _warn = _decode_text_with_fallbacks("hello 世界".encode("utf-8"))
    assert "hello" in text
    assert enc.startswith("utf")

    gb_payload = b"\xd6\xd0\xb9\xfa"  # "中国" in GB2312/GB18030
    text2, enc2, _ = _decode_text_with_fallbacks(gb_payload)
    assert text2 == "\u4e2d\u56fd"  # 中国
    assert enc2 == "gb18030"


def test_looks_binary_sniff() -> None:
    assert _looks_binary_by_sniff(b"MZ\x00\x01") is True
    assert _looks_binary_by_sniff(b"<?php echo 1;") is False


class _FakeDL:
    def __init__(self, content: bytes, error: str | None = None) -> None:
        self.content = content
        self.error = error


class _FakeBackend:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def download_files(self, paths: list[str]) -> list[_FakeDL]:
        return [_FakeDL(self._payload)]


def test_sread_file_text_via_runtime() -> None:
    rt = SimpleNamespace(backend=_FakeBackend(b"line1\nline2\n"))
    out = sread_file("/workspace/f.txt", runtime=rt)
    assert out["ok"] is True
    assert out["content_kind"] == "text"
    assert out["view_mode"] == "window"
    assert out["text"] == "line1\nline2"
    assert out["lines_returned"] == 2


def test_sread_file_head_tail_splits_large_file() -> None:
    lines = [f"L{i}" for i in range(100)]
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    rt = SimpleNamespace(backend=_FakeBackend(payload))
    out = sread_file("/workspace/big.php", view_mode="head_tail", limit=20, runtime=rt)
    assert out["ok"] is True
    assert out["view_mode"] == "head_tail"
    assert out["head_lines_returned"] == 20
    assert out["tail_lines_returned"] == 20
    assert out["tail_line_start"] == 80
    assert out["omitted_lines"] == 60
    assert out["total_lines"] == 100
    assert out["lines_returned"] == 40
    assert "L0" in out["text"] and "L19" in out["text"]
    assert "L80" in out["text"] and "L99" in out["text"]
    assert "60 lines omitted" in out["text"]
    assert out["truncation_reason"] == "head_tail_omit_middle"


def test_sread_file_head_tail_short_file_returns_full_once() -> None:
    payload = ("\n".join(f"L{i}" for i in range(30)) + "\n").encode("utf-8")
    rt = SimpleNamespace(backend=_FakeBackend(payload))
    out = sread_file("/workspace/small.php", view_mode="head_tail", limit=20, runtime=rt)
    assert out["ok"] is True
    assert out["view_mode"] == "head_tail"
    assert out["head_lines_returned"] == 30
    assert out["tail_lines_returned"] == 0
    assert out["tail_line_start"] is None
    assert out["omitted_lines"] == 0
    assert "--- omitted" not in out["text"]
    assert out["truncation_reason"] is None


def test_sread_file_head_tail_ignores_offset_warning() -> None:
    payload = b"a\nb\nc\n"
    rt = SimpleNamespace(backend=_FakeBackend(payload))
    out = sread_file("/workspace/t.php", offset=2, view_mode="head_tail", limit=5, runtime=rt)
    assert out["ok"] is True
    assert "offset_ignored_for_head_tail" in out["warnings"]
    assert "a" in out["text"] and "c" in out["text"]


def test_sread_file_invalid_path() -> None:
    rt = SimpleNamespace(backend=_FakeBackend(b"x"))
    out = sread_file("not-absolute.txt", runtime=rt)
    assert out["ok"] is False
    assert out["error_code"] == "INVALID_PATH"


def test_sread_file_no_injected_runtime_uses_layered_backend(monkeypatch: Any) -> None:
    """When ToolNode does not inject runtime (invoke/HITL), still resolve reads via factory."""

    def fake_layered(*_a: Any, **_kw: Any) -> Any:
        def factory(_rt: Any) -> Any:
            return _FakeBackend(b"line1\nline2\n")

        return factory

    monkeypatch.setattr(
        "app.backends.composite.create_layered_backend",
        fake_layered,
    )
    out = sread_file("/workspace/a.php", runtime=None)
    assert out["ok"] is True
    assert out["content_kind"] == "text"
    assert out["view_mode"] == "window"
    assert out["lines_returned"] == 2
