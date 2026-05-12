"""Server-side artifact store for uploaded files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


class ArtifactStore:
    """Persist uploaded artifacts and return local server paths."""

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(
        self,
        *,
        session_id: str,
        filename: str,
        content: Any,
        fallback_text: str = "",
    ) -> str:
        """Save file content under session folder and return absolute path."""
        safe_session = self._safe_segment(session_id or "default")
        safe_filename = self._safe_segment(filename or "artifact.bin")
        payload = self._to_bytes(content, fallback_text=fallback_text)
        digest = hashlib.sha256(payload).hexdigest()[:12]
        target_dir = self.base_dir / safe_session
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{digest}_{safe_filename}"
        target_path.write_bytes(payload)
        return str(target_path.resolve())

    @staticmethod
    def _safe_segment(value: str) -> str:
        chars = []
        for char in value:
            if char.isalnum() or char in ("-", "_", "."):
                chars.append(char)
            else:
                chars.append("_")
        return "".join(chars)[:120] or "artifact"

    @staticmethod
    def _to_bytes(content: Any, *, fallback_text: str) -> bytes:
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            return content.encode("utf-8", errors="replace")
        if content is None:
            return (fallback_text or "").encode("utf-8", errors="replace")
        return str(content).encode("utf-8", errors="replace")
