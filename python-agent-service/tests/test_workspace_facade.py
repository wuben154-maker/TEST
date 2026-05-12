"""WorkspaceFacadeBackend — virtual /workspace/ ↔ scoped owner subtree.

Two flavors of test exist:

1. Contract tests against ``WorkspaceFacadeBackend`` alone, using
   *route-local* suffixes as input (mirroring what ``CompositeBackend``
   dispatches in production) and asserting route-local outputs.

2. Integration tests against ``CompositeBackend(/workspace/ → facade)``
   which exercise the real LLM-facing link (paths like
   ``/workspace/a.txt`` in, ``/workspace/a.txt`` out).

Both layers must agree, otherwise ``read_file`` silently fails for files
uploaded under an owner root — which is exactly the bug this module
originally shipped with.
"""

from __future__ import annotations

from pathlib import Path

from app._vendor.deepagents.backends.composite import CompositeBackend
from app._vendor.deepagents.backends.filesystem import FilesystemBackend
from app._vendor.deepagents.backends.state import StateBackend
from app.backends.workspace_facade import WorkspaceFacadeBackend
from app.backends.workspace_scope import (
    WorkspaceScopedFilesystemBackend,
    reset_workspace_scope_root,
    set_workspace_scope_root,
)


def _build(tmp_path: Path, owner: str) -> tuple[WorkspaceFacadeBackend, object]:
    """Build facade + bind ``owner`` as the current workspace scope root.

    Seeds a single ``a.txt`` file under the scoped root so the facade has
    something to list/read. ``owner`` uses the same shape
    (``u_alice/p_proj1`` etc.) the real ``owner_segment`` helper produces.
    """
    (tmp_path / owner).mkdir(parents=True)
    (tmp_path / owner / "a.txt").write_text("hello")
    inner = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    scoped = WorkspaceScopedFilesystemBackend(inner)
    facade = WorkspaceFacadeBackend(scoped)
    tok = set_workspace_scope_root(f"/{owner}")
    return facade, tok


def _build_composite(
    tmp_path: Path, owner: str
) -> tuple[CompositeBackend, object]:
    """Build the real CompositeBackend(/workspace/ → facade) link.

    This reproduces the shape produced by ``create_layered_backend`` so the
    tests cover the "path as the LLM sees it" contract rather than just the
    facade in isolation.
    """
    (tmp_path / owner).mkdir(parents=True)
    (tmp_path / owner / "a.txt").write_text("hello")
    inner = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    scoped = WorkspaceScopedFilesystemBackend(inner)
    facade = WorkspaceFacadeBackend(scoped)

    class _EmptyState:
        """Tiny stand-in for StateBackend that just errors on everything.

        The tests only need ``/workspace/`` routes; any hit on the default
        backend would be a bug we want to surface.
        """

    composite = CompositeBackend(
        default=StateBackend(),
        routes={"/workspace/": facade},
    )
    tok = set_workspace_scope_root(f"/{owner}")
    return composite, tok


# ---------------------------------------------------------------------------
# Contract tests — facade called directly with route-local suffixes.
# ---------------------------------------------------------------------------


