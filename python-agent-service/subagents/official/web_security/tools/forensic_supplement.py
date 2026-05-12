"""Deterministic forensic excerpts and capability matrix for webshell/hosted-code triage.

Surfaces what analysts often obtain via SReadFile + grep: banners, credential hints,
reverse-shell primitives, DB/mail/proxy use, UA filtering, and decode chains — without
asking the LLM to mine the file again.
"""

from __future__ import annotations

import re

from .models import CapabilityMatrixRow, ForensicSnippet, ForensicSupplement

_MAX_JOINED = 500_000
_MAX_HEADER = 2000
_MAX_SNIP = 260

# --- High-signal capability rows (stable ids for reports / UI) ---

_MATRIX_ROWS: tuple[tuple[str, str, str], ...] = (
    ("os_command", "OS command execution", "os_command"),
    ("reverse_or_bind_shell", "Reverse / bind shell primitives", "reverse_or_bind_shell"),
    ("dynamic_eval", "Dynamic code execution (eval/assert/…)", "dynamic_eval"),
    ("file_manager", "File manager / upload / delete", "file_manager"),
    ("database_access", "Database client / SQL", "database_access"),
    ("mail_or_smtp", "Mail / SMTP abuse", "mail_or_smtp"),
    ("proxy_port_scan", "Proxy, port scan, or SOCKS", "proxy_port_scan"),
    ("credential_gate", "Password gate / hard-coded credentials", "credential_gate"),
    ("crawler_or_waf_evasion", "Crawler / UA / WAF evasion", "crawler_or_waf_evasion"),
    ("obfuscated_loader", "Encoded / compressed loader chain", "obfuscated_loader"),
)

# Pattern groups: (matrix_key, confidence, regex flags, pattern)
_PATTERNS: tuple[tuple[str, float, int, str], ...] = (
    (
        "reverse_or_bind_shell",
        0.88,
        re.I,
        r"(?:fsockopen|pfsockopen|stream_socket_client|socket_create|socket_connect)\s*\(",
    ),
    (
        "reverse_or_bind_shell",
        0.82,
        re.I,
        r"(?:proc_open|popen)\s*\([^)]*['\"]/(?:bin/)?(?:ba)?sh",
    ),
    ("reverse_or_bind_shell", 0.78, re.I, r"bash\s+-i\b|/dev/tcp/"),
    (
        "file_manager",
        0.72,
        re.I,
        r"\b(move_uploaded_file|rmdir|unlink|rename|chmod|copy)\s*\(",
    ),
    ("file_manager", 0.65, re.I, r"\bfile_get_contents\s*\([^)]*\$_(?:GET|POST|REQUEST)"),
    ("database_access", 0.8, re.I, r"mysqli?_connect\b|new\s+mysqli\b|PDO\s*\(|mysql_connect\s*\("),
    ("database_access", 0.72, re.I, r"\b(?:mysqli|PDO|sqlite3|pg_connect|oci_connect)\b"),
    ("mail_or_smtp", 0.75, re.I, r"\bmail\s*\(|PHPMailer|smtp\.|Swift_Mailer\b"),
    ("proxy_port_scan", 0.7, re.I, r"fopen\s*\(\s*['\"]tcp://|curl_exec\s*\(|SOCKS"),
    (
        "credential_gate",
        0.68,
        re.I,
        r"\$_(?:SESSION|COOKIE)\s*\[\s*['\"][^'\"]*(pass|pwd|auth)",
    ),
    ("credential_gate", 0.82, re.I, r"\b(?:password|passwd)\s*=\s*['\"]"),
    ("crawler_or_waf_evasion", 0.7, re.I, r"HTTP_USER_AGENT|HTTP_REFERER|stripos\s*\([^)]*bot"),
    (
        "obfuscated_loader",
        0.75,
        re.I,
        r"(?:base64_decode|gzinflate|gzuncompress|str_rot13|convert_uudecode)\s*\(",
    ),
)


def _truncate(text: str, limit: int) -> str:
    t = text.strip().replace("\r\n", "\n")
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "..."


