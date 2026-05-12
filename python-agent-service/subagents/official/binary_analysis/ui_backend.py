"""State-backed backend for deep-agents-ui uploads, routed via CompositeBackend.

Design
------

See https://docs.langchain.com/oss/python/deepagents/backends#compositebackend-router.

The BinaryAnalyst agent wants two independent filesystem surfaces:

1. A disk-backed view of the ``skills/`` tree so ``SkillsMiddleware`` (and
   the agent's ``read_file`` tool) can enumerate ``SKILL.md`` files.
2. A state-backed view of UI uploads so when a user attaches a sample
   through deep-agents-ui the agent's ``ls`` / ``read_file`` / ``glob``
   tools transparently see ``/uploaded/<name>``.

Instead of reimplementing the union manually, we delegate the routing to
the framework's :class:`CompositeBackend`:

```python
CompositeBackend(
    default=FilesystemBackend(root_dir=skills_root, virtual_mode=True),
    routes={"/uploaded/": UploadsStateBackend()},
)
```

``CompositeBackend`` strips the ``/uploaded/`` prefix before calling the
routed backend, and re-prepends it to paths in the backend's response.
deep-agents-ui, however, writes upload keys into ``state.files`` as
``"uploaded/<name>"`` (without a leading slash).
:class:`UploadsStateBackend` bridges that gap: it receives the
prefix-stripped path (e.g. ``"/calc.exe"``) and translates it back to the
UI-native state key (``"uploaded/calc.exe"``).

The adapter is intentionally thin — it understands exactly one
namespace and delegates nothing. Writes / edits are rejected because the
UI layer is the sole owner of the upload stream (the agent should only
read these files).
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, cast

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.utils import (
    _glob_search_files,
    create_file_data,
    file_data_to_string,
    format_read_response,
    grep_matches_from_files,
)
from deepagents.middleware.filesystem import FileData

if TYPE_CHECKING:  # pragma: no cover
    from langchain.tools import ToolRuntime

UI_STATE_PREFIX = "uploaded/"
ROUTE_PREFIX = "/uploaded/"
_READONLY_ERROR = (
    "/uploaded/ paths are managed by deep-agents-ui and are read-only for the agent."
)


def _decode_maybe_base64(raw: str) -> str:
    """Decode ``raw`` as base64 when possible; otherwise return unchanged.

    deep-agents-ui serialises binary attachments (``.exe``, ``.eml`` …) as
    a single base64 string. Plain-text attachments arrive unchanged;
    those should round-trip verbatim.
    """
    stripped = raw.strip()
    if not stripped:
        return ""
    try:
        decoded = base64.standard_b64decode(stripped)
    except (ValueError, TypeError):
        return raw
    return decoded.decode("utf-8", errors="replace")


def _to_file_data(value: Any) -> FileData:
    """Normalise a ``state.files`` value to the ``FileData`` shape."""
    if isinstance(value, dict) and "content" in value:
        return cast("FileData", value)
    if isinstance(value, str):
        return cast("FileData", create_file_data(_decode_maybe_base64(value)))
    return cast("FileData", create_file_data(""))


class UploadsStateBackend(BackendProtocol):
    """Read-only backend exposing ``state.files['uploaded/*']`` to the agent.

    Consumed via :class:`CompositeBackend` under the ``/uploaded/`` route.
    The routing layer strips the ``/uploaded/`` prefix before every call,
    so this backend sees request paths like ``/calc.exe``; internally it
    maps those back to the UI-owned state key ``uploaded/calc.exe``.

    Writes, edits and uploads are rejected — ``CompositeBackend`` never
    silently falls through on write failures, so the agent receives a
    clear "read-only" message instead of corrupting the UI's state.
    """

    def __init__(self, runtime: ToolRuntime) -> None:
        self.runtime = runtime

    # ------------------------------------------------------------------
    # Path translation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _state_key(stripped_path: str) -> str:
        """Map a post-routing path (``/calc.exe``) to the UI state key."""
        name = stripped_path.lstrip("/")
        return UI_STATE_PREFIX + name

    @staticmethod
    def _virtual_path(state_key: str) -> str | None:
        """Map a UI state key back to a route-stripped virtual path.

        Returns ``None`` for keys that do not live under the ``uploaded/``
        namespace so the adapter can safely ignore unrelated
        ``state.files`` entries (e.g. deepagents' own scratch files).
        """
        bare = state_key[1:] if state_key.startswith("/") else state_key
        if not bare.startswith(UI_STATE_PREFIX):
            return None
        return "/" + bare[len(UI_STATE_PREFIX) :]

    def _overlay(self) -> dict[str, FileData]:
        """Return ``{virtual_path: FileData}`` for every UI upload."""
        raw_files = self.runtime.state.get("files") if self.runtime.state else None
        if not isinstance(raw_files, dict):
            return {}
        overlay: dict[str, FileData] = {}
        for key, value in raw_files.items():
            if not isinstance(key, str):
                continue
            virtual = self._virtual_path(key)
            if virtual is None:
                continue
            overlay[virtual] = _to_file_data(value)
        return overlay

    # ------------------------------------------------------------------
    # Read-only surface
    # ------------------------------------------------------------------

    def ls_info(self, path: str) -> list[FileInfo]:
        overlay = self._overlay()
        normalised_path = path if path.endswith("/") else path + "/"

        infos: list[FileInfo] = []
        subdirs: set[str] = set()
        for virtual, file_data in overlay.items():
            if not virtual.startswith(normalised_path):
                continue
            relative = virtual[len(normalised_path) :]
            if "/" in relative:
                subdirs.add(normalised_path + relative.split("/")[0] + "/")
                continue
            content = file_data.get("content", [])
            infos.append(
                FileInfo(
                    path=virtual,
                    is_dir=False,
                    size=len("\n".join(content)),
                    modified_at=file_data.get("modified_at", ""),
                )
            )
        infos.extend(
            FileInfo(path=sub, is_dir=True, size=0, modified_at="")
            for sub in sorted(subdirs)
        )
        infos.sort(key=lambda info: info.get("path", ""))
        return infos

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        overlay = self._overlay()
        file_data = overlay.get(file_path)
        if file_data is None:
            return f"Error: File '{file_path}' not found"
        return format_read_response(file_data, offset, limit)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        overlay = self._overlay()
        raw = _glob_search_files(overlay, pattern, path)
        if raw == "No files found":
            return []
        results: list[FileInfo] = []
        for matched in raw.split("\n"):
            file_data = overlay.get(matched)
            if file_data is None:
                continue
            content = file_data.get("content", [])
            results.append(
                FileInfo(
                    path=matched,
                    is_dir=False,
                    size=len("\n".join(content)),
                    modified_at=file_data.get("modified_at", ""),
                )
            )
        return results

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        overlay = self._overlay()
        return cast(
            "list[GrepMatch] | str",
            grep_matches_from_files(
                overlay, pattern, path if path is not None else "/", glob
            ),
        )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        overlay = self._overlay()
        responses: list[FileDownloadResponse] = []
        for path in paths:
            file_data = overlay.get(path)
            if file_data is None:
                responses.append(
                    FileDownloadResponse(
                        path=path, content=None, error="file_not_found"
                    )
                )
                continue
            responses.append(
                FileDownloadResponse(
                    path=path,
                    content=file_data_to_string(file_data).encode("utf-8"),
                    error=None,
                )
            )
        return responses

    # ------------------------------------------------------------------
    # Write surface (uploads are owned by the UI layer)
    # ------------------------------------------------------------------

    def write(self, file_path: str, content: str) -> WriteResult:  # noqa: ARG002
        return WriteResult(error=_READONLY_ERROR)

    def edit(
        self,
        file_path: str,  # noqa: ARG002
        old_string: str,  # noqa: ARG002
        new_string: str,  # noqa: ARG002
        replace_all: bool = False,  # noqa: ARG002, FBT001, FBT002
    ) -> EditResult:
        return EditResult(error=_READONLY_ERROR)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # The adapter participates in the upload contract for symmetry
        # with other backends, but the UI owns the actual write path.
        return [
            FileUploadResponse(path=path, error="permission_denied")
            for path, _ in files
        ]


__all__ = [
    "ROUTE_PREFIX",
    "UI_STATE_PREFIX",
    "UploadsStateBackend",
]
