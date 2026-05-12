"""Tests for resolving LLM-visible sample paths to upload files."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.analyze_request_context import (
    reset_analyze_request_context,
    set_analyze_request_context,
)
from app.backends.workspace_scope import (
    reset_workspace_scope_root,
    set_workspace_scope_root,
)
from app.services.sample_path_resolver import CurrentRequestSamplePathResolver


@pytest.fixture()
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(root))
    from app.config.settings import get_settings

    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


def _bind_request(*, user_id: str | None, session_id: str, project_id: str | None):
    scope = (
        f"/u_{user_id}/p_{project_id}"
        if user_id and project_id
        else f"/s_{session_id}"
        if not user_id
        else f"/u_{user_id}/default"
    )
    scope_tok = set_workspace_scope_root(scope)
    ctx_toks = set_analyze_request_context(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        request_id="req-test",
    )
    return scope_tok, ctx_toks


def _reset_request(scope_tok, ctx_toks) -> None:
    reset_workspace_scope_root(scope_tok)
    reset_analyze_request_context(*ctx_toks)


def test_resolves_workspace_path_under_current_owner(upload_dir: Path) -> None:
    target = upload_dir / "u_alice" / "p_proj1" / "sample.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    scope_tok, ctx_toks = _bind_request(
        user_id="alice", session_id="sess1", project_id="proj1"
    )
    try:
        resolved = CurrentRequestSamplePathResolver().resolve("/workspace/sample.exe")
    finally:
        _reset_request(scope_tok, ctx_toks)

    assert resolved is not None
    assert resolved.host_path == target
    assert resolved.display_path == "/workspace/sample.exe"


def test_resolves_legacy_upload_path_with_authorization(upload_dir: Path) -> None:
    target = upload_dir / "u_alice" / "p_proj1" / "sample.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    scope_tok, ctx_toks = _bind_request(
        user_id="alice", session_id="sess1", project_id="proj1"
    )
    try:
        resolved = CurrentRequestSamplePathResolver().resolve(
            "/uploads/u_alice/p_proj1/sample.exe"
        )
    finally:
        _reset_request(scope_tok, ctx_toks)

    assert resolved is not None
    assert resolved.host_path == target
    assert resolved.display_path == "/workspace/sample.exe"


def test_rejects_legacy_upload_path_for_other_project(upload_dir: Path) -> None:
    target = upload_dir / "u_alice" / "p_other" / "sample.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    scope_tok, ctx_toks = _bind_request(
        user_id="alice", session_id="sess1", project_id="proj1"
    )
    try:
        with pytest.raises(PermissionError):
            CurrentRequestSamplePathResolver().resolve(
                "/uploads/u_alice/p_other/sample.exe"
            )
    finally:
        _reset_request(scope_tok, ctx_toks)


def test_resolves_user_default_upload_for_project_analyze(upload_dir: Path) -> None:
    target = upload_dir / "u_alice" / "default" / "sample.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    scope_tok, ctx_toks = _bind_request(
        user_id="alice", session_id="sess1", project_id="proj1"
    )
    try:
        resolved = CurrentRequestSamplePathResolver().resolve("/workspace/sample.exe")
    finally:
        _reset_request(scope_tok, ctx_toks)

    assert resolved is not None
    assert resolved.host_path == target

