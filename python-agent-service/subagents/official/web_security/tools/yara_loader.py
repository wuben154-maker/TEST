"""Resolve absolute path to web-security skill YARA rules directory."""

from __future__ import annotations

import os
from pathlib import Path

from app.config.settings import SERVICE_ROOT

DEFAULT_RELATIVE_YARA_DIR = Path("subagents/official/web_security/skills/web_security/yara")


def resolve_web_security_yara_dir() -> Path:
    """
    Rules ship under the official web-security skill bundle (real files on disk).

    Override with WEB_THREAT_YARA_RULES_DIR (absolute or relative to SERVICE_ROOT).
    """
    override = os.environ.get("WEB_THREAT_YARA_RULES_DIR", "").strip()
    if override:
        p = Path(override)
        return p if p.is_absolute() else (SERVICE_ROOT / p).resolve()
    return (SERVICE_ROOT / DEFAULT_RELATIVE_YARA_DIR).resolve()
