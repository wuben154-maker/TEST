"""Infer artifact_type from raw text and optional hint."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import unquote

from .code_language import has_hosted_code_markers
from .models import ArtifactType

Hint = Literal["auto", "http", "code"]


_HTTP_FIRST = re.compile(
    r"^\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|CONNECT|TRACE)\s+\S+",
    re.IGNORECASE | re.MULTILINE,
)


def classify_artifact(text: str, hint: str) -> ArtifactType:
    """Classify input as HTTP traffic, hosted code, mixed, or unknown."""
    h = (hint or "auto").strip().lower()
    if h == "http":
        return "http_traffic"
    if h == "code":
        return "webshell_or_code"

    has_code = has_hosted_code_markers(text)
    has_http = bool(_HTTP_FIRST.search(text))
    stripped = text.strip()
    decoded = unquote(stripped)
    if stripped.startswith(("http://", "https://")):
        has_http = True
    if re.search(r'"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+\S+\s+HTTP/\d', text, re.I):
        has_http = True

    if has_http and has_code:
        return "mixed"
    if has_http:
        return "http_traffic"
    if has_code:
        return "webshell_or_code"
    # Likely raw payload or log fragment without verb line
    if re.search(r"\b(union\s+select|javascript:|<script|onerror\s*=)\b", decoded, re.I):
        return "http_traffic"
    return "unknown"
