"""Virtual ``/workspace/`` facade over a scoped filesystem backend.

The LLM and the frontend see every user-writable file under ``/workspace/…``
regardless of the real on-disk location. Internally those paths still resolve
to ``<upload_dir>/<owner_segment>/…`` so multi-tenant isolation holds.

This backend is mounted on ``CompositeBackend`` at the ``/workspace/`` route
and sits in front of ``WorkspaceScopedFilesystemBackend`` (which caps every
inner call to the owner's subtree via ContextVar).

Contract with ``CompositeBackend``:

* ``CompositeBackend`` strips the ``/workspace/`` prefix before dispatching,
  so ``facade.read("/a.txt")`` corresponds to the LLM-level
  ``/workspace/a.txt``. All path-accepting methods therefore receive
  **route-local suffixes** (``/`` or ``/<basename>/…``).
* Returned paths (``ls`` / ``glob`` / ``grep`` entries) must be emitted in
  the same route-local form because ``CompositeBackend`` re-prefixes them
  with ``/workspace`` before handing the response back to the tool. See
  ``_remap_file_info_path`` in the vendored composite backend.
* ``write`` / ``edit`` results have their ``path`` overwritten by the
  composite with the original caller-supplied path, so what the facade
  returns there is cosmetic; we still emit the full ``/workspace/…`` form
  to keep direct-callers (tests, scripts) behaving sensibly.

For backwards compatibility with callers that still hand us the full
``/workspace/x`` path (older tests, offline scripts), the suffix helpers
auto-strip a leading ``/workspace`` if present.
"""

from __future__ import annotations

from typing import Any

# NOTE: Vendored WriteResult / EditResult use @dataclass(init=False) with a
# custom __init__ that injects a sentinel for ``files_update``; we construct
# fresh instances via their public keyword arguments when rewriting paths.

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
from app.backends.constants import WORKSPACE_VIRTUAL_ROOT
from app.backends.workspace_scope import get_workspace_scope_root

_VIRTUAL_TRIM = WORKSPACE_VIRTUAL_ROOT.rstrip("/")  # "/workspace"

# Top-level namespaces that must never resolve under the workspace facade.
# CompositeBackend already routes these elsewhere, but direct callers (tests,
# scripts) may abuse the facade; we reject them explicitly to keep the
# isolation invariant regardless of entry point.
_FORBIDDEN_TOP_LEVEL: tuple[str, ...] = (
    "/memories",
    "/parameters",
    "/skills",
    "/uploads",
    "/reports",
    "/etc",
)


