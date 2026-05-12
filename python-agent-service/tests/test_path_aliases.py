"""Tests for ``app.backends.path_aliases``.

Validates the path-canonicalization helper and the ``PathAliasBackend``
wrapper. The helper must be idempotent and must never touch paths outside
``/workspace/``.
"""

from __future__ import annotations

from typing import Any

import pytest

from app._vendor.deepagents.backends.protocol import (
    EditResult,
    LsResult,
    WriteResult,
)
from app.backends.path_aliases import PathAliasBackend, canonicalize_agent_path


class _Recorder:
    """Minimal BackendProtocol stub that records the paths it received."""

    def __init__(self) -> None:
        self.ls_paths: list[str] = []
        self.read_paths: list[str] = []
        self.write_paths: list[str] = []
        self.edit_paths: list[str] = []
        self.glob_paths: list[str] = []
        self.grep_paths: list[str | None] = []

    def ls(self, path: str) -> LsResult:
        self.ls_paths.append(path)
        return LsResult(entries=[])

    async def als(self, path: str) -> LsResult:  # pragma: no cover - not used here
        self.ls_paths.append(path)
        return LsResult(entries=[])

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        self.read_paths.append(file_path)
        return "ok"

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        self.read_paths.append(file_path)
        return "ok"

    def write(self, file_path: str, content: str) -> WriteResult:
        self.write_paths.append(file_path)
        return WriteResult(path=file_path)

    async def awrite(self, file_path: str, content: str) -> WriteResult:  # pragma: no cover
        self.write_paths.append(file_path)
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        self.edit_paths.append(file_path)
        return EditResult(path=file_path, occurrences=1)

    async def aedit(self, *args: Any, **kwargs: Any) -> EditResult:  # pragma: no cover
        self.edit_paths.append(args[0])
        return EditResult(path=args[0], occurrences=1)

    def glob(self, pattern: str, path: str = "/"):
        from app._vendor.deepagents.backends.protocol import GlobResult

        self.glob_paths.append(path)
        return GlobResult(matches=[])

    async def aglob(self, pattern: str, path: str = "/"):  # pragma: no cover
        from app._vendor.deepagents.backends.protocol import GlobResult

        self.glob_paths.append(path)
        return GlobResult(matches=[])

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None):
        from app._vendor.deepagents.backends.protocol import GrepResult

        self.grep_paths.append(path)
        return GrepResult(matches=[])

    async def agrep(self, *args: Any, **kwargs: Any):  # pragma: no cover
        from app._vendor.deepagents.backends.protocol import GrepResult

        self.grep_paths.append(kwargs.get("path"))
        return GrepResult(matches=[])

    def execute(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError

    async def aexecute(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError

    def upload_files(self, files):  # pragma: no cover - trivial
        return []

    async def aupload_files(self, files):  # pragma: no cover
        return []

    def download_files(self, paths):  # pragma: no cover
        return []

    async def adownload_files(self, paths):  # pragma: no cover
        return []


class TestCanonicalize:
    def test_empty_returns_as_is(self) -> None:
        assert canonicalize_agent_path("") == ""
        assert canonicalize_agent_path(None) is None  # type: ignore[arg-type]

    def test_folds_pascal_workspace(self) -> None:
        assert canonicalize_agent_path("/Workspace/foo.txt") == "/workspace/foo.txt"
        assert canonicalize_agent_path("Workspace/foo.txt") == "/workspace/foo.txt"
        assert canonicalize_agent_path("workspace/foo") == "/workspace/foo"

    def test_folds_bare_workspace_token(self) -> None:
        assert canonicalize_agent_path("/Workspace") == "/workspace"
        assert canonicalize_agent_path("Workspace") == "/workspace"

    def test_strips_owner_segment_user_project(self) -> None:
        assert (
            canonicalize_agent_path("/workspace/u_abc-123/p_xyz/a/b.txt")
            == "/workspace/a/b.txt"
        )

    def test_strips_owner_segment_user_default(self) -> None:
        assert (
            canonicalize_agent_path(
                "/workspace/u_fae4a472-7766-44ed-bdbf-315f8cf59076/default/ghost.php"
            )
            == "/workspace/ghost.php"
        )

    def test_strips_owner_segment_session(self) -> None:
        assert (
            canonicalize_agent_path("/workspace/s_sess123/nested/file.txt")
            == "/workspace/nested/file.txt"
        )

    def test_combined_case_and_owner(self) -> None:
        assert (
            canonicalize_agent_path(
                "Workspace/u_fae4a472-7766-44ed-bdbf-315f8cf59076/default/ghost.php"
            )
            == "/workspace/ghost.php"
        )

    def test_idempotent(self) -> None:
        once = canonicalize_agent_path("/workspace/u_abc/default/a/b")
        twice = canonicalize_agent_path(once)
        assert once == twice == "/workspace/a/b"

    def test_leaves_non_workspace_paths_untouched(self) -> None:
        for p in (
            "/skills/web_security/SKILL.md",
            "/memories/note.txt",
            "/uploads/u_abc/x",
            "/tmp/foo.txt",
            "relative/path.txt",
        ):
            assert canonicalize_agent_path(p) == p

    def test_backslash_normalized(self) -> None:
        assert (
            canonicalize_agent_path(r"\workspace\foo\bar.txt")
            == "/workspace/foo/bar.txt"
        )


class TestPathAliasBackendDelegation:
    def test_read_rewrites_before_delegate(self) -> None:
        rec = _Recorder()
        backend = PathAliasBackend(rec)
        backend.read("/Workspace/u_abc/default/file.php")
        assert rec.read_paths == ["/workspace/file.php"]

    def test_write_rewrites_before_delegate(self) -> None:
        rec = _Recorder()
        PathAliasBackend(rec).write("/workspace/u_abc/p_xyz/a.txt", "hi")
        assert rec.write_paths == ["/workspace/a.txt"]

    def test_ls_rewrites_before_delegate(self) -> None:
        rec = _Recorder()
        PathAliasBackend(rec).ls("/Workspace")
        assert rec.ls_paths == ["/workspace"]

    def test_edit_rewrites_before_delegate(self) -> None:
        rec = _Recorder()
        PathAliasBackend(rec).edit(
            "/workspace/s_sid/report.md", "old", "new"
        )
        assert rec.edit_paths == ["/workspace/report.md"]

    def test_glob_rewrites_before_delegate(self) -> None:
        rec = _Recorder()
        PathAliasBackend(rec).glob("*.php", path="/Workspace")
        assert rec.glob_paths == ["/workspace"]

    def test_grep_handles_none_path(self) -> None:
        rec = _Recorder()
        PathAliasBackend(rec).grep("needle", path=None)
        assert rec.grep_paths == [None]

    @pytest.mark.asyncio
    async def test_aread_rewrites(self) -> None:
        rec = _Recorder()
        await PathAliasBackend(rec).aread(
            "/workspace/u_fae4a472-7766-44ed-bdbf-315f8cf59076/default/ghost.php"
        )
        assert rec.read_paths == ["/workspace/ghost.php"]
