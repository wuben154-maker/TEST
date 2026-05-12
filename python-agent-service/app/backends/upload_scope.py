"""Deprecated compatibility shim.

The previous ``ScopedUploadFilesystemBackend`` + ``upload_stripped_root``
ContextVar are now unified under ``workspace_scope`` to match the user-visible
``/workspace/`` virtual namespace. This module re-exports the new symbols
under the old names so any lingering importers keep working through the
transition; new code should import from ``app.backends.workspace_scope``.
"""

from __future__ import annotations

from app.backends.workspace_scope import (
    OUTSIDE_SCOPE_ERROR,
    WorkspaceScopedFilesystemBackend as ScopedUploadFilesystemBackend,
    get_workspace_scope_root as get_upload_stripped_root,
    reset_workspace_scope_root as reset_upload_stripped_root,
    set_workspace_scope_root as set_upload_stripped_root,
    workspace_scope as upload_scope,
)

__all__ = [
    "OUTSIDE_SCOPE_ERROR",
    "ScopedUploadFilesystemBackend",
    "get_upload_stripped_root",
    "reset_upload_stripped_root",
    "set_upload_stripped_root",
    "upload_scope",
]
