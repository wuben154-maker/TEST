"""ScopedUploadFilesystemBackend restricts ls/read to contextvar root."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app._vendor.deepagents.backends.filesystem import FilesystemBackend
from app.backends.upload_scope import (
    ScopedUploadFilesystemBackend,
    reset_upload_stripped_root,
    set_upload_stripped_root,
)


def test_scoped_ls_root_hides_sibling(tmp_path: Path):
    (tmp_path / "s_a").mkdir()
    (tmp_path / "s_b").mkdir()
    (tmp_path / "s_a" / "1.txt").write_text("a")
    (tmp_path / "s_b" / "2.txt").write_text("b")

    inner = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    scoped = ScopedUploadFilesystemBackend(inner)
    tok = set_upload_stripped_root("/s_a")

    try:
        infos = scoped.ls_info("/")
        paths = {i["path"] for i in infos}
        assert any("1.txt" in p for p in paths)
        assert not any("s_b" in p for p in paths)
    finally:
        reset_upload_stripped_root(tok)


def test_scoped_read_denied_outside(tmp_path: Path):
    (tmp_path / "s_a").mkdir()
    (tmp_path / "s_b").mkdir()
    (tmp_path / "s_b" / "secret.txt").write_text("no")

    inner = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    scoped = ScopedUploadFilesystemBackend(inner)
    tok = set_upload_stripped_root("/s_a")
    try:
        out = scoped.read("/s_b/secret.txt")
        # New contract: WorkspaceScopedFilesystemBackend surfaces the explicit
        # "path outside your workspace" error so the LLM learns the boundary.
        assert "outside your workspace" in out.lower() or "not in" in out.lower()
    finally:
        reset_upload_stripped_root(tok)


def test_layered_backend_binds_scoped_upload_backend(tmp_path: Path):
    """Main graph and subagents share create_layered_backend; /uploads/ must be scoped."""
    from app.backends.composite import create_layered_backend

    upload_root = tmp_path / "up"
    upload_root.mkdir()
    with patch(
        "app.config.get_settings",
        return_value=SimpleNamespace(upload_dir=str(upload_root)),
    ):
        factory = create_layered_backend()
        backend = factory(MagicMock())
    # Factory now wraps CompositeBackend with PathAliasBackend for UX robustness;
    # unwrap for the route-level assertion.
    composite = getattr(backend, "_inner", backend)
    uploads_backend = composite.routes.get("/uploads/")
    assert isinstance(uploads_backend, ScopedUploadFilesystemBackend)
