"""Infer primary hosted-code language (PHP, JSP, Python, ASPX).

Priority when markers conflict: PHP → JSP → Python → ASPX (see design.md).
"""

from __future__ import annotations

import re

# e.g. `#!/usr/bin/python3` or `#!/usr/bin/env python3`
_PYTHON_SHEBANG = re.compile(r"^#!.+\bpython\d?\b", re.MULTILINE)


def _looks_aspx(text: str) -> bool:
    """
    ASPX / WebForms markers (avoid treating JSP `<%@ page import=...` as ASPX).

    Do not use `<%@ Page` alone; JSP has similar page directives.
    """
    if re.search(r'runat\s*=\s*["\']server["\']', text, re.IGNORECASE):
        return True
    if re.search(r'Language\s*=\s*["\']C#', text, re.IGNORECASE):
        return True
    if re.search(r'Language\s*=\s*["\']VB', text, re.IGNORECASE):
        return True
    if re.search(
        r"<%@\s*Page\b[^%]{0,400}(CodeFile|Inherits|MasterPageFile|Async)\s*=",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    return False


def has_hosted_code_markers(content: str) -> bool:
    """True if text looks like hosted source (not only HTTP traffic)."""
    return infer_hosted_language(content) != "unknown"


def infer_hosted_language(content: str) -> str:
    """
    Return primary hosted-code language label.
    """
    if not content or not content.strip():
        return "unknown"

    text = content

    if "<?php" in text or "<?=" in text:
        return "php"

    # ASPX before generic JSP `<%@ page`.
    if _looks_aspx(text):
        return "aspx"

    # JSP directive (often lowercase 'page') or scriptlets
    if re.search(r"<%@\s*page\b", text, re.IGNORECASE):
        return "jsp"
    if "<%" in text or "%>" in text:
        return "jsp"

    if _PYTHON_SHEBANG.search(text):
        return "python"
    if _python_webshell_heuristic(text):
        return "python"
    if re.search(
        r"<html\b|<script\b|dangerouslySetInnerHTML|\.innerHTML\s*=",
        text,
        re.IGNORECASE,
    ):
        return "html"
    if re.search(
        r"\b(document\.write|window\.location|child_process\.|eval\s*\()",
        text,
        re.IGNORECASE,
    ):
        return "javascript"

    return "unknown"


def _python_webshell_heuristic(text: str) -> bool:
    """High-precision heuristic for bare .py webshells without shebang."""
    if len(text) > 200_000:
        return False
    has_import = bool(
        re.search(
            r"^\s*(import\s+(os|subprocess|sys)"
            r"|from\s+(os|subprocess)\s+import)",
            text,
            re.MULTILINE,
        )
    )
    has_sink = bool(
        re.search(
            r"\b(eval|exec|__import__|compile)\s*\("
            r"|subprocess\.(run|call|Popen|check_output)\s*\("
            r"|os\.(system|popen|spawn|execv|execl)\s*\(",
            text,
            re.IGNORECASE,
        )
    )
    return has_import and has_sink
