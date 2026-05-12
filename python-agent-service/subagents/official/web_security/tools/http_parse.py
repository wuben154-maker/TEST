"""Best-effort HTTP request text parser (method, path, headers, body, query)."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class ParsedHttpRequest:
    """Structured view of a raw HTTP request or log fragment."""

    ok: bool = False
    method: str = ""
    path: str = ""
    query_string: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    errors: list[str] = field(default_factory=list)
    query_location_prefix: str = "query"


_FIRST_LINE_RE = re.compile(
    r"^(?P<method>[A-Z]+)\s+(?P<target>\S+)(?:\s+HTTP/\d[\d.]*\s*)?$",
    re.IGNORECASE,
)


def parse_http_request(raw: str) -> ParsedHttpRequest:
    """Split raw text into HTTP components; tolerant of malformed input."""
    out = ParsedHttpRequest()
    if not raw or not raw.strip():
        out.errors.append("empty_input")
        return out

    text = _normalize_url_or_log(raw.replace("\r\n", "\n"))
    if text.startswith("__SECMANUS_LOG_REQUEST__\n"):
        out.query_location_prefix = "log.request_uri"
        text = text.split("\n", 1)[1]
    lines = text.split("\n")

    # Find first non-empty line as request line
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        out.errors.append("no_request_line")
        return out

    m = _FIRST_LINE_RE.match(lines[idx].strip())
    if not m:
        out.errors.append("request_line_unparsed")
        return out

    out.method = m.group("method").upper()
    target = m.group("target")
    # Split path and query from target (may be absolute URL or path)
    if target.startswith("http://") or target.startswith("https://"):
        p = urlparse(target)
        out.path = p.path or "/"
        out.query_string = p.query or ""
    else:
        if "?" in target:
            path_part, qs = target.split("?", 1)
            out.path = path_part
            out.query_string = qs
        else:
            out.path = target

    idx += 1
    # Headers until blank line
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            break
        if ":" in line:
            k, v = line.split(":", 1)
            key = k.strip().lower()
            out.headers[key] = v.strip()
        idx += 1

    # Rest is body
    if idx < len(lines):
        out.body = "\n".join(lines[idx:])

    out.ok = True
    return out


def iter_query_params(query_string: str) -> list[tuple[str, str]]:
    """Yield (name, decoded_value) pairs from application/x-www-form-urlencoded query."""
    if not query_string:
        return []
    parsed = parse_qs(query_string, keep_blank_values=True)
    result: list[tuple[str, str]] = []
    for name, values in parsed.items():
        for v in values:
            result.append((name, unquote(v.replace("+", " "))))
    return result


def iter_body_params(body: str, content_type: str | None) -> list[tuple[str, str]]:
    """Parse supported body fields into (location_suffix, value) pairs."""
    ct = (content_type or "").lower()
    if "application/json" in ct and body.strip():
        try:
            parsed = json.loads(body)
            return list(_flatten_json(parsed))
        except Exception:
            return []
    if "application/x-www-form-urlencoded" in ct or (
        not ct and "=" in body and "&" in body and body.strip()
    ):
        try:
            parsed = parse_qs(body, keep_blank_values=True)
            out: list[tuple[str, str]] = []
            for name, values in parsed.items():
                for v in values:
                    out.append((name, unquote(v.replace("+", " "))))
            return out
        except Exception:
            return []
    return []


def iter_cookies(cookie_header: str) -> list[tuple[str, str]]:
    """Parse a Cookie header into name/value pairs."""
    out: list[tuple[str, str]] = []
    for chunk in cookie_header.split(";"):
        if "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        if name:
            out.append((name, unquote(value.strip())))
    return out


def _flatten_json(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_json(child, next_prefix)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            next_prefix = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            yield from _flatten_json(child, next_prefix)
    else:
        yield prefix or "$", str(value)


def _normalize_url_or_log(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith(("http://", "https://")):
        return f"GET {stripped} HTTP/1.1\nHost: url-only\n\n"
    m = re.search(r'"(?P<method>GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(?P<target>\S+)\s+HTTP/\d[\d.]*"', raw, re.I)
    if not m:
        return raw
    target = m.group("target")
    method = m.group("method").upper()
    normalized = f"{method} {target} HTTP/1.1\nHost: log-entry\n\n"
    # Marker consumed after parsing so evidence can distinguish log-derived URIs.
    return "__SECMANUS_LOG_REQUEST__\n" + normalized


def infer_param_context(param_name: str, value: str) -> str:
    """Heuristic injection context label for a parameter."""
    lower = param_name.lower()
    if any(x in lower for x in ("callback", "jsonp", "script")):
        return "js_string"
    if any(x in lower for x in ("html", "content", "desc", "message", "body", "comment")):
        return "html_text"
    if any(x in lower for x in ("url", "redirect", "next", "return", "dest")):
        return "raw"
    if "<" in value or "script" in value.lower():
        return "html_text"
    return "unknown"
