"""Sandbox backend factory shared by CLI, LangGraph UI, and subagent registry.

Uses :func:`config.settings` to choose subprocess vs E2B unless ``use_e2b`` is
passed explicitly by the caller (runner flag).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import settings

if TYPE_CHECKING:
    from sandbox.client import SandboxClient


def build_binary_sandbox_client(*, use_e2b: bool | None = None) -> SandboxClient:
    """Return a concrete :class:`~sandbox.client.SandboxClient` backend.

    Args:
        use_e2b: When ``None``, read ``settings().use_e2b``. When ``True``
            return :class:`~sandbox.e2b_backend.E2BBackend` (credentials are
            validated by :meth:`config.settings`).
        When ``False``, always return :class:`~sandbox.subprocess_backend.SubprocessBackend`.

    Returns:
        E2B or subprocess backend implementing :class:`~sandbox.client.SandboxClient`.
    """
    resolved = settings().use_e2b if use_e2b is None else use_e2b
    if resolved:
        from sandbox.e2b_backend import E2BBackend  # noqa: PLC0415

        return E2BBackend()

    from sandbox.subprocess_backend import SubprocessBackend  # noqa: PLC0415

    return SubprocessBackend()


__all__ = ["build_binary_sandbox_client"]
