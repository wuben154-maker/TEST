"""Resolve LLM-visible sample paths to authorized host upload files.

Binary-analysis tools should receive `/workspace/...` paths from the LLM/UI,
not host absolute paths. This resolver is the app-side bridge that maps those
virtual paths back to the current request's owner-scoped upload directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.analyze_request_context import (
    get_analyze_project_id,
    get_analyze_session_id,
    get_analyze_user_id,
)
from app.backends.constants import (
    DEFAULT_PROJECT_SEGMENT,
    USER_OWNER_PREFIX,
    WORKSPACE_VIRTUAL_ROOT,
)
from app.backends.path_aliases import fold_workspace_ui_spelling
from app.backends.workspace_scope import get_workspace_scope_root
from app.config import get_settings
from app.services.upload_path_auth import (
    authorize_virtual_path,
    owner_segment,
    sanitize_path_segment,
)

_UPLOADS_PREFIX = "/uploads/"


@dataclass(frozen=True)
class ResolvedSamplePath:
    """Authorized host file resolved from an agent-visible sample path."""

    kind: str
    host_path: Path
    display_path: str


def _ensure_abs(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _workspace_tail(path: str) -> str | None:
    p = fold_workspace_ui_spelling((path or "").strip())
    if not p:
        return None
    p = _ensure_abs(p)
    root = WORKSPACE_VIRTUAL_ROOT.rstrip("/")
    if p == root:
        return ""
    if p.startswith(WORKSPACE_VIRTUAL_ROOT):
        return p[len(root) :].lstrip("/")
    return None


def _current_owner_root() -> str:
    root = get_workspace_scope_root()
    if root:
        return root.strip("/")
    user_id = get_analyze_user_id()
    session_id = get_analyze_session_id() or "default"
    project_id = get_analyze_project_id()
    return owner_segment(user_id=user_id, session_id=session_id, project_id=project_id)


def _safe_join_upload(upload_dir: Path, owner: str, tail: str) -> Path:
    rel = Path(owner.strip("/")) / Path(tail)
    if not tail or ".." in Path(tail).parts:
        raise ValueError("Invalid workspace sample path")
    actual = (upload_dir / rel).resolve()
    upload_root = upload_dir.resolve()
    try:
        actual.relative_to(upload_root)
    except ValueError as exc:
        raise ValueError("Workspace sample path escapes upload root") from exc
    return actual


class CurrentRequestSamplePathResolver:
    """Resolve `/workspace/...` and legacy `/uploads/...` for the active request."""

    def resolve(self, path: str) -> ResolvedSamplePath | None:
        raw = (path or "").strip()
        if not raw:
            return None

        settings = get_settings()
        upload_dir = Path(settings.upload_dir)
        normalized = fold_workspace_ui_spelling(raw)
        normalized_abs = _ensure_abs(normalized)

        if normalized_abs.startswith(_UPLOADS_PREFIX):
            ok, disk, msg = authorize_virtual_path(
                normalized_abs,
                upload_dir=upload_dir,
                user_id=get_analyze_user_id(),
                session_id=get_analyze_session_id() or "default",
                project_id=get_analyze_project_id(),
                allow_legacy_flat=settings.allow_legacy_flat_upload_paths,
            )
            if not ok or disk is None:
                raise PermissionError(msg or "Upload path not authorized")
            display_path = f"{WORKSPACE_VIRTUAL_ROOT}{disk.name}"
            return ResolvedSamplePath(
                kind="host_upload",
                host_path=disk,
                display_path=display_path,
            )

        tail = _workspace_tail(normalized_abs)
        if tail is None:
            return None

        owner = _current_owner_root()
        candidates = [_safe_join_upload(upload_dir, owner, tail)]

        user_id = get_analyze_user_id()
        project_id = get_analyze_project_id()
        if user_id and project_id:
            default_owner = (
                f"{USER_OWNER_PREFIX}{sanitize_path_segment(user_id)}/"
                f"{DEFAULT_PROJECT_SEGMENT}"
            )
            default_candidate = _safe_join_upload(upload_dir, default_owner, tail)
            if default_candidate not in candidates:
                candidates.append(default_candidate)

        for candidate in candidates:
            if candidate.is_file():
                return ResolvedSamplePath(
                    kind="host_upload",
                    host_path=candidate,
                    display_path=f"{WORKSPACE_VIRTUAL_ROOT}{Path(tail).name}",
                )

        raise FileNotFoundError(f"Workspace sample path not found: {normalized_abs}")


def build_current_request_sample_path_resolver() -> CurrentRequestSamplePathResolver:
    """Factory used by the app-side binary-analysis registry adapter."""

    return CurrentRequestSamplePathResolver()