def _ensure_abs(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _owner_root() -> str:
    """Current per-request owner root (``/u_x/p_y`` or ``/s_x``), or ``/``."""
    root = get_workspace_scope_root()
    if not root:
        return "/"
    return root if root.startswith("/") else f"/{root}"


def _normalize_suffix(path: str) -> str | None:
    """Reduce ``path`` to a route-local suffix (``/`` or ``/<basename>/…``).

    Accepts three shapes so both the real CompositeBackend link and
    direct-call sites (tests / CLI) work:

    * CompositeBackend-stripped form — ``/`` or ``/file.txt``.
    * Legacy full virtual path — ``/workspace`` / ``/workspace/`` /
      ``/workspace/file.txt`` (prefix is trimmed in place).
    * Bare root ``""`` — treated as ``/``.

    Returns ``None`` for paths that clearly belong to another top-level
    route (``/memories/``, ``/etc/``, …). This is an explicit "out of
    scope" signal the caller converts into a user-visible error.
    """
    if not path:
        return "/"

    p = _ensure_abs(path)

    # Legacy form — strip the /workspace prefix so the rest of the logic
    # always reasons about a route-local suffix.
    if p == WORKSPACE_VIRTUAL_ROOT or p == _VIRTUAL_TRIM:
        return "/"
    if p.startswith(WORKSPACE_VIRTUAL_ROOT):
        p = p[len(_VIRTUAL_TRIM):] or "/"

    # Reject paths that escape into sibling top-level namespaces. Matches
    # both ``/etc`` (exact) and ``/etc/passwd`` (subpath).
    for forbidden in _FORBIDDEN_TOP_LEVEL:
        if p == forbidden or p.startswith(forbidden + "/"):
            return None

    if not p.startswith("/"):
        p = f"/{p}"
    return p


def _to_inner(path: str) -> str | None:
    """Translate a (possibly-legacy) facade path to the scoped inner path.

    Returns ``None`` when ``path`` is not under the workspace namespace so
    the caller can surface a dedicated error.
    """
    suffix = _normalize_suffix(path)
    if suffix is None:
        return None

    root = _owner_root()
    if root == "/" or root == "":
        # No owner bound (tests / offline): the inner backend is not
        # namespaced, so the suffix *is* the inner path.
        return suffix
    if suffix == "/":
        return root + "/"
    # Suffix already starts with '/'; join safely without double slash.
    return f"{root}{suffix}"


def _to_route_local(inner_path: str) -> str:
    """Translate an inner (scoped) path back into a route-local suffix.

    The returned value is what ``CompositeBackend`` expects from a routed
    backend: it will re-prefix this suffix with ``/workspace`` before
    handing the response to the tool caller.
    """
    p = _ensure_abs(inner_path)
    if p == "/":
        return "/"

    root = _owner_root().rstrip("/")
    if root and (p == root or p.startswith(root + "/")):
        tail = p[len(root):] or "/"
        return tail
    # No owner bound: pass the path through as-is.
    return p


def _to_full_virtual(inner_path: str) -> str:
    """Translate an inner path to the full ``/workspace/…`` form.

    Used for result fields that are presented to direct callers (tests)
    without going through ``CompositeBackend`` remapping. Within the real
    link these paths are usually overwritten by the composite so the exact
    value is cosmetic.
    """
    suffix = _to_route_local(inner_path)
    if suffix == "/":
        return WORKSPACE_VIRTUAL_ROOT
    return f"{_VIRTUAL_TRIM}{suffix}"


# Short error string returned to the LLM when a call lands on the workspace
# facade with a path that does not live under /workspace/.
_OUTSIDE_WORKSPACE_ERROR = "path must be under /workspace/"


class WorkspaceFacadeBackend(BackendProtocol):
    """Wrap a scoped filesystem backend and expose it as ``/workspace/``."""

    def __init__(self, inner: BackendProtocol) -> None:
        self._inner = inner

    # ------------------------------------------------------------------ ls
    def ls(self, path: str) -> LsResult:
        inner_path = _to_inner(path)
        if inner_path is None:
            return LsResult(error=_OUTSIDE_WORKSPACE_ERROR)
        result = self._inner.ls(inner_path)
        if result.error or not result.entries:
            return result
        rewritten = [
            {**entry, "path": _to_route_local(entry.get("path", ""))}
            for entry in result.entries
        ]
        return LsResult(entries=rewritten)

    # ------------------------------------------------------------------ read
    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        inner_path = _to_inner(file_path)
        if inner_path is None:
            # Legacy backends may return a plain string; keep the same shape.
            return f"Error: {_OUTSIDE_WORKSPACE_ERROR}"
        return self._inner.read(inner_path, offset=offset, limit=limit)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        inner_path = _to_inner(file_path)
        if inner_path is None:
            return f"Error: {_OUTSIDE_WORKSPACE_ERROR}"
        # BackendProtocol supplies a default aread(to_thread->read) for
        # backends that only implement sync I/O, so this delegation works
        # whether or not the inner chain is async-native.
        return await self._inner.aread(inner_path, offset=offset, limit=limit)

    # ------------------------------------------------------------------ write
    def write(self, file_path: str, content: str) -> WriteResult:
        inner_path = _to_inner(file_path)
        if inner_path is None:
            return WriteResult(error=_OUTSIDE_WORKSPACE_ERROR, path=None)
        res = self._inner.write(inner_path, content)
        if res.error or not res.path:
            return res
        return WriteResult(
            error=res.error,
            path=_to_full_virtual(res.path),
            files_update=res.files_update,
        )

    # ------------------------------------------------------------------ edit
    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        inner_path = _to_inner(file_path)
        if inner_path is None:
            return EditResult(error=_OUTSIDE_WORKSPACE_ERROR)
        res = self._inner.edit(
            inner_path, old_string, new_string, replace_all=replace_all
        )
        if res.error or not getattr(res, "path", None):
            return res
        return EditResult(
            error=res.error,
            path=_to_full_virtual(res.path),  # type: ignore[arg-type]
            files_update=res.files_update,
            occurrences=res.occurrences,
        )

    # ------------------------------------------------------------------ glob
    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        inner_path = _to_inner(path) if path else _to_inner("/")
        if inner_path is None:
            return GlobResult(error=_OUTSIDE_WORKSPACE_ERROR)
        res = self._inner.glob(pattern, path=inner_path)
        if res.error or not res.matches:
            return res
        rewritten = [
            {**m, "path": _to_route_local(m.get("path", ""))} for m in res.matches
        ]
        return GlobResult(matches=rewritten)

    # ------------------------------------------------------------------ grep
    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        if path is None:
            inner_path: str | None = None
        else:
            inner_path = _to_inner(path)
            if inner_path is None:
                return GrepResult(error=_OUTSIDE_WORKSPACE_ERROR)
        res = self._inner.grep(pattern, path=inner_path, glob=glob)
        if res.error or not res.matches:
            return res
        rewritten = []
        for m in res.matches:
            p = m.get("path")
            if isinstance(p, str) and p:
                rewritten.append({**m, "path": _to_route_local(p)})
            else:
                rewritten.append(m)
        return GrepResult(matches=rewritten)

    # --------------------------------------------------------- upload/download
    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        rewritten: list[tuple[str, bytes]] = []
        errors: list[FileUploadResponse] = []
        for p, data in files:
            inner_path = _to_inner(p)
            if inner_path is None:
                errors.append(
                    FileUploadResponse(path=p, error="permission_denied")
                )
            else:
                rewritten.append((inner_path, data))
        responses = self._inner.upload_files(rewritten) if rewritten else []
        remapped = [
            FileUploadResponse(path=_to_route_local(r.path), error=r.error)
            if r.path
            else r
            for r in responses
        ]
        return errors + remapped

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        inner_paths: list[str] = []
        denied: list[FileDownloadResponse] = []
        for p in paths:
            inner_path = _to_inner(p)
            if inner_path is None:
                denied.append(
                    FileDownloadResponse(
                        path=p, content=None, error="permission_denied"
                    )
                )
            else:
                inner_paths.append(inner_path)
        results = self._inner.download_files(inner_paths) if inner_paths else []
        remapped = [
            FileDownloadResponse(
                path=_to_route_local(r.path), content=r.content, error=r.error
            )
            if r.path
            else r
            for r in results
        ]
        return denied + remapped


__all__ = [
    "WorkspaceFacadeBackend",
]
