"""Session registry for sandbox handles (ADR-16 crash-recovery hook).

This module maintains a process-wide ``_SESSION_REGISTRY`` mapping
``analysis_id`` → :class:`~sandbox.client.SandboxSession`.

Two reasons this exists:

1. **Crash recovery** — if the Agent dies mid-analysis the registry lets a
   supervisor enumerate outstanding sandboxes and force-kill them, preventing
   "zombie" sandboxes from continuing to incur cost (ADR-16 §2).

2. **Session reuse inside a single analysis** — the per-analysis lifecycle
   (ADR-16 decision B) means all Tool calls share one sandbox; the registry
   lets Tools look it up by ``analysis_id`` instead of passing the handle
   through every call chain.

All public helpers are async and serialise mutations via an
``asyncio.Lock`` so concurrent ``create`` calls from different analyses do
not race.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sandbox.client import SandboxSession

if TYPE_CHECKING:  # pragma: no cover
    from sandbox.client import SandboxClient

_SESSION_REGISTRY: dict[str, SandboxSession] = {}
_registry_lock = asyncio.Lock()
_creation_locks: dict[str, asyncio.Lock] = {}
_creation_locks_guard = asyncio.Lock()


async def register_session(session: SandboxSession) -> None:
    """Register ``session`` under its ``analysis_id``.

    Args:
        session: Freshly created sandbox session to track.

    Raises:
        RuntimeError: If a session for the same ``analysis_id`` is already
            registered.  The caller should kill the stale session first.
    """
    async with _registry_lock:
        if session.analysis_id in _SESSION_REGISTRY:
            msg = (
                f"Sandbox session for analysis_id={session.analysis_id!r} "
                "is already registered; kill the existing session before "
                "creating a new one."
            )
            raise RuntimeError(msg)
        _SESSION_REGISTRY[session.analysis_id] = session


async def unregister_session(analysis_id: str) -> SandboxSession | None:
    """Remove and return the session bound to ``analysis_id``.

    Args:
        analysis_id: UUID string of the analysis whose session to evict.

    Returns:
        The evicted :class:`SandboxSession`, or ``None`` if no session was
        registered under that id.
    """
    async with _registry_lock:
        return _SESSION_REGISTRY.pop(analysis_id, None)


async def get_session(analysis_id: str) -> SandboxSession | None:
    """Return the session bound to ``analysis_id``, or ``None`` if absent."""
    async with _registry_lock:
        return _SESSION_REGISTRY.get(analysis_id)


async def get_or_create_session(
    client: SandboxClient, analysis_id: str
) -> SandboxSession:
    """Atomically return the session for ``analysis_id``, creating one if absent.

    Guards against the check-then-create race that arises when an LLM
    emits parallel tool calls (FB-F-02): both ``FileIdentifyTool._ensure_session``
    and ``SandboxSessionTool`` action ``create`` would observe an empty
    registry, each spin up a fresh remote sandbox, and the second
    :func:`register_session` call would raise :class:`RuntimeError` while
    leaking an orphan sandbox to the backend (paid cost on E2B).

    A per-``analysis_id`` :class:`asyncio.Lock` is held for the whole
    check-or-create window so at most one backend ``create`` call is in
    flight for a given analysis.  Locks for different analysis ids stay
    independent, preserving parallel creation across analyses.

    Args:
        client: Concrete :class:`SandboxClient` backend instance (either
            :class:`SubprocessBackend` or :class:`E2BBackend`).
        analysis_id: Identifier of the analysis session (ULID).

    Returns:
        The :class:`SandboxSession` bound to ``analysis_id``.  Identical
        across concurrent callers for the same ``analysis_id``.
    """
    async with _creation_locks_guard:
        creation_lock = _creation_locks.setdefault(analysis_id, asyncio.Lock())
    async with creation_lock:
        existing = await get_session(analysis_id)
        if existing is not None:
            return existing
        return await client.create(analysis_id)


async def all_analysis_ids() -> list[str]:
    """Return a snapshot list of all currently registered ``analysis_id`` values.

    Useful for crash-recovery supervisors that need to enumerate outstanding
    sandboxes before shutting the process down.
    """
    async with _registry_lock:
        return list(_SESSION_REGISTRY.keys())
