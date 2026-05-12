"""Per-request workspace sandbox: restrict the filesystem tools to one owner subtree.

A ContextVar carries the current request's ``owner_segment()`` value (e.g.
``/u_alice/p_proj1``). ``WorkspaceScopedFilesystemBackend`` wraps a disk-backed
``FilesystemBackend`` and enforces that every read/write/ls/glob/grep/execute
stays within that subtree. This enforcement lives one layer below
``WorkspaceFacadeBackend`` (virtual ``/workspace/`` ↔ physical ``/<owner>/``
translation), so both the LLM-visible namespace and the physical disk scope
agree on exactly the same subtree.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

from app._vendor.deepagents.backends.filesystem import FilesystemBackend
from app._vendor.deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    WriteResult,
)

# Stripped path inside the upload mount. Examples:
#   logged-in + project   -> "/u_alice/p_proj1"
#   logged-in, no project -> "/u_alice/default"
#   anonymous             -> "/s_session"
_workspace_scope_root: ContextVar[str | None] = ContextVar(
    "workspace_scope_root", default=None
)


def get_workspace_scope_root() -> str | None:
    return _workspace_scope_root.get()


def set_workspace_scope_root(root: str | None) -> Token:
    """Stripped form: /u_xxx/p_yyy (or /s_xxx), leading slash, no trailing slash."""
    return _workspace_scope_root.set(root)


def reset_workspace_scope_root(token: Token) -> None:
    _workspace_scope_root.reset(token)


@contextmanager
def workspace_scope(stripped_root: str | None) -> Iterator[None]:
    """Bind the sandbox for one analyze run (main + subagents on the same task)."""
    tok = set_workspace_scope_root(stripped_root)
    try:
        yield
    finally:
        reset_workspace_scope_root(tok)


def _normalize_inner_path(path: str) -> str:
    p = path if path.startswith("/") else f"/{path}"
    # Drop trailing slash for comparisons; keep the root "/" literal.
    return p.rstrip("/") or "/"


def _allowed(stripped_path: str, root: str) -> bool:
    p = _normalize_inner_path(stripped_path)
    r = _normalize_inner_path(root)
    if p == r:
        return True
    return p.startswith(r + "/")


# Short error string returned to the LLM when it attempts to touch something
# outside its workspace. Worded so the model backs off instead of retrying.
OUTSIDE_SCOPE_ERROR = "path outside your workspace"


class WorkspaceScopedFilesystemBackend(BackendProtocol):
    """Restrict ``FilesystemBackend`` to one owner directory via ContextVar.

    Semantics:
      * ``ls("/")`` / ``glob(pattern, path="/")`` are interpreted as "list the
        current owner subtree" — we rewrite the request to the scoped root.
      * Anything else must start with the scoped root. Out-of-scope calls
        receive a short, explicit error so the LLM gets actionable feedback
        (previously some paths returned empty results which misled agents).
    """

    def __init__(self, inner: FilesystemBackend) -> None:
        self._inner = inner

    def _root(self) -> str | None:
        return get_workspace_scope_root()

    def _deny(self, path: str) -> bool:
        root = self._root()
        if root is None:
            return False
        return not _allowed(path, root)

    def ls(self, path: str) -> LsResult:
        root = self._root()
        if root is None:
            return self._inner.ls(path)
        p = _normalize_inner_path(path)
        if p == "/":
            return self._inner.ls(root + "/")
        if self._deny(path):
            return LsResult(error=OUTSIDE_SCOPE_ERROR)
        return self._inner.ls(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        if self._deny(file_path):
            return f"Error: {OUTSIDE_SCOPE_ERROR}"
        return self._inner.read(file_path, offset=offset, limit=limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        if self._deny(file_path):
            return WriteResult(error=OUTSIDE_SCOPE_ERROR)
        return self._inner.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        if self._deny(file_path):
            return EditResult(error=OUTSIDE_SCOPE_ERROR)
        return self._inner.edit(
            file_path, old_string, new_string, replace_all=replace_all
        )

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        root = self._root()
        if root is None:
            return self._inner.grep(pattern, path=path, glob=glob)
        if path is None or _normalize_inner_path(path) == "/":
            return self._inner.grep(pattern, path=root + "/", glob=glob)
        if self._deny(path):
            return GrepResult(error=OUTSIDE_SCOPE_ERROR)
        return self._inner.grep(pattern, path=path, glob=glob)

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        root = self._root()
        if root is None:
            return self._inner.glob(pattern, path=path)
        if _normalize_inner_path(path) == "/":
            return self._inner.glob(pattern, path=root + "/")
        if self._deny(path):
            return GlobResult(error=OUTSIDE_SCOPE_ERROR)
        return self._inner.glob(pattern, path=path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        root = self._root()
        if root is None:
            return self._inner.upload_files(files)
        responses: list[FileUploadResponse] = []
        safe: list[tuple[str, bytes]] = []
        for path, data in files:
            if self._deny(path):
                responses.append(
                    FileUploadResponse(path=path, error="permission_denied")
                )
            else:
                safe.append((path, data))
        if safe:
            responses.extend(self._inner.upload_files(safe))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        if self._root() is None:
            return self._inner.download_files(paths)
        out: list[FileDownloadResponse] = []
        for p in paths:
            if self._deny(p):
                out.append(
                    FileDownloadResponse(
                        path=p, content=None, error="permission_denied"
                    )
                )
                continue
            out.extend(self._inner.download_files([p]))
        return out


__all__ = [
    "OUTSIDE_SCOPE_ERROR",
    "WorkspaceScopedFilesystemBackend",
    "get_workspace_scope_root",
    "reset_workspace_scope_root",
    "set_workspace_scope_root",
    "workspace_scope",
]
