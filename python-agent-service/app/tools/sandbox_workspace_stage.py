"""Resolve SecManus workspace virtual paths for E2B staging uploads.

Maps agent-visible ``/workspace/...`` and legacy ``/uploads/...`` paths to
on-disk files under the current workspace scope, then builds sandbox-local paths
under ``/workspace/<project_slug>/<basename>`` plus substitution pairs for command
rewrite.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.analyze_request_context import (
    get_analyze_project_id,
    get_analyze_session_id,
    get_analyze_user_id,
)
from app.backends.path_aliases import canonicalize_agent_path
from app.backends.workspace_facade import _to_inner
from app.backends.workspace_scope import get_workspace_scope_root
from app.config.settings import get_settings
from app.services.upload_path_auth import (
    authorize_virtual_path,
    sanitize_path_segment,
)


def staging_project_slug() -> str:
    """Filesystem-safe slug from current analyze project_id or session_id."""
    pid = get_analyze_project_id()
    sid = get_analyze_session_id()
    raw = pid or sid or "default"
    return sanitize_path_segment(str(raw), max_len=128)


def staging_workspace_prefix() -> str:
    """Sandbox-local prefix ``/workspace/<slug>/`` for staged VM copies."""
    return f"/workspace/{staging_project_slug()}/"


def strip_workspace_staging_for_guard(text: str) -> str:
    """Mask staged ``/workspace/<slug>/…`` spans so host-path guards ignore them."""
    if not text:
        return text
    prefix = staging_workspace_prefix()
    pat = re.compile(re.escape(prefix) + r"[^\s'\";`|&)]+")
    return pat.sub(lambda m: " " * len(m.group(0)), text)


def _strip_shell_junk(raw: str) -> str:
    return raw.rstrip(",);]`}>")

_WS_SEG_RE = re.compile(
    r"(?:"
    r"/workspace/[^\s'\"`;|&)]+"
    r"|/uploads/[^\s'\"`;|&)]+"
    r"|(?<![\w/])workspace/[^\s'\"`;|&)]+"
    r")",
    re.IGNORECASE,
)


def extract_workspace_paths_from_command(command: str) -> list[str]:
    """Find virtual path tokens inside a shell command string."""
    found: list[str] = []
    seen: set[str] = set()
    for m in _WS_SEG_RE.finditer(command or ""):
        tok = _strip_shell_junk(m.group(0))
        if not tok:
            continue
        canon = canonicalize_agent_path(tok)
        if canon not in seen:
            seen.add(canon)
            found.append(canon)
    return found


def _rewrite_variants(canonical_vp: str) -> list[str]:
    """Substitution keys longest-first for ``command`` rewriting."""
    keys = [canonical_vp]
    if canonical_vp.startswith("/workspace/"):
        tail = canonical_vp[len("/workspace/"):]
        keys.append("workspace/" + tail)
    uniq: list[str] = []
    seen: set[str] = set()
    for k in sorted(keys, key=len, reverse=True):
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


def _unique_staged_filename(safe_base: str, used_names: set[str]) -> str:
    """Pick ``stem.ext`` then ``stem_2.ext`` … until unique within one staging batch."""
    if safe_base not in used_names:
        used_names.add(safe_base)
        return safe_base
    if "." in safe_base:
        stem_main, _, ext = safe_base.rpartition(".")
        ext_full = "." + ext
    else:
        stem_main = safe_base
        ext_full = ""
    n = 2
    while True:
        cand = f"{stem_main}_{n}{ext_full}"
        if cand not in used_names:
            used_names.add(cand)
            return cand
        n += 1


def _inner_within_workspace_scope(inner_path: str) -> bool:
    root = get_workspace_scope_root()
    if not root:
        return True
    ip = inner_path if inner_path.startswith("/") else "/" + inner_path
    rp = root if root.startswith("/") else "/" + root
    rp = rp.rstrip("/")
    ip_norm = "/" + ip.strip("/")
    return ip_norm == rp or ip_norm.startswith(rp + "/")


def resolve_workspace_virtual_to_disk(
    canon: str,
    upload_dir: Path,
) -> tuple[Path | None, str]:
    """Resolve virtual path to an authorized on-disk file."""
    settings = get_settings()
    uid = get_analyze_user_id()
    sid = get_analyze_session_id() or ""
    pid = get_analyze_project_id()

    ok, disk, msg = authorize_virtual_path(
        canon,
        upload_dir=upload_dir,
        user_id=uid,
        session_id=sid,
        project_id=pid,
        allow_legacy_flat=settings.allow_legacy_flat_upload_paths,
    )
    if ok and disk is not None and disk.is_file():
        return disk, ""

    inner = _to_inner(canon)
    if inner is None:
        return None, msg or "cannot_resolve_workspace_path"

    inner_norm = inner if inner.startswith("/") else "/" + inner
    if not _inner_within_workspace_scope(inner_norm):
        return None, msg or "outside_workspace_scope"

    try:
        disk2 = (upload_dir / inner_norm.lstrip("/")).resolve()
        upload_resolved = upload_dir.resolve()
        disk2.relative_to(upload_resolved)
    except ValueError:
        return None, "outside_upload_dir"

    if disk2.is_file():
        return disk2, ""
    return None, msg or "file_not_found"


def prepare_workspace_staging(
    *,
    workspace_stage_paths: list[str] | None,
    command: str,
    auto_extract_from_command: bool,
    upload_dir: Path,
    max_bytes_per_file: int,
) -> tuple[list[tuple[str, bytes]], list[tuple[str, str]], str | None]:
    """Build sandbox uploads (path + raw bytes) and command substitution pairs.

    Returns ``(uploads, replacements_longest_old_first, error_message)``.
    """
    collected: list[str] = []
    if workspace_stage_paths:
        for raw in workspace_stage_paths:
            s = (raw or "").strip()
            if s:
                collected.append(canonicalize_agent_path(s))
    if auto_extract_from_command:
        collected.extend(extract_workspace_paths_from_command(command))

    seen_vp: set[str] = set()
    ordered: list[str] = []
    for vp in collected:
        if vp not in seen_vp:
            seen_vp.add(vp)
            ordered.append(vp)

    uploads: list[tuple[str, bytes]] = []
    replacements: list[tuple[str, str]] = []
    slug = staging_project_slug()
    used_staged_names: set[str] = set()

    for vp in ordered:
        disk, err = resolve_workspace_virtual_to_disk(vp, upload_dir)
        if disk is None:
            return [], [], err or "staging_failed"

        try:
            size = disk.stat().st_size
        except OSError as exc:
            return [], [], f"cannot_stat:{disk}:{exc}"

        if size > max_bytes_per_file:
            msg = (
                f"staged_file_too_large:{vp} ({size} bytes; "
                f"max {max_bytes_per_file})"
            )
            return [], [], msg

        try:
            content = disk.read_bytes()
        except OSError as exc:
            return [], [], f"cannot_read:{disk}:{exc}"

        safe_base = sanitize_path_segment(
            disk.name.replace("\\", "/").split("/")[-1],
            max_len=180,
        )
        fname = _unique_staged_filename(safe_base, used_staged_names)
        dest = f"/workspace/{slug}/{fname}"
        uploads.append((dest, content))

        for variant in _rewrite_variants(vp):
            replacements.append((variant, dest))

    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    return uploads, replacements, None


def rewrite_command_workspace_paths(
    command: str,
    replacements_longest_first: list[tuple[str, str]],
) -> str:
    """Replace virtual path literals with sandbox destinations."""
    out = command
    for old, new in replacements_longest_first:
        out = out.replace(old, new)
    return out
