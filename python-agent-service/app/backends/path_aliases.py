"""Path-alias wrapper that normalizes agent-supplied paths before routing.

The LLM / UI presents files under the virtual ``/workspace/`` root, but the
agent occasionally produces malformed variants that break routing:

* ``Workspace/x`` / ``/Workspace/x`` — legacy PascalCase paste; folded to
  ``/workspace/...`` (user-facing SSE scrub now emits lowercase ``workspace/...``).
* ``/workspace/u_<id>/p_<id>/x`` or ``/workspace/u_<id>/default/x`` — stale
  owner-scoped paths copied from an earlier UI build. ``WorkspaceFacadeBackend``
  then prepends the owner root again, yielding a non-existent double-nested
  path.
* ``/workspace/s_<id>/x`` — same, for anonymous sessions.

:class:`PathAliasBackend` sits on the outside of :class:`CompositeBackend`
and rewrites the path argument of every inbound call. It performs no
routing or IO of its own — purely path canonicalization. Authoritative
multi-tenant isolation still comes from
``WorkspaceScopedFilesystemBackend`` via ContextVar; this wrapper is a
UX-robustness layer only.
"""

from __future__ import annotations

import re
from typing import Any

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

# Strip ``/workspace/<owner_segment>`` prefixes left over from pre-scrub UI
# versions. The segment shapes match what ``owner_segment()`` produces:
#   * u_<uid>/p_<pid>   — logged-in user + project
#   * u_<uid>/default   — logged-in user, no project
#   * s_<sid>           — anonymous session
_OWNER_SEG_RE = re.compile(
    r"^/workspace/(?:u_[\w.-]+/(?:p_[\w.-]+|default)|s_[\w.-]+)(?=/|$)"
)


def fold_workspace_ui_spelling(path: str) -> str:
    """Fold UI PascalCase ``Workspace`` onto ``/workspace`` (segment-safe).

    Does **not** strip owner segments (``u_/p_/s_``); use that only in
    :func:`canonicalize_agent_path` so upload disk resolution keeps full
    ``u_<id>/...`` tails.
    """
    if not path:
        return path
    p = path.replace("\\", "/")
    if p.startswith("/Workspace/") or p == "/Workspace":
        return "/workspace" + p[len("/Workspace") :]
    if p.lower() == "workspace":
        return "/workspace"
    if p.lower().startswith("workspace/"):
        return "/workspace/" + p.split("/", 1)[1]
    return p


def canonicalize_agent_path(path: str) -> str:
    """Return the canonical virtual-path form of ``path``.

    Idempotent. Only rewrites things that look like ``/workspace/``
    variants; any path outside that namespace is returned verbatim so
    ``/skills/``, ``/memories/``, ``/uploads/`` etc. keep working.
    """
    if not path:
        return path

    p = fold_workspace_ui_spelling(path)

    if not p.startswith("/"):
        return path  # not a virtual path; hand off untouched

    p = _OWNER_SEG_RE.sub("/workspace", p)

    while "//" in p:
        p = p.replace("//", "/")

    return p or path


class PathAliasBackend(BackendProtocol):
    """Canonicalize agent paths, then delegate to ``inner``.

    Every path-accepting method in :class:`BackendProtocol` is wrapped.
    Sync and async variants share the same rewrite helper.
    """

    def __init__(self, inner: BackendProtocol) -> None:
        self._inner = inner

    # ------------------------------------------------------------------ ls
    def ls(self, path: str) -> LsResult:
        return self._inner.ls(canonicalize_agent_path(path))

    async def als(self, path: str) -> LsResult:
        return await self._inner.als(canonicalize_agent_path(path))

    # ------------------------------------------------------------------ read
    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        return self._inner.read(
            canonicalize_agent_path(file_path), offset=offset, limit=limit
        )

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        return await self._inner.aread(
            canonicalize_agent_path(file_path), offset=offset, limit=limit
        )

    # ------------------------------------------------------------------ write
    def write(self, file_path: str, content: str) -> WriteResult:
        return self._inner.write(canonicalize_agent_path(file_path), content)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await self._inner.awrite(canonicalize_agent_path(file_path), content)

    # ------------------------------------------------------------------ edit
    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self._inner.edit(
            canonicalize_agent_path(file_path),
            old_string,
            new_string,
            replace_all=replace_all,
        )

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return await self._inner.aedit(
            canonicalize_agent_path(file_path),
            old_string,
            new_string,
            replace_all=replace_all,
        )

    # ------------------------------------------------------------------ glob
    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        return self._inner.glob(pattern, path=canonicalize_agent_path(path))

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        return await self._inner.aglob(pattern, path=canonicalize_agent_path(path))

    # ------------------------------------------------------------------ grep
    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        normalized = canonicalize_agent_path(path) if path else path
        return self._inner.grep(pattern, path=normalized, glob=glob)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        normalized = canonicalize_agent_path(path) if path else path
        return await self._inner.agrep(pattern, path=normalized, glob=glob)

    # --------------------------------------------------------- execute pass-through
    def execute(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - trivial
        return self._inner.execute(*args, **kwargs)

    async def aexecute(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        return await self._inner.aexecute(*args, **kwargs)

    # --------------------------------------------------------- upload/download
    def upload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        return self._inner.upload_files(
            [(canonicalize_agent_path(p), data) for p, data in files]
        )

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        return await self._inner.aupload_files(
            [(canonicalize_agent_path(p), data) for p, data in files]
        )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._inner.download_files([canonicalize_agent_path(p) for p in paths])

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await self._inner.adownload_files(
            [canonicalize_agent_path(p) for p in paths]
        )


__all__ = [
    "PathAliasBackend",
    "canonicalize_agent_path",
    "fold_workspace_ui_spelling",
]