def _mask_assignment_value(raw: str) -> str:
    """Mask plausible password literals inside captured strings."""
    s = raw.strip()
    if len(s) <= 2:
        return "[redacted]"
    if len(s) <= 8:
        return s[0] + "*" * (len(s) - 2) + s[-1]
    return s[:2] + "*" * min(16, len(s) - 4) + s[-2:]


def extract_file_header_preview(text: str, language: str) -> str:
    """Prefer opening block comment near start; otherwise first lines (PHP/JSP-ish)."""
    head = text[:4000]
    if language == "php":
        m = re.search(r"/\*[\s\S]{10,1600}?\*/", head)
        if m:
            return _truncate(m.group(0), _MAX_HEADER)
    lines = text.splitlines()[:80]
    return _truncate("\n".join(lines), _MAX_HEADER)


def _line_for_position(text: str, pos: int, window: int = 220) -> str:
    start = max(0, text.rfind("\n", 0, pos))
    line_start = start + 1 if start >= 0 else 0
    chunk = text[line_start : line_start + window * 2]
    line = chunk.split("\n")[0].strip()
    return _truncate(line, window)


def _collect_snippets_for_patterns(
    joined: str, row_key: str, max_snips: int = 2
) -> tuple[bool, float, list[str]]:
    snippets: list[str] = []
    best_conf = 0.0
    any_hit = False
    # OS command sinks (mirror webshell_intel but attach line context)
    if row_key == "os_command":
        pat = re.compile(
            r"\b(system|exec|shell_exec|passthru|popen|proc_open)\s*\(",
            re.I,
        )
        for m in pat.finditer(joined):
            any_hit = True
            best_conf = max(best_conf, 0.85)
            if len(snippets) < max_snips:
                snippets.append(_line_for_position(joined, m.start()))
        return bool(any_hit), (best_conf or 0.85), snippets

    if row_key == "dynamic_eval":
        pat = re.compile(
            r"\b(eval|assert|create_function)\s*\(",
            re.I,
        )
        for m in pat.finditer(joined):
            any_hit = True
            best_conf = max(best_conf, 0.82)
            if len(snippets) < max_snips:
                snippets.append(_line_for_position(joined, m.start()))
        return bool(any_hit), (best_conf or 0.82), snippets

    if row_key == "obfuscated_loader":
        pat = re.compile(
            r"(base64_decode\s*\(|gzinflate\s*\(|str_rot13\s*\(|gzuncompress\s*\()",
            re.I,
        )
        for m in pat.finditer(joined):
            any_hit = True
            best_conf = max(best_conf, 0.72)
            if len(snippets) < max_snips:
                snippets.append(_line_for_position(joined, m.start()))
        return bool(any_hit), (best_conf or 0.72), snippets

    # Generic pattern lookup from _PATTERNS
    for rk, conf, rflag, patt in _PATTERNS:
        if rk != row_key:
            continue
        rx = re.compile(patt, rflag)
        for m in rx.finditer(joined):
            any_hit = True
            best_conf = max(best_conf, conf)
            if len(snippets) < max_snips:
                snippets.append(_line_for_position(joined, m.start()))
    return bool(any_hit), best_conf, snippets[:max_snips]


def _credential_snippets(joined: str, max_snips: int = 4) -> list[ForensicSnippet]:
    out: list[ForensicSnippet] = []
    rx = re.compile(
        r"(?:\$|->)\s*[a-zA-Z_][a-zA-Z0-9_]{0,32}\s*=\s*"
        r"['\"]([a-zA-Z0-9_!@#$%^&*+.:-]{6,96})['\"]",
        re.I,
    )
    for m in rx.finditer(joined[:200000]):
        if len(out) >= max_snips:
            break
        raw = m.group(1)
        lowered = joined[max(0, m.start() - 40) : m.end() + 40].lower()
        if not any(k in lowered for k in ("pass", "pwd", "passwd", "auth", "salt", "key")):
            # Skip incidental string assignments unless context suggests credential.
            continue
        line = _line_for_position(joined, m.start())
        masked = line
        raw_sub = raw
        if raw_sub:
            masked = line.replace(raw_sub, _mask_assignment_value(raw_sub))
        out.append(ForensicSnippet(category="credential_literal", preview=masked))
    return out