class TestFacadeContractLs:
    def test_ls_root_maps_to_owner(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            res = facade.ls("/")
            assert res.error is None
            paths = [e.get("path", "") for e in (res.entries or [])]
            # Route-local: no /workspace and no owner segment.
            assert any(p == "/a.txt" for p in paths), paths
            assert not any("u_alice" in p for p in paths), paths
            assert not any(p.startswith("/workspace") for p in paths), paths
        finally:
            reset_workspace_scope_root(tok)

    def test_ls_legacy_full_path_still_works(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            res = facade.ls("/workspace/")
            assert res.error is None
            paths = [e.get("path", "") for e in (res.entries or [])]
            assert any(p == "/a.txt" for p in paths), paths
        finally:
            reset_workspace_scope_root(tok)

    def test_ls_outside_workspace_errors(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "s_x")
        try:
            res = facade.ls("/memories/")
            assert res.error is not None
            assert "workspace" in res.error.lower()
        finally:
            reset_workspace_scope_root(tok)


class TestFacadeContractRead:
    def test_read_route_local(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            out = facade.read("/a.txt")
            # Read may return ReadResult or plain str depending on inner backend.
            if hasattr(out, "file_data") and out.file_data:
                assert "hello" in out.file_data["content"]
            else:
                assert "hello" in str(out)
        finally:
            reset_workspace_scope_root(tok)

    def test_read_legacy_full_path(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            out = facade.read("/workspace/a.txt")
            text = out.file_data["content"] if hasattr(out, "file_data") and out.file_data else str(out)
            assert "hello" in text
        finally:
            reset_workspace_scope_root(tok)

    def test_read_outside_workspace_errors(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            out = facade.read("/etc/passwd")
            assert "workspace" in str(out).lower()
        finally:
            reset_workspace_scope_root(tok)


class TestFacadeContractWriteEdit:
    def test_write_route_local(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            wr = facade.write("/new.txt", "data")
            assert wr.error is None
            # Facade preserves the /workspace/ form so direct callers still
            # get a stable identifier; CompositeBackend overwrites this with
            # the caller-supplied path in the real link.
            assert wr.path == "/workspace/new.txt"
            ls = facade.ls("/")
            paths = [e.get("path", "") for e in (ls.entries or [])]
            assert any("new.txt" in p for p in paths)
        finally:
            reset_workspace_scope_root(tok)

    def test_write_outside_workspace_denied(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            wr = facade.write("/etc/evil.txt", "nope")
            assert wr.error is not None and "workspace" in wr.error.lower()
        finally:
            reset_workspace_scope_root(tok)


class TestFacadeContractGlobGrep:
    def test_glob_returns_route_local(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            res = facade.glob("*.txt", path="/")
            assert res.error is None
            paths = [m.get("path", "") for m in (res.matches or [])]
            assert not any("u_alice" in p for p in paths)
            assert not any(p.startswith("/workspace") for p in paths)
        finally:
            reset_workspace_scope_root(tok)

    def test_glob_outside_workspace_errors(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "s_x")
        try:
            res = facade.glob("*.txt", path="/etc/")
            assert res.error is not None and "workspace" in res.error.lower()
        finally:
            reset_workspace_scope_root(tok)

    def test_grep_rewrites_matches(self, tmp_path: Path):
        facade, tok = _build(tmp_path, "u_alice/p_proj1")
        try:
            res = facade.grep("hello", path="/", glob="*.txt")
            paths = [m.get("path", "") for m in (res.matches or [])]
            assert not any("u_alice" in p for p in paths)
            assert not any(p.startswith("/workspace") for p in paths)
        finally:
            reset_workspace_scope_root(tok)


# ---------------------------------------------------------------------------
# Integration tests — CompositeBackend + facade, exercising the real LLM path.
# This is the link that was previously broken (CompositeBackend stripped
# ``/workspace/`` but the facade required it).
# ---------------------------------------------------------------------------


class TestCompositeIntegration:
    def test_read_through_composite(self, tmp_path: Path):
        composite, tok = _build_composite(tmp_path, "u_alice/p_proj1")
        try:
            out = composite.read("/workspace/a.txt")
            text = out.file_data["content"] if hasattr(out, "file_data") and out.file_data else str(out)
            assert "hello" in text
            # Regression: the pre-fix facade returned this error for every
            # read through the composite link.
            assert "path must be under /workspace/" not in text
        finally:
            reset_workspace_scope_root(tok)

    def test_ls_through_composite_adds_prefix_back(self, tmp_path: Path):
        composite, tok = _build_composite(tmp_path, "u_alice/p_proj1")
        try:
            res = composite.ls("/workspace/")
            assert res.error is None
            paths = [e.get("path", "") for e in (res.entries or [])]
            # CompositeBackend re-prefixes with /workspace, so the tool caller
            # sees the full virtual path — never the owner segment.
            assert any(p == "/workspace/a.txt" for p in paths), paths
            assert not any("u_alice" in p for p in paths), paths
        finally:
            reset_workspace_scope_root(tok)

    def test_write_through_composite(self, tmp_path: Path):
        composite, tok = _build_composite(tmp_path, "u_alice/p_proj1")
        try:
            wr = composite.write("/workspace/new.txt", "data")
            assert wr.error is None
            assert wr.path == "/workspace/new.txt"
            # File actually landed on disk under the owner root.
            assert (tmp_path / "u_alice" / "p_proj1" / "new.txt").read_text() == "data"
        finally:
            reset_workspace_scope_root(tok)


class TestCrossOwnerIsolation:
    def test_owner_a_cannot_see_owner_b_files(self, tmp_path: Path):
        (tmp_path / "u_a" / "default").mkdir(parents=True)
        (tmp_path / "u_a" / "default" / "a.txt").write_text("A")
        (tmp_path / "u_b" / "default").mkdir(parents=True)
        (tmp_path / "u_b" / "default" / "b.txt").write_text("B")

        inner = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
        scoped = WorkspaceScopedFilesystemBackend(inner)
        facade = WorkspaceFacadeBackend(scoped)

        tok = set_workspace_scope_root("/u_a/default")
        try:
            res = facade.ls("/")
            paths = [e.get("path", "") for e in (res.entries or [])]
            assert any("a.txt" in p for p in paths), paths
            assert not any("b.txt" in p for p in paths), paths
        finally:
            reset_workspace_scope_root(tok)
