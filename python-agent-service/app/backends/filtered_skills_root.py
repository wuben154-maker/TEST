"""Filesystem backend view that exposes only selected child skill package directories."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from app._vendor.deepagents.backends.filesystem import FilesystemBackend
from app._vendor.deepagents.backends.protocol import FileDownloadResponse, FileInfo, LsResult


def _first_path_segment(virtual_path: str) -> str | None:
    parts = [p for p in virtual_path.replace("\\", "/").split("/") if p]
    return parts[0] if parts else None


class FilteredChildDirsFilesystemBackend:
    """Wrap a virtual-mode FilesystemBackend; only allowed immediate child dirs are visible."""

    def __init__(self, inner: FilesystemBackend, allowed_child_dirs: frozenset[str]) -> None:
        self._inner = inner
        self._allowed = allowed_child_dirs

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def ls(self, path: str) -> LsResult:
        norm = path if path.startswith("/") else "/" + path
        if norm.rstrip("/") in ("", "/"):
            out: list[FileInfo] = []
            for fi in (self._inner.ls("/").entries or []):
                if not fi.get("is_dir"):
                    continue
                seg = PurePosixPath(fi["path"].rstrip("/")).name
                if seg in self._allowed:
                    out.append(fi)
            return LsResult(entries=out)
        top = _first_path_segment(norm)
        if top and top not in self._allowed:
            return LsResult(entries=[])
        return self._inner.ls(norm)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            top = _first_path_segment(path)
            if top and top not in self._allowed:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
                continue
            responses.extend(self._inner.download_files([path]))
        return responses