def _extra_behavior_tags(
    rows: dict[str, tuple[bool, float]],
) -> list[str]:
    tags: list[str] = []
    if rows.get("reverse_or_bind_shell", (False, 0))[0]:
        tags.append("network_bind_or_reverse_capability")
    if rows.get("credential_gate", (False, 0))[0]:
        tags.append("authentication_gate_or_hardcoded_material")
    if rows.get("mail_or_smtp", (False, 0))[0]:
        tags.append("email_or_smtp_abuse_primitive")
    if rows.get("proxy_port_scan", (False, 0))[0]:
        tags.append("network_scan_or_proxy_primitive")
    if rows.get("database_access", (False, 0))[0]:
        tags.append("database_client_primitive")
    return sorted(tags)


def build_forensic_supplement(
    *,
    original: str,
    decoded_layers: list[str],
    language: str,
) -> tuple[ForensicSupplement, list[str]]:
    joined = original
    if decoded_layers:
        joined = original + "\n" + "\n".join(decoded_layers[:5])
    if len(joined) > _MAX_JOINED:
        joined = joined[:_MAX_JOINED]

    preview = extract_file_header_preview(original, language)

    rows_state: dict[str, tuple[bool, float]] = {}
    matrix_rows: list[CapabilityMatrixRow] = []

    for cid, label, row_key in _MATRIX_ROWS:
        detected = False
        conf = 0.0
        snippets: list[str] = []

        if row_key in ("file_manager", "database_access", "mail_or_smtp", "proxy_port_scan"):
            ok, cf, snippets = _collect_snippets_for_patterns(joined, row_key)
            detected = ok
            conf = cf
        elif row_key == "credential_gate":
            cred_snips = _credential_snippets(joined)
            if cred_snips:
                detected = True
                conf = 0.75
                snippets = [c.preview[: _MAX_SNIP] for c in cred_snips[:2]]
            # Also password= pattern via generic patterns
            ok, cf, sn2 = _collect_snippets_for_patterns(joined, "credential_gate")
            if ok:
                detected = True
                conf = max(conf, cf)
                for s in sn2:
                    if s not in snippets and len(snippets) < 2:
                        snippets.append(s)
        elif row_key == "crawler_or_waf_evasion":
            ok, cf, snippets = _collect_snippets_for_patterns(joined, row_key)
            detected = ok
            conf = cf
        elif row_key == "os_command":
            ok, cf, snippets = _collect_snippets_for_patterns(joined, "os_command")
            detected = ok
            conf = cf
        elif row_key == "dynamic_eval":
            ok, cf, snippets = _collect_snippets_for_patterns(joined, "dynamic_eval")
            detected = ok
            conf = cf
        elif row_key == "reverse_or_bind_shell":
            ok, cf, snippets = _collect_snippets_for_patterns(joined, "reverse_or_bind_shell")
            detected = ok
            conf = cf
        elif row_key == "obfuscated_loader":
            ok, cf, snippets = _collect_snippets_for_patterns(joined, "obfuscated_loader")
            detected = ok
            conf = cf
        else:
            ok, cf, snippets = False, 0.0, []

        rows_state[row_key] = (detected, conf)

        matrix_rows.append(
            CapabilityMatrixRow(
                id=cid,
                label=label,
                detected=detected,
                confidence=conf,
                snippets=snippets[:2],
            )
        )

    extra_behaviors = _extra_behavior_tags(rows_state)

    extra_snips: list[ForensicSnippet] = []
    extra_snips.extend(_credential_snippets(joined))

    # Dedupe forensic snippets by preview prefix
    seen: set[str] = set()
    deduped: list[ForensicSnippet] = []
    for fs in extra_snips:
        k = fs.preview[:80]
        if k in seen:
            continue
        seen.add(k)
        deduped.append(fs)

    supplement = ForensicSupplement(
        file_header_preview=preview,
        capability_matrix=sorted(matrix_rows, key=lambda r: r.id),
        snippets=sorted(deduped[:12], key=lambda s: (s.category, s.preview)),
    )
    return supplement, extra_behaviors
