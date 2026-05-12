"""Shared backend constants (virtual path prefixes, owner scope keys)."""

from __future__ import annotations

# Virtual root presented to the LLM for the user-writable area. All user uploads,
# agent-produced artifacts, and main/subagent workspace reads/writes live under this
# prefix. Maps to an owner-scoped subtree of settings.upload_dir on disk.
WORKSPACE_VIRTUAL_ROOT: str = "/workspace/"

# Default owner segment used for anonymous sessions that never resolved a user id.
ANON_OWNER_PREFIX: str = "s_"
USER_OWNER_PREFIX: str = "u_"
PROJECT_OWNER_PREFIX: str = "p_"
DEFAULT_PROJECT_SEGMENT: str = "default"

__all__ = [
    "WORKSPACE_VIRTUAL_ROOT",
    "ANON_OWNER_PREFIX",
    "USER_OWNER_PREFIX",
    "PROJECT_OWNER_PREFIX",
    "DEFAULT_PROJECT_SEGMENT",
]
