"""StandaloneStateBackend: In-memory backend for use without ToolRuntime.

Used by middleware (FilesystemMiddleware, SummarizationMiddleware) when
ToolRuntime is not available (e.g. at init time). Does NOT sync with
LangGraph agent state. For agent file operations, use StateBackend(runtime)
via the BackendFactory.
"""

from typing import Any

from app.datetime_support import format_api_datetime, now_app

from app._vendor.deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from app._vendor.deepagents.backends.utils import (
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)
import wcmatch.glob as wcglob


class StandaloneStateBackend(BackendProtocol):
    """Ephemeral in-memory backend that does not require ToolRuntime.

    Use this when you need a BackendProtocol instance before the agent
    has a runtime (e.g. for middleware init). For agent-internal file
    operations, use StateBackend(runtime) via BackendFactory.
    """

    def __init__(self):
        """Initialize with empty file store."""
        self._files: dict[str, dict[str, Any]] = {}

    def _normalize_path(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _validate_path(self, path: str) -> str:
        if ".." in path:
            raise ValueError(f"Path traversal not allowed: {path}")
        return self._normalize_path(path)

    def ls_info(self, path: str) -> list[FileInfo]:
        path = self._validate_path(path)
        if not path.endswith("/"):
            path += "/"

        infos: list[FileInfo] = []
        subdirs: set[str] = set()

        for k, fd in self._files.items():
            if not k.startswith(path):
                continue
            relative = k[len(path) :]
            if "/" in relative:
                subdir_name = relative.split("/")[0]
                subdirs.add(path + subdir_name + "/")
                continue
            size = len("\n".join(fd.get("content", [])))
            infos.append(
                {
                    "path": k,
                    "is_dir": False,
                    "size": int(size),
                    "modified_at": fd.get("modified_at", ""),
                }
            )

        infos.extend(
            FileInfo(path=subdir, is_dir=True, size=0, modified_at="")
            for subdir in sorted(subdirs)
        )
        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        file_path = self._validate_path(file_path)
        if file_path not in self._files:
            return f"Error: File '{file_path}' not found"

        content = "\n".join(self._files[file_path].get("content", []))
        empty_msg = check_empty_content(content)
        if empty_msg:
            return empty_msg

        lines = content.splitlines()
        start_idx = offset
        end_idx = min(start_idx + limit, len(lines))
        if start_idx >= len(lines):
            return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"
        selected = lines[start_idx:end_idx]
        return format_content_with_line_numbers(selected, start_line=start_idx + 1)

    def write(self, file_path: str, content: str) -> WriteResult:
        file_path = self._validate_path(file_path)
        if file_path in self._files:
            return WriteResult(
                error=f"Cannot write to {file_path} because it already exists. "
                "Read and then make an edit, or write to a new path."
            )
        now = format_api_datetime(now_app())
        self._files[file_path] = {
            "content": content.split("\n"),
            "created_at": now,
            "modified_at": now,
        }
        return WriteResult(path=file_path, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        file_path = self._validate_path(file_path)
        if file_path not in self._files:
            return EditResult(error=f"Error: File '{file_path}' not found")

        content = "\n".join(self._files[file_path].get("content", []))
        result = perform_string_replacement(content, old_string, new_string, replace_all)
        if isinstance(result, str):
            return EditResult(error=result)
        new_content, occurrences = result
        self._files[file_path]["content"] = new_content.split("\n")
        self._files[file_path]["modified_at"] = format_api_datetime(now_app())
        return EditResult(path=file_path, files_update=None, occurrences=int(occurrences))

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        search_path = self._validate_path(path or "/")
        matches: list[GrepMatch] = []
        for file_path, fd in self._files.items():
            if not file_path.startswith(search_path):
                continue
            if glob:
                name = file_path.split("/")[-1]
                if not wcglob.globmatch(name, glob, flags=wcglob.BRACE | wcglob.GLOBSTAR):
                    continue
            for line_num, line in enumerate(fd.get("content", []), 1):
                if pattern in line:
                    matches.append({"path": file_path, "line": line_num, "text": line})
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        path = self._validate_path(path)
        results: list[FileInfo] = []
        for file_path, fd in self._files.items():
            if not file_path.startswith(path):
                continue
            rel = file_path[len(path) :].lstrip("/")
            if not rel:
                continue
            if wcglob.globmatch(rel, pattern, flags=wcglob.BRACE | wcglob.GLOBSTAR):
                size = len("\n".join(fd.get("content", [])))
                results.append(
                    {
                        "path": file_path,
                        "is_dir": False,
                        "size": size,
                        "modified_at": fd.get("modified_at", ""),
                    }
                )
        results.sort(key=lambda x: x.get("path", ""))
        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        raise NotImplementedError(
            "StandaloneStateBackend does not support upload_files. "
            "Use invoke(files={...}) to pass files at invocation time."
        )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            path = self._validate_path(path)
            if path not in self._files:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
                continue
            content_str = "\n".join(self._files[path].get("content", []))
            responses.append(
                FileDownloadResponse(path=path, content=content_str.encode("utf-8"), error=None)
            )
        return responses
