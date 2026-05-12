"""Owner-scoped ``StoreBackend`` wrapper.

``/memories/`` and ``/parameters/`` are routed to a single in-memory
:class:`~app.backends.store.InMemoryStore`. Without scoping, every user /
session would share the same namespace — a logged-in user could then read
another user's memories simply by calling ``read_file('/memories/foo')``.

``OwnerScopedStoreBackend`` resolves the per-request owner
(``u_<uid>/p_<pid>`` or ``s_<sid>``) from :mod:`app.backends.workspace_scope`
and qualifies the underlying store namespace with it. The exposed virtual
paths stay clean (``/memories/...``); only the backing namespace changes, so
cross-owner isolation is enforced at the store layer.

Calls that happen outside a request context (startup warmups, unit tests)
fall back to an ``_unscoped`` namespace so behaviour stays deterministic.
"""

from __future__ import annotations

from typing import Any

from app._vendor.deepagents.backends.protocol import BackendProtocol
from app.backends.store import InMemoryStore, StoreBackend
from app.backends.workspace_scope import get_workspace_scope_root

_FALLBACK_OWNER = "_unscoped"


def _owner_key() -> str:
    """Flatten the per-request owner root into a namespace-safe key."""
    root = get_workspace_scope_root() or ""
    cleaned = root.strip("/").replace("/", "__")
    return cleaned or _FALLBACK_OWNER


class OwnerScopedStoreBackend(BackendProtocol):
    """Delegate to ``StoreBackend`` with a dynamically-scoped namespace.

    A new ``StoreBackend`` is constructed per call (cheap — it only captures
    a namespace string + a shared ``BaseStore`` reference) so each dispatch
    uses the current request's owner key.
    """

    def __init__(
        self,
        *,
        base_namespace: str,
        store: Any | None = None,
    ) -> None:
        self._base_namespace = base_namespace
        self._store = store or InMemoryStore()

    def _delegate(self) -> StoreBackend:
        ns = f"{self._base_namespace}/{_owner_key()}"
        return StoreBackend(self._store, namespace=ns)

    # ----- sync BackendProtocol methods -----------------------------------
    def ls(self, path):  # type: ignore[override]
        return self._delegate().ls(path)

    def read(self, file_path, offset: int = 0, limit: int = 2000):  # type: ignore[override]
        return self._delegate().read(file_path, offset=offset, limit=limit)

    def write(self, file_path, content):  # type: ignore[override]
        return self._delegate().write(file_path, content)

    def edit(self, file_path, old_string, new_string, *, replace_all: bool = False):  # type: ignore[override]
        return self._delegate().edit(
            file_path, old_string, new_string, replace_all=replace_all
        )

    def glob(self, pattern, path: str = "/"):  # type: ignore[override]
        return self._delegate().glob(pattern, path=path)

    def grep(self, pattern, path=None, glob=None):  # type: ignore[override]
        return self._delegate().grep(pattern, path=path, glob=glob)

    def upload_files(self, files):  # type: ignore[override]
        return self._delegate().upload_files(files)

    def download_files(self, paths):  # type: ignore[override]
        return self._delegate().download_files(paths)

    # ----- async BackendProtocol methods ----------------------------------
    async def als(self, path):  # type: ignore[override]
        return await self._delegate().als(path)

    async def aread(self, file_path, offset: int = 0, limit: int = 2000):  # type: ignore[override]
        return await self._delegate().aread(file_path, offset=offset, limit=limit)

    async def awrite(self, file_path, content):  # type: ignore[override]
        return await self._delegate().awrite(file_path, content)

    async def aedit(self, file_path, old_string, new_string, *, replace_all: bool = False):  # type: ignore[override]
        return await self._delegate().aedit(
            file_path, old_string, new_string, replace_all=replace_all
        )

    async def aglob(self, pattern, path: str = "/"):  # type: ignore[override]
        return await self._delegate().aglob(pattern, path=path)

    async def agrep(self, pattern, path=None, glob=None):  # type: ignore[override]
        return await self._delegate().agrep(pattern, path=path, glob=glob)

    async def aupload_files(self, files):  # type: ignore[override]
        return await self._delegate().aupload_files(files)

    async def adownload_files(self, paths):  # type: ignore[override]
        return await self._delegate().adownload_files(paths)


__all__ = ["OwnerScopedStoreBackend"]
