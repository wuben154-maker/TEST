"""Cross-owner isolation test for ``/memories/`` and ``/parameters/``.

Before the owner-scoped wrapper, both owners writing to ``/memories/foo``
would collide in a shared namespace. After the wrapper the namespace is
``memories/<owner_key>`` and writes are invisible across owners.
"""

from __future__ import annotations

from app.backends.owner_scoped_store import (
    OwnerScopedStoreBackend,
    _owner_key,
)
from app.backends.workspace_scope import (
    reset_workspace_scope_root,
    set_workspace_scope_root,
)


def test_owner_key_fallback_without_scope():
    # No ContextVar set yet -> stable "_unscoped" key.
    assert _owner_key() == "_unscoped"


def test_owner_key_strips_and_flattens():
    tok = set_workspace_scope_root("/u_alice/p_proj1")
    try:
        assert _owner_key() == "u_alice__p_proj1"
    finally:
        reset_workspace_scope_root(tok)


def test_cross_owner_memories_isolated():
    backend = OwnerScopedStoreBackend(base_namespace="memories")

    # alice writes
    tok_a = set_workspace_scope_root("/u_alice/p_proj1")
    try:
        res = backend.write("/alpha.md", "alice-secret")
        assert res.error is None, res.error
    finally:
        reset_workspace_scope_root(tok_a)

    # bob reads same path -> must miss (not leak alice's content)
    tok_b = set_workspace_scope_root("/u_bob/p_proj1")
    try:
        res = backend.read("/alpha.md")
        # StoreBackend.read returns a legacy str (either "Error: File not
        # found: ..." or formatted content). Either way, alice's secret
        # must not appear in bob's view.
        text = res if isinstance(res, str) else str(getattr(res, "file_data", ""))
        assert "alice-secret" not in text
    finally:
        reset_workspace_scope_root(tok_b)

    # alice can still read her own
    tok_a2 = set_workspace_scope_root("/u_alice/p_proj1")
    try:
        res = backend.read("/alpha.md")
        text = res if isinstance(res, str) else str(getattr(res, "file_data", ""))
        assert "alice-secret" in text
    finally:
        reset_workspace_scope_root(tok_a2)


def test_same_user_different_projects_isolated():
    backend = OwnerScopedStoreBackend(base_namespace="parameters")

    tok_p1 = set_workspace_scope_root("/u_alice/p_proj1")
    try:
        backend.write("/k.txt", "value-p1")
    finally:
        reset_workspace_scope_root(tok_p1)

    tok_p2 = set_workspace_scope_root("/u_alice/p_proj2")
    try:
        res = backend.read("/k.txt")
        text = res if isinstance(res, str) else str(getattr(res, "file_data", ""))
        assert "value-p1" not in text
    finally:
        reset_workspace_scope_root(tok_p2)
