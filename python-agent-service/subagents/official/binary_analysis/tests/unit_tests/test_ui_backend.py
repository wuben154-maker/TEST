"""Unit tests for :class:`binary_analysis.ui_backend.UploadsStateBackend`.

The adapter is composed into a :class:`CompositeBackend` in production
(see :mod:`langgraph_entry`), so the tests exercise both
the adapter in isolation *and* the composition against a disk-backed
:class:`FilesystemBackend` — that is the wiring deep-agents-ui actually
hits and the regression surface we care about.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend

from ui_backend import ROUTE_PREFIX, UploadsStateBackend


@dataclass
class _FakeRuntime:
    """Minimal ``ToolRuntime`` stand-in exposing only ``state``."""

    state: dict[str, Any] = field(default_factory=dict)


@pytest.fixture()
def skills_root(tmp_path: Path) -> Path:
    """Disk-backed skills root with one SKILL.md file."""
    skill_dir = tmp_path / "proto-pe"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Proto: PE\n\nA sample skill for tests.\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture()
def runtime_with_upload() -> _FakeRuntime:
    """Runtime carrying a base64 ``uploaded/calc.exe`` blob — the exact
    shape deep-agents-ui produces for a binary attachment.
    """
    encoded = base64.standard_b64encode(b"MZhello").decode("ascii")
    return _FakeRuntime(state={"files": {"uploaded/calc.exe": encoded}})


@pytest.fixture()
def composite(skills_root: Path, runtime_with_upload: _FakeRuntime) -> CompositeBackend:
    """Composite backend mirroring the LangGraph dev entrypoint wiring."""
    return CompositeBackend(
        default=FilesystemBackend(root_dir=skills_root, virtual_mode=True),
        routes={ROUTE_PREFIX: UploadsStateBackend(runtime_with_upload)},
    )


# ---------------------------------------------------------------------------
# Adapter in isolation
# ---------------------------------------------------------------------------


def test_adapter_maps_stripped_path_to_ui_state_key(
    runtime_with_upload: _FakeRuntime,
) -> None:
    """``CompositeBackend`` passes us ``/calc.exe`` after stripping the
    route prefix; we must still find ``state.files['uploaded/calc.exe']``.
    """
    backend = UploadsStateBackend(runtime_with_upload)

    content = backend.read("/calc.exe")
    assert "MZhello" in content


def test_adapter_read_missing_returns_error(
    runtime_with_upload: _FakeRuntime,
) -> None:
    backend = UploadsStateBackend(runtime_with_upload)
    assert "not found" in backend.read("/missing.bin")


def test_adapter_ls_lists_uploads_with_virtual_paths(
    runtime_with_upload: _FakeRuntime,
) -> None:
    backend = UploadsStateBackend(runtime_with_upload)
    entries = backend.ls_info("/")
    paths = {info.get("path") for info in entries}
    assert paths == {"/calc.exe"}


def test_adapter_glob_matches_uploads(
    runtime_with_upload: _FakeRuntime,
) -> None:
    backend = UploadsStateBackend(runtime_with_upload)
    matches = {info.get("path") for info in backend.glob_info("*.exe", "/")}
    assert matches == {"/calc.exe"}


def test_adapter_write_is_rejected(runtime_with_upload: _FakeRuntime) -> None:
    backend = UploadsStateBackend(runtime_with_upload)
    result = backend.write("/new.bin", "nope")
    assert result.error is not None
    assert "read-only" in result.error


def test_adapter_edit_is_rejected(runtime_with_upload: _FakeRuntime) -> None:
    backend = UploadsStateBackend(runtime_with_upload)
    result = backend.edit("/calc.exe", "MZhello", "xx")
    assert result.error is not None
    assert "read-only" in result.error


def test_adapter_ignores_non_upload_state_entries(
    runtime_with_upload: _FakeRuntime,
) -> None:
    """Entries not living under the ``uploaded/`` namespace must not leak
    through to the agent — they belong to deepagents' default backend.
    """
    runtime_with_upload.state["files"]["scratch.md"] = "not an upload"
    runtime_with_upload.state["files"]["/notes.md"] = "also not an upload"

    backend = UploadsStateBackend(runtime_with_upload)
    paths = {info.get("path") for info in backend.ls_info("/")}
    assert paths == {"/calc.exe"}


def test_adapter_download_files_returns_upload_bytes(
    runtime_with_upload: _FakeRuntime,
) -> None:
    backend = UploadsStateBackend(runtime_with_upload)
    responses = backend.download_files(["/calc.exe"])
    assert len(responses) == 1
    assert responses[0].error is None
    assert responses[0].content == b"MZhello"


def test_adapter_tolerates_missing_state_files(skills_root: Path) -> None:
    backend = UploadsStateBackend(_FakeRuntime())
    assert backend.ls_info("/") == []
    assert "not found" in backend.read("/any.bin")


# ---------------------------------------------------------------------------
# CompositeBackend integration — the wiring deep-agents-ui actually uses
# ---------------------------------------------------------------------------


def test_composite_root_lists_skills_and_uploaded_dir(
    composite: CompositeBackend,
) -> None:
    """``ls /`` must surface both disk skills and the ``/uploaded/`` route."""
    paths = {info.get("path") for info in composite.ls_info("/")}
    assert "/uploaded/" in paths
    # FilesystemBackend(virtual_mode=True) reports skill dirs with a
    # trailing slash.
    assert "/proto-pe/" in paths or "/proto-pe" in paths


def test_composite_routes_uploaded_dir_listing(
    composite: CompositeBackend,
) -> None:
    """``ls /uploaded/`` must delegate to the uploads adapter and
    re-prepend the route prefix on returned paths."""
    paths = {info.get("path") for info in composite.ls_info("/uploaded/")}
    assert paths == {"/uploaded/calc.exe"}


def test_composite_read_routes_to_uploads_backend(
    composite: CompositeBackend,
) -> None:
    """Reading via the full ``/uploaded/...`` path must hit the adapter."""
    content = composite.read("/uploaded/calc.exe")
    assert "MZhello" in content


def test_composite_read_routes_to_disk_for_skills(
    composite: CompositeBackend, skills_root: Path
) -> None:
    """Reads under the default namespace still hit the disk backend."""
    content = composite.read("/proto-pe/SKILL.md")
    assert "Proto: PE" in content
    # Sanity: the file is actually on disk.
    assert (skills_root / "proto-pe" / "SKILL.md").exists()


def test_composite_glob_aggregates_across_backends(
    composite: CompositeBackend,
) -> None:
    """``glob`` at ``/`` must merge results from both legs."""
    matches = {info.get("path") for info in composite.glob_info("**/*", "/")}
    # Expect at least one disk match and the upload.
    assert any(p and "proto-pe" in p and "SKILL.md" in p for p in matches), matches
    assert "/uploaded/calc.exe" in matches


def test_composite_write_to_upload_is_rejected(
    composite: CompositeBackend,
) -> None:
    """``CompositeBackend`` routes the write → adapter returns read-only."""
    result = composite.write("/uploaded/new.bin", "nope")
    assert result.error is not None
    assert "read-only" in result.error
