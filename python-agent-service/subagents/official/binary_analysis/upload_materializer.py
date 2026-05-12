"""Middleware that materialises deep-agents-ui uploads to host disk.

Context:

* ``UIUploadBackend`` (see :mod:`ui_backend`) makes
  ``state.files['uploaded/*']`` visible to the agent's built-in ``ls`` /
  ``read_file`` / ``glob`` tools.
* ``FileIdentifyTool`` (FR-01), and by extension every downstream
  sandbox step, opens the sample via :func:`Path.stat` /
  :meth:`Path.open` and therefore needs a real host path — a virtual
  ``/uploaded/calc.exe`` key cannot be read from the filesystem.

This middleware bridges the two worlds. On every invocation it scans
``state.files`` for ``uploaded/*`` entries, decodes the base64 payload
that deep-agents-ui writes, and drops the bytes under a per-thread host
directory (``<host_upload_root>/<thread_id>/<filename>``). It then
appends a single :class:`SystemMessage` listing the virtual->host
mapping so the LLM knows which string to pass to ``file_identify``.

The middleware is idempotent: already-materialised uploads are tracked
by key so we do not keep rewriting the same bytes on every step, and a
re-upload with the same key simply refreshes the host copy.

Scope:

* Active only on the LangGraph dev entrypoint (see
  :mod:`langgraph_entry`); the production CLI path
  never hands UI uploads to the agent.
* Does **not** execute the sample — it only writes bytes so tooling
  later in the chain can read them. Execution remains gated by
  :class:`SandboxClient`, preserving ADR-05 "zero execution on host".
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import SystemMessage

if TYPE_CHECKING:  # pragma: no cover
    from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

UPLOADED_PREFIX = "/uploaded/"

# Conservative allow-list: keep filenames simple to avoid Windows reserved
# characters and path injection via state keys.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._\- ]{1,255}$")


def _decode_payload(value: Any) -> bytes | None:
    """Extract raw bytes from a ``state.files`` entry if possible.

    deep-agents-ui stores binary uploads as a single base64 string; some
    other writers may wrap the same payload in a ``FileData`` dict with a
    single-line ``content`` list. Both shapes decode back to the same
    bytes; anything else is rejected so we never persist untrusted junk
    to disk.
    """
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return base64.b64decode(stripped, validate=True)
        except (ValueError, base64.binascii.Error):
            return None
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list) and len(content) == 1:
            try:
                return base64.b64decode(str(content[0]).strip(), validate=True)
            except (ValueError, base64.binascii.Error):
                return None
    return None


class UploadMaterializerMiddleware(AgentMiddleware):
    """Write ``state.files['uploaded/*']`` to host disk and tell the agent.

    Args:
        host_upload_root: Directory that will host the materialised
            uploads. Created on init if missing; a sub-directory is
            created per LangGraph ``thread_id`` observed at runtime so
            concurrent sessions cannot collide.
        thread_id_fallback: Directory name used when the runtime does
            not expose a ``thread_id`` (typically only during tests).
    """

    def __init__(
        self,
        *,
        host_upload_root: Path,
        thread_id_fallback: str = "anonymous",
    ) -> None:
        super().__init__()
        self._root = Path(host_upload_root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._fallback = thread_id_fallback
        # Track which virtual keys were already materialised in this
        # process lifetime so repeat invocations do not add a fresh
        # SystemMessage on every step.
        self._materialised: set[str] = set()

    @staticmethod
    def _thread_id(runtime: Runtime[Any]) -> str | None:
        """Best-effort pull of the LangGraph thread_id from the runtime."""
        ctx = getattr(runtime, "config", None) or {}
        configurable = ctx.get("configurable") if isinstance(ctx, dict) else None
        if isinstance(configurable, dict):
            tid = configurable.get("thread_id")
            if isinstance(tid, str) and tid:
                return tid
        return None

    def _resolve_target_dir(self, runtime: Runtime[Any]) -> Path:
        thread_id = self._thread_id(runtime) or self._fallback
        target = self._root / thread_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    def before_agent(
        self,
        state: AgentState,
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Scan ``state.files`` for new uploads and materialise them."""
        files = state.get("files") if isinstance(state, dict) else None
        if not isinstance(files, dict) or not files:
            return None

        target_dir = self._resolve_target_dir(runtime)
        fresh: list[tuple[str, Path]] = []

        for raw_key, value in files.items():
            if not isinstance(raw_key, str):
                continue
            norm_key = raw_key if raw_key.startswith("/") else "/" + raw_key
            if not norm_key.startswith(UPLOADED_PREFIX):
                continue
            if norm_key in self._materialised:
                continue

            # Require exact shape ``/uploaded/<single-component>`` so
            # traversal (``..``) and nested paths cannot sneak into the
            # host filesystem via state keys.
            segments = norm_key.split("/")
            if len(segments) != 3 or segments[0] != "" or segments[1] != "uploaded":
                logger.warning(
                    "Skipping upload key with disallowed shape: %r", norm_key
                )
                continue
            filename = segments[2]
            if not filename or not _SAFE_FILENAME.match(filename):
                logger.warning("Skipping upload with unsafe filename: %r", norm_key)
                continue

            payload = _decode_payload(value)
            if payload is None:
                # Not a base64 binary upload (e.g. plain-text message).
                # UIUploadBackend already exposes the text to `read_file`;
                # nothing to materialise.
                self._materialised.add(norm_key)
                continue

            host_path = target_dir / filename
            try:
                host_path.write_bytes(payload)
            except OSError:
                logger.exception(
                    "Failed to materialise upload %s to %s", norm_key, host_path
                )
                continue

            self._materialised.add(norm_key)
            fresh.append((norm_key, host_path))

        if not fresh:
            return None

        lines = [f"- `{key}` -> host path: `{path}`" for key, path in fresh]
        hint = (
            "[UI_UPLOADS_MATERIALIZED]\n"
            "The following user uploads are now available on the host "
            "filesystem. When a tool expects a real sample path (e.g. "
            "`file_identify`), pass the **host path** rather than the "
            "`/uploaded/...` virtual path:\n" + "\n".join(lines)
        )
        return {"messages": [SystemMessage(content=hint)]}


__all__ = ["UploadMaterializerMiddleware"]
