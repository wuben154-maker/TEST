"""Unit tests for DatabaseBackend.

Uses InMemoryStore to avoid external DB dependencies.
Tests ls_info, read, write, edit, glob_info, grep_raw.
"""

import pytest

from app.backends.database_backend import DatabaseBackend
from app.backends.store import InMemoryStore


@pytest.fixture
def store():
    """In-memory store for testing."""
    return InMemoryStore()


@pytest.fixture
def backend(store):
    """DatabaseBackend with InMemoryStore."""
    return DatabaseBackend(namespace="memories", store=store)


class TestDatabaseBackendWriteRead:
    """Tests for write and read operations."""

    def test_write_and_read(self, backend):
        """Write content and read it back."""
        result = backend.write("/test.txt", "hello world")
        assert result.error is None
        assert result.path == "/test.txt"

        content = backend.read("/test.txt")
        assert "hello world" in content
        assert "[Lines 1-1 of 1]" in content

    def test_read_nonexistent(self, backend):
        """Read non-existent file returns error message."""
        content = backend.read("/nonexistent.txt")
        assert "Error: File not found" in content

    def test_write_empty(self, backend):
        """Write empty content."""
        result = backend.write("/empty.txt", "")
        assert result.error is None
        content = backend.read("/empty.txt")
        assert "File exists but is empty" in content

    def test_read_with_offset_limit(self, backend):
        """Read with pagination."""
        lines = ["line1", "line2", "line3", "line4", "line5"]
        backend.write("/multi.txt", "\n".join(lines))

        content = backend.read("/multi.txt", offset=1, limit=2)
        assert "[Lines 2-3 of 5]" in content
        assert "line2" in content
        assert "line3" in content


class TestDatabaseBackendLsInfo:
    """Tests for ls_info (directory listing)."""

    def test_ls_info_empty(self, backend):
        """List empty directory."""
        infos = backend.ls_info("/")
        assert infos == []

    def test_ls_info_with_files(self, backend):
        """List directory with files."""
        backend.write("/file1.txt", "a")
        backend.write("/file2.txt", "b")

        infos = backend.ls_info("/")
        assert len(infos) == 2
        paths = [p.get("path", "") for p in infos]
        assert "/file1.txt" in paths
        assert "/file2.txt" in paths

    def test_ls_info_subdir(self, backend):
        """List with subdirectory structure."""
        backend.write("/subdir/file.txt", "content")

        infos = backend.ls_info("/")
        assert len(infos) >= 1
        dirs = [p for p in infos if p.get("is_dir", False)]
        files = [p for p in infos if not p.get("is_dir", False)]
        assert any("/subdir/" in p.get("path", "") for p in dirs) or any("/subdir/file.txt" in p.get("path", "") for p in files)


class TestDatabaseBackendEdit:
    """Tests for edit operation."""

    def test_edit_single(self, backend):
        """Edit single occurrence."""
        backend.write("/edit.txt", "foo bar baz")
        result = backend.edit("/edit.txt", "bar", "qux")

        assert result.error is None
        assert result.occurrences == 1
        content = backend.read("/edit.txt")
        assert "foo qux baz" in content

    def test_edit_replace_all(self, backend):
        """Edit replace all occurrences."""
        backend.write("/edit.txt", "foo foo foo")
        result = backend.edit("/edit.txt", "foo", "bar", replace_all=True)

        assert result.error is None
        assert result.occurrences == 3
        content = backend.read("/edit.txt")
        assert "bar bar bar" in content

    def test_edit_nonexistent(self, backend):
        """Edit non-existent file."""
        result = backend.edit("/nonexistent.txt", "old", "new")
        assert result.error is not None
        assert "File not found" in result.error

    def test_edit_pattern_not_found(self, backend):
        """Edit when pattern not in file."""
        backend.write("/edit.txt", "hello")
        result = backend.edit("/edit.txt", "xyz", "abc")
        assert result.error is not None
        assert "Pattern not found" in result.error


class TestDatabaseBackendGlobInfo:
    """Tests for glob_info."""

    def test_glob_info(self, backend):
        """Glob pattern matching."""
        backend.write("/a.txt", "x")
        backend.write("/b.txt", "x")
        backend.write("/c.log", "x")

        infos = backend.glob_info("*.txt", "/")
        assert len(infos) >= 2
        paths = [p.get("path", "") for p in infos]
        assert "/a.txt" in paths
        assert "/b.txt" in paths


class TestDatabaseBackendGrepRaw:
    """Tests for grep_raw."""

    def test_grep_raw(self, backend):
        """Grep pattern in files."""
        backend.write("/file1.txt", "hello world\nfoo bar\n")
        backend.write("/file2.txt", "baz hello qux\n")

        matches = backend.grep_raw("hello")
        assert len(matches) >= 2
        paths = [m.get("path", "") for m in matches]
        assert "/file1.txt" in paths
        assert "/file2.txt" in paths

    def test_grep_raw_line_content(self, backend):
        """Grep returns correct line content."""
        backend.write("/grep.txt", "line1\nmatch here\nline3")
        matches = backend.grep_raw("match here")

        assert len(matches) == 1
        assert matches[0]["line"] == 2
        assert "match here" in matches[0]["text"]


class TestDatabaseBackendPathValidation:
    """Tests for path validation."""

    def test_path_traversal_rejected(self, backend):
        """Path traversal is rejected."""
        with pytest.raises(ValueError, match="Path traversal"):
            backend.read("/../etc/passwd")

    def test_path_normalized(self, backend):
        """Path without leading slash is normalized."""
        backend.write("relative.txt", "content")
        content = backend.read("/relative.txt")
        assert "content" in content


class TestDatabaseBackendUploadDownload:
    """Tests for upload_files and download_files."""

    def test_upload_files(self, backend):
        """Upload binary files."""
        files = [("/uploaded.txt", b"binary content")]
        results = backend.upload_files(files)

        assert len(results) == 1
        assert results[0].path == "/uploaded.txt"
        assert results[0].error is None

        content = backend.read("/uploaded.txt")
        assert "binary content" in content

    def test_download_files(self, backend):
        """Download files."""
        backend.write("/download.txt", "content")
        results = backend.download_files(["/download.txt"])

        assert len(results) == 1
        assert results[0].path == "/download.txt"
        assert results[0].error is None
        assert results[0].content == b"content"

    def test_download_nonexistent(self, backend):
        """Download non-existent file."""
        results = backend.download_files(["/missing.txt"])
        assert results[0].error == "file_not_found"
