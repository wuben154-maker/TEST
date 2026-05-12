"""Unit tests for workspace → sandbox staging helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.analyze_request_context import reset_analyze_request_context, set_analyze_request_context
from app.backends.workspace_scope import workspace_scope
from app.services.upload_path_auth import owner_segment
from app.tools.sandbox_workspace_stage import (
    extract_workspace_paths_from_command,
    prepare_workspace_staging,
    rewrite_command_workspace_paths,
    staging_workspace_prefix,
    strip_workspace_staging_for_guard,
)


@pytest.fixture()
def staged_upload_layout(tmp_path: Path) -> tuple[Path, str]:
    """Anonymous owner tree + sample file."""
    sid = "sess-stage-test"
    owner = owner_segment(user_id=None, session_id=sid, project_id=None)
    owner_dir = tmp_path / owner
    owner_dir.mkdir(parents=True)
    sample = owner_dir / "sample.php"
    sample.write_bytes(b"<?php // staging test")
    return tmp_path, sid


def test_extract_workspace_paths_from_command_finds_tokens() -> None:
    cmd = 'echo hi && cat /workspace/sample.php && ls "/uploads/u_x/y/z"'
    got = extract_workspace_paths_from_command(cmd)
    assert "/workspace/sample.php" in got
    assert "/uploads/u_x/y/z" in got


def test_rewrite_command_workspace_paths() -> None:
    reps = [("/workspace/a.php", "/workspace/p_demo_session/a.php")]
    assert rewrite_command_workspace_paths("cat /workspace/a.php", reps) == (
        "cat /workspace/p_demo_session/a.php"
    )


def test_prepare_workspace_staging_reads_short_workspace_path(
    staged_upload_layout: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_root, sid = staged_upload_layout
    mock_settings = MagicMock()
    mock_settings.upload_dir = upload_root
    mock_settings.max_upload_bytes_per_file = 100_000_000
    mock_settings.allow_legacy_flat_upload_paths = True
    monkeypatch.setattr(
        "app.tools.sandbox_workspace_stage.get_settings",
        lambda: mock_settings,
    )

    ut, pt, rt, st = set_analyze_request_context(
        user_id=None,
        project_id=None,
        request_id="",
        session_id=sid,
    )
    owner_slash = "/" + owner_segment(user_id=None, session_id=sid, project_id=None)
    try:
        with workspace_scope(owner_slash):
            uploads, replacements, err = prepare_workspace_staging(
                workspace_stage_paths=["/workspace/sample.php"],
                command="",
                auto_extract_from_command=False,
                upload_dir=upload_root,
                max_bytes_per_file=mock_settings.max_upload_bytes_per_file,
            )
            assert err is None
            assert len(uploads) == 1
            dest, raw = uploads[0]
            assert dest.startswith("/workspace/")
            assert dest.endswith("/sample.php")
            assert len(replacements) >= 1
    finally:
        reset_analyze_request_context(ut, pt, rt, st)


def test_strip_workspace_staging_masks_for_guard() -> None:
    ut, pt, rt, st = set_analyze_request_context(
        user_id=None,
        project_id="p_xyz_demo",
        request_id="",
        session_id="sess",
    )
    try:
        prefix = staging_workspace_prefix()
        assert prefix == "/workspace/p_xyz_demo/"
        line = f"cat {prefix}sample.php && echo done"
        masked = strip_workspace_staging_for_guard(line)
        assert "sample.php" not in masked
        assert "done" in masked
    finally:
        reset_analyze_request_context(ut, pt, rt, st)
