"""Redact host filesystem paths from user-visible strings (task list, SSE toolInput).

Analyst-facing UI must not show server upload layout or drive letters (e.g.
``D:\\code\\...\\uploads\\u_...``). Replaced segments become ``/workspace/<basename>``,
consistent with the virtual workspace contract.
"""

from __future__ import annotations

import copy
import re
from pathlib import PurePath, PureWindowsPath
from typing import Any

# UNC \\server\share\path
_UNC_PATH = re.compile(r"(?<![\\])(\\{2}[^\\\r\n]+(?:\\[^\\\r\n]+)+)")
# Windows D:\... or D:/...
_WIN_ABS_PATH = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z]:)(?:\\|/)(?:[^\\/:*?\"<>|\r\n]+(?:\\|/))*[^\\/:*?\"<>|\r\n]+"
)
# Owner-scoped upload dirs on Unix-style paths
_UNIX_UPLOADS = re.compile(
    r"(?<![A-Za-z0-9/])/[^\s\r\n]*?/uploads/u_[^\s\r\n]+"
)


def _workspace_basename_label(raw: str) -> str:
    t = raw.strip()
    while t and t[-1] in ".,;:!?)'\"\t":
        t = t[:-1].rstrip()
    if not t:
        return "/workspace/<redacted>"
    if len(t) >= 2 and t[1] == ":":
        name = PureWindowsPath(t).name
    elif t.startswith("\\\\"):
        name = PureWindowsPath(t.replace("/", "\\")).name
    else:
        name = PurePath(t.replace("\\", "/")).name
    if not name or name in (".", ".."):
        return "/workspace/<redacted>"
    return f"/workspace/{name}"


def redact_host_paths_in_text(text: str) -> str:
    """Replace host-looking path segments with ``/workspace/<basename>``.

    Leaves ``/workspace/...`` and single-component relative names unchanged.
    """
    if not text or not isinstance(text, str):
        return text

    def _repl(m: re.Match[str]) -> str:
        return _workspace_basename_label(m.group(0))

    out = _UNC_PATH.sub(_repl, text)
    out = _WIN_ABS_PATH.sub(_repl, out)
    out = _UNIX_UPLOADS.sub(_repl, out)
    return out


def sanitize_write_todos_tool_input_for_display(tc_args: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy ``write_todos`` / ``task`` list args with redacted todo text fields."""
    out = copy.deepcopy(tc_args)
    key = None
    if "todos" in out:
        key = "todos"
    elif "tasks" in out:
        key = "tasks"
    if not key:
        return out
    items = out.get(key)
    if not isinstance(items, list):
        return out
    new_list: list[Any] = []
    for todo in items:
        if not isinstance(todo, dict):
            new_list.append(todo)
            continue
        t = dict(todo)
        for fld in ("content", "task", "title"):
            v = t.get(fld)
            if isinstance(v, str):
                t[fld] = redact_host_paths_in_text(v)
        new_list.append(t)
    out[key] = new_list
    return out


def sanitize_task_tool_input_for_display(tc_args: dict[str, Any]) -> dict[str, Any]:
    """Redact path-like leakage in ``task()`` tool call args shown to the client."""
    out = copy.deepcopy(tc_args)
    desc = out.get("description")
    if isinstance(desc, str):
        out["description"] = redact_host_paths_in_text(desc)
    return out
