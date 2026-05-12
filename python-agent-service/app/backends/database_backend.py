"""Database Backend - Implements BackendProtocol for Supabase and PostgreSQL.

Fully compatible with official deepagents BackendProtocol. Alternative to
StoreBackend when using Supabase/PostgreSQL instead of LangGraph BaseStore.

- Official StoreBackend: Requires ToolRuntime + LangGraph BaseStore
- DatabaseBackend: Uses PostgresStore/SupabaseStore (get/set/list_keys interface)

Supports:
- DATABASE_MODE=local: PostgreSQL via asyncpg (PostgresStore)
- DATABASE_MODE=supabase: Supabase client (agent_store table)

Used for persistent storage of memories and parameters in create_layered_backend routes.
"""

import asyncio
import fnmatch
from typing import Any

import structlog

from app._vendor.deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)

logger = structlog.get_logger()


def _run_async(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    return asyncio.run(coro)


class DatabaseBackend(BackendProtocol):
    """Backend that stores files in database (PostgreSQL or Supabase).

    Implements official BackendProtocol from deepagents. Files are stored as
    path -> content in the agent_store (namespace + key structure).
    """

    def __init__(self, namespace: str = "files", store: Any = None):
        """Initialize database backend.

        Args:
            namespace: Store namespace for file paths (e.g., "memories", "parameters").
            store: BaseStore instance (PostgresStore, InMemoryStore, or SupabaseStore).
                   If None, creates store based on DATABASE_MODE from settings.
        """
        self.namespace = namespace
        self._store = store
        self._store_instance = None

    def _get_store(self):
        """Lazy-init store based on settings."""
        if self._store_instance is not None:
            return self._store_instance
        if self._store is not None:
            self._store_instance = self._store
            return self._store_instance

        from app.config import get_settings
        settings = get_settings()

        if settings.database_mode == "supabase":
            from app.backends.supabase_store import SupabaseStore
            self._store_instance = SupabaseStore()
        else:
            from app.backends.store import PostgresStore, StoreConfig
            self._store_instance = PostgresStore(StoreConfig())
        return self._store_instance

    def _path_to_key(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _validate_path(self, path: str) -> str:
        if ".." in path:
            raise ValueError(f"Path traversal not allowed: {path}")
        return self._path_to_key(path)

    def ls_info(self, path: str) -> list[FileInfo]:
        path = self._validate_path(path)
        if not path.endswith("/"):
            path += "/"

        keys = _run_async(self._get_store().list_keys(self.namespace, path))

        seen_dirs: set[str] = set()
        infos: list[FileInfo] = []

        for key in keys:
            relative = key[len(path):]
            if "/" in relative:
                dir_name = relative.split("/")[0]
                subdir = path + dir_name + "/"
                if subdir not in seen_dirs:
                    seen_dirs.add(subdir)
                    name = dir_name
                    infos.append(FileInfo(path=subdir, is_dir=True, size=0, modified_at=""))
            else:
                infos.append(FileInfo(path=key, is_dir=False, size=0, modified_at=""))

        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        path = self._validate_path(file_path)
        key = self._path_to_key(path)

        item = _run_async(self._get_store().get(key, self.namespace))
        if not item:
            return f"Error: File not found: {file_path}"

        content = item.value if isinstance(item.value, str) else str(item.value)
        lines = content.split("\n")

        if not content or (len(lines) == 1 and lines[0] == ""):
            return "File exists but is empty."

        selected = lines[offset : offset + limit]
        result = []
        for i, line in enumerate(selected, start=offset + 1):
            result.append(f"{i:6d}\t{line}")
        total = len(lines)
        shown = len(selected)
        header = f"[Lines {offset + 1}-{offset + shown} of {total}]\n"
        return header + "\n".join(result)

    def write(self, file_path: str, content: str) -> WriteResult:
        path = self._validate_path(file_path)
        key = self._path_to_key(path)

        try:
            _run_async(self._get_store().set(key, content, self.namespace))
            return WriteResult(error=None, path=path, files_update=None)
        except Exception as e:
            logger.error("DatabaseBackend write failed", path=path, error=str(e))
            return WriteResult(error=str(e), path=None, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        path = self._validate_path(file_path)
        key = self._path_to_key(path)

        item = _run_async(self._get_store().get(key, self.namespace))
        if not item:
            return EditResult(error=f"File not found: {file_path}")

        content = item.value if isinstance(item.value, str) else str(item.value)
        if old_string not in content:
            return EditResult(error="Pattern not found in file")

        if replace_all:
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            count = 1

        try:
            _run_async(self._get_store().set(key, new_content, self.namespace))
            return EditResult(error=None, path=path, files_update=None, occurrences=count)
        except Exception as e:
            logger.error("DatabaseBackend edit failed", path=path, error=str(e))
            return EditResult(error=str(e))

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        path = self._validate_path(path)
        if not path.endswith("/"):
            path += "/"

        keys = _run_async(self._get_store().list_keys(self.namespace, path))
        infos: list[FileInfo] = []

        for key in keys:
            if fnmatch.fnmatch(key, pattern) or fnmatch.fnmatch(key.split("/")[-1], pattern):
                infos.append(FileInfo(path=key, is_dir=False, size=0, modified_at=""))

        return infos

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        search_prefix = "" if path is None or path == "" else (path if path.endswith("/") else path + "/")
        keys = _run_async(self._get_store().list_keys(self.namespace, search_prefix))
        matches: list[GrepMatch] = []

        for key in keys:
            if search_prefix and not key.startswith(search_prefix):
                continue
            if glob and not fnmatch.fnmatch(key, glob):
                continue

            item = _run_async(self._get_store().get(key, self.namespace))
            if not item:
                continue

            content = item.value if isinstance(item.value, str) else str(item.value)
            lines = content.split("\n")

            for i, line in enumerate(lines, start=1):
                if pattern in line:
                    matches.append(GrepMatch(path=key, line=i, text=line))

        return matches

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files to store."""
        results: list[FileUploadResponse] = []
        for path, content in files:
            path = self._path_to_key(path)
            try:
                content_str = content.decode("utf-8", errors="replace")
                _run_async(self._get_store().set(path, content_str, self.namespace))
                results.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                logger.error("DatabaseBackend upload_files failed", path=path, error=str(e))
                results.append(FileUploadResponse(path=path, error="permission_denied"))
        return results

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from store."""
        results: list[FileDownloadResponse] = []
        for path in paths:
            path = self._path_to_key(path)
            item = _run_async(self._get_store().get(path, self.namespace))
            if not item:
                results.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))
                continue
            content = item.value if isinstance(item.value, str) else str(item.value)
            results.append(FileDownloadResponse(path=path, content=content.encode("utf-8"), error=None))
        return results
