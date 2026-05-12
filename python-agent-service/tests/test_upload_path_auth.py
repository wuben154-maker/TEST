"""Unit tests for upload virtual path authorization."""

from pathlib import Path

import pytest
from app.services.upload_path_auth import (
    authorize_virtual_path,
    owner_segment,
    resolve_upload_disk_path,
)


def test_owner_segment_user_only_defaults_project():
    # Logged-in without a project should get u_<uid>/default (two-level).
    assert owner_segment(user_id="abc-123", session_id="ignored") == "u_abc-123/default"


def test_owner_segment_user_plus_project():
    assert (
        owner_segment(user_id="alice", session_id="s1", project_id="proj1")
        == "u_alice/p_proj1"
    )


def test_owner_segment_anonymous_session():
    assert owner_segment(user_id=None, session_id="proj-1") == "s_proj-1"
    # project_id is silently ignored when user is missing (isolation still holds).
    assert (
        owner_segment(user_id=None, session_id="proj-1", project_id="ignored")
        == "s_proj-1"
    )


def test_owner_segment_sanitizes_illegal_chars():
    assert (
        owner_segment(user_id="u/../e", session_id="sess", project_id="p$%x")
        == "u_u_.._e/p_p__x"
    )


def test_resolve_upload_disk_path_legacy_uploads(tmp_path: Path):
    (tmp_path / "s_x").mkdir()
    (tmp_path / "s_x" / "a.txt").write_text("hi")
    p = resolve_upload_disk_path(tmp_path, "/uploads/s_x/a.txt")
    assert p.is_file()
    assert p.read_text() == "hi"


def test_resolve_upload_disk_path_workspace(tmp_path: Path):
    (tmp_path / "u_alice" / "p_proj1").mkdir(parents=True)
    (tmp_path / "u_alice" / "p_proj1" / "a.txt").write_text("hi")
    p = resolve_upload_disk_path(tmp_path, "/workspace/u_alice/p_proj1/a.txt")
    assert p.is_file()
    assert p.read_text() == "hi"


def test_resolve_upload_disk_path_workspace_pascal_case(tmp_path: Path):
    (tmp_path / "u_alice" / "p_proj1").mkdir(parents=True)
    (tmp_path / "u_alice" / "p_proj1" / "a.txt").write_text("hi")
    p = resolve_upload_disk_path(tmp_path, "/Workspace/u_alice/p_proj1/a.txt")
    assert p.is_file()
    assert p.read_text() == "hi"


def test_authorize_owned_path_anonymous(tmp_path: Path):
    (tmp_path / "s_sess").mkdir()
    (tmp_path / "s_sess" / "f.txt").write_text("x")
    ok, disk, msg = authorize_virtual_path(
        "/uploads/s_sess/f.txt",
        upload_dir=tmp_path,
        user_id=None,
        session_id="sess",
        allow_legacy_flat=True,
    )
    assert ok and disk and not msg


def test_authorize_owned_path_user_plus_project(tmp_path: Path):
    (tmp_path / "u_alice" / "p_proj1").mkdir(parents=True)
    (tmp_path / "u_alice" / "p_proj1" / "f.txt").write_text("x")
    ok, disk, msg = authorize_virtual_path(
        "/uploads/u_alice/p_proj1/f.txt",
        upload_dir=tmp_path,
        user_id="alice",
        session_id="s1",
        project_id="proj1",
    )
    assert ok and disk and not msg


def test_authorize_user_default_upload_for_project_scoped_analyze(tmp_path: Path):
    """Transition composer uploads to u_<uid>/default/ before a project id exists."""
    (tmp_path / "u_alice" / "default").mkdir(parents=True)
    (tmp_path / "u_alice" / "default" / "f.txt").write_text("x")
    ok, disk, msg = authorize_virtual_path(
        "/uploads/u_alice/default/f.txt",
        upload_dir=tmp_path,
        user_id="alice",
        session_id="new-proj-session",
        project_id="brand-new-proj",
    )
    assert ok and disk and not msg


def test_authorize_rejects_other_user_default_bucket(tmp_path: Path):
    (tmp_path / "u_bob" / "default").mkdir(parents=True)
    (tmp_path / "u_bob" / "default" / "f.txt").write_text("x")
    ok, _, msg = authorize_virtual_path(
        "/uploads/u_bob/default/f.txt",
        upload_dir=tmp_path,
        user_id="alice",
        session_id="s1",
        project_id="proj1",
    )
    assert not ok
    assert "not authorized" in (msg or "").lower()


def test_authorize_rejects_other_project(tmp_path: Path):
    (tmp_path / "u_alice" / "p_other").mkdir(parents=True)
    (tmp_path / "u_alice" / "p_other" / "f.txt").write_text("x")
    ok, _, msg = authorize_virtual_path(
        "/uploads/u_alice/p_other/f.txt",
        upload_dir=tmp_path,
        user_id="alice",
        session_id="s1",
        project_id="proj1",
    )
    assert not ok
    assert "not authorized" in (msg or "").lower()


def test_authorize_rejects_other_session(tmp_path: Path):
    (tmp_path / "s_other").mkdir()
    ok, _, msg = authorize_virtual_path(
        "/uploads/s_other/f.txt",
        upload_dir=tmp_path,
        user_id=None,
        session_id="mine",
        allow_legacy_flat=True,
    )
    assert not ok
    assert "not authorized" in (msg or "").lower() or "forbidden" in (msg or "").lower()


def test_authorize_rejects_user_accessing_session_prefix(tmp_path: Path):
    ok, _, _ = authorize_virtual_path(
        "/uploads/s_any/f.txt",
        upload_dir=tmp_path,
        user_id="user-1",
        session_id="sess",
        allow_legacy_flat=True,
    )
    assert not ok
