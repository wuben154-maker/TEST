"""Unit tests for ``humanize_tool_output`` (SSE tool-result humanizer).

Rules under test (see ``docs/Process/tool-result-humanization/design.md``):

- Empty / non-JSON / JSON-scalar inputs are returned unchanged.
- Top-level dict: ``error`` first line, content keys (stdout/stderr/...) as
  ``--- <key> ---`` blocks at the end, other non-empty fields as one-per-line
  ``key: value``. ``None`` / ``""`` / ``[]`` / ``{}`` fields are dropped.
- Arrays of scalars render as comma-joined; arrays of dicts render as numbered
  list.
- Long strings are truncated with ``... [truncated]`` suffix.
- Never raises on malformed input.
"""

from __future__ import annotations

import json

import pytest

from app.sse.tool_result_humanizer import humanize_tool_output


# --- U-01: sandbox_run success with stdout ----------------------------------


def test_u01_sandbox_run_success_renders_meta_then_stdout_block() -> None:
    raw = json.dumps(
        {
            "exit_code": 0,
            "stdout": "hello\nworld\n",
            "stderr": "",
            "sandbox_id": "sb_abc",
            "mode": "run",
            "downloaded_files": [],
            "error": None,
        }
    )

    out = humanize_tool_output(raw)

    assert out == (
        "exit_code: 0\n"
        "sandbox_id: sb_abc\n"
        "mode: run\n"
        "\n"
        "--- stdout ---\n"
        "hello\n"
        "world"
    )


# --- U-02: sandbox_run failure: error prefix ---------------------------------


def test_u02_error_field_becomes_top_line_with_prefix() -> None:
    raw = json.dumps({"error": "Timed out", "exit_code": -1, "mode": "run"})

    out = humanize_tool_output(raw)

    assert out == "error: Timed out\nexit_code: -1\nmode: run"


def test_u02b_error_null_or_empty_is_ignored() -> None:
    raw = json.dumps({"error": None, "exit_code": 0})
    assert humanize_tool_output(raw) == "exit_code: 0"

    raw2 = json.dumps({"error": "", "exit_code": 0})
    assert humanize_tool_output(raw2) == "exit_code: 0"


# --- U-03: web_search with list of result objects ---------------------------


def test_u03_object_array_renders_as_numbered_list() -> None:
    raw = json.dumps(
        {
            "query": "xss",
            "results": [
                {"title": "A", "url": "https://a", "snippet": "snip-a"},
                {"title": "B", "url": "https://b", "snippet": "snip-b"},
            ],
        }
    )

    out = humanize_tool_output(raw)

    assert out == (
        "query: xss\n"
        "results (2):\n"
        "  1. title: A\n"
        "     url: https://a\n"
        "     snippet: snip-a\n"
        "  2. title: B\n"
        "     url: https://b\n"
        "     snippet: snip-b"
    )


# --- U-04: scalar arrays + empty arrays dropped -----------------------------


def test_u04_scalar_arrays_joined_empty_dropped() -> None:
    raw = json.dumps(
        {
            "ips": ["1.1.1.1", "2.2.2.2"],
            "domains": ["evil.com"],
            "hashes": [],
        }
    )

    out = humanize_tool_output(raw)

    assert out == "ips: 1.1.1.1, 2.2.2.2\ndomains: evil.com"


# --- U-05: nested dict array ------------------------------------------------


def test_u05_nested_object_array_indented() -> None:
    raw = json.dumps(
        {
            "exit_code": 0,
            "downloaded_files": [{"path": "/out/a.log", "bytes": 123}],
        }
    )

    out = humanize_tool_output(raw)

    assert out == (
        "exit_code: 0\n"
        "downloaded_files (1):\n"
        "  1. path: /out/a.log\n"
        "     bytes: 123"
    )


# --- U-06: non-JSON input is identity ---------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "['a.txt', 'b.txt']",  # Python repr (ls/glob)
        "hello world",
        "",
        "   ",
        "not: json at all",
    ],
)
def test_u06_non_json_returned_as_is(raw: str) -> None:
    assert humanize_tool_output(raw) == raw


# --- U-07: JSON scalar (number/bool/string) returned as-is ------------------


@pytest.mark.parametrize(
    "raw",
    [
        "42",
        "true",
        "false",
        "null",
        '"hello"',
    ],
)
def test_u07_json_scalar_returned_as_is(raw: str) -> None:
    assert humanize_tool_output(raw) == raw


# --- U-08: all fields empty -> empty string ---------------------------------


def test_u08_all_fields_empty_returns_empty_string() -> None:
    raw = json.dumps(
        {
            "stdout": "",
            "stderr": "",
            "error": None,
            "exit_code": None,
            "files": [],
        }
    )
    assert humanize_tool_output(raw) == ""


# --- U-09: long content block truncated -------------------------------------


def test_u09_long_content_block_truncated() -> None:
    long_stdout = "a" * 12_000
    raw = json.dumps({"exit_code": 0, "stdout": long_stdout})

    out = humanize_tool_output(raw)

    assert out.startswith("exit_code: 0\n\n--- stdout ---\n")
    assert out.endswith("\n... [truncated]")
    assert "aaaa" in out
    assert len(out) < len(raw)


# --- U-10: malformed JSON never raises --------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        '{"error": ',
        '{"key": "value",',
        "{",
        '[{"broken":',
    ],
)
def test_u10_malformed_json_returns_identity(raw: str) -> None:
    assert humanize_tool_output(raw) == raw


# --- U-11: top-level list of objects ----------------------------------------


def test_u11_top_level_object_array() -> None:
    raw = json.dumps(
        [
            {"name": "A", "count": 1},
            {"name": "B", "count": 2},
        ]
    )

    out = humanize_tool_output(raw)

    assert out == (
        "(2 items):\n"
        "  1. name: A\n"
        "     count: 1\n"
        "  2. name: B\n"
        "     count: 2"
    )


# --- U-12: top-level list of scalars ----------------------------------------


def test_u12_top_level_scalar_array_joined() -> None:
    raw = json.dumps(["a.txt", "b.txt", "c.txt"])
    assert humanize_tool_output(raw) == "a.txt, b.txt, c.txt"


# --- U-13: bool / numeric scalars render without quotes ---------------------


def test_u13_bool_and_numeric_scalars() -> None:
    raw = json.dumps({"ok": True, "count": 0, "ratio": 1.5, "flag": False})
    out = humanize_tool_output(raw)
    assert out == "ok: true\ncount: 0\nratio: 1.5\nflag: false"


# --- U-14: nested dict inside meta ------------------------------------------


def test_u14_nested_dict_value_indented() -> None:
    raw = json.dumps({"exit_code": 0, "meta": {"arch": "x86", "os": "linux"}})
    out = humanize_tool_output(raw)
    assert out == ("exit_code: 0\nmeta:\n  arch: x86\n  os: linux")
