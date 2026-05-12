"""Split main agent final AIMessage into task digest and full report (no extra LLM).

Machine anchors (exact line match after strip) — keep in sync with MASTER_AGENT.md:
  ## SM_FULL_REPORT
  ## SM_TASK_DIGEST

Preferred order: report-first (new).  Legacy digest-first is still accepted for
backward compatibility with old sessions / cached model outputs.
"""

from __future__ import annotations

import re
from typing import Any

# Hiragana/Katakana + CJK Unified + CJK Compatibility (incl. 中文 / 日文 / 韓文常用區)
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")

DIGEST_HEADING = "## SM_TASK_DIGEST"
REPORT_HEADING = "## SM_FULL_REPORT"

# Subagent final message: visible SSE shows WRAPUP only; FULL_REPORT stays for parent tool return.
SUBAGENT_WRAPUP_HEADING = "## SM_SUBAGENT_WRAPUP"
SUBAGENT_FULL_HEADING = "## SM_SUBAGENT_FULL_REPORT"

# Sentinel that subagents emit before the machine-only stats payload (fenced
# JSON block carrying ``research_stats`` or ``findings``). The chat UI must
# never display the sentinel or anything after it; ``stats_meta`` parsers read
# the JSON from the *raw* task output, where the sentinel is harmless.
SUBAGENT_STATS_PAYLOAD_HEADING = "### SM_STATS_PAYLOAD"


def _strip_stats_payload_tail(text: str) -> str:
    """Truncate at the first ``### SM_STATS_PAYLOAD`` line (inclusive).

    Returns the trimmed prose with trailing whitespace removed. If the
    sentinel is absent the input is returned unchanged (modulo right-strip
    handled by callers).
    """
    if not text:
        return text
    # Match the sentinel as a line-anchored heading; ignore trailing inline
    # whitespace on that line.
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == SUBAGENT_STATS_PAYLOAD_HEADING:
            return "".join(lines[:i]).rstrip()
    return text

# Heuristic fallback when anchors are missing (must stay LLM-free).
_MAX_DIGEST_BLOCK_CHARS = 600
_TRUNCATE_DIGEST_CHARS = 500

# Subagent SSE: keep streamed visible body short when model omits anchors.
_MAX_SUBAGENT_WRAPUP_HEURISTIC_CHARS = 800
_TRUNCATE_SUBAGENT_WRAPUP_CHARS = 500

# Body-first layout: report markdown before the first ## SM_SUBAGENT_WRAPUP (no duplicate under FULL).
def _substantial_prefix_for_body_first(prefix: str) -> bool:
    """True when text before the first WRAPUP heading is plausibly the real report body."""
    p = (prefix or "").strip()
    if len(p) < 200:
        return False
    if p.lstrip().startswith("#"):
        return True
    if "\n## " in p or "\n# " in p:
        return True
    return len(p) >= 2500


def split_final_assistant_message(text: str) -> tuple[str | None, str | None]:
    """Parse digest and report from anchored final message.

    Accepts both orderings:
      * **New (preferred):** ``## SM_FULL_REPORT`` then ``## SM_TASK_DIGEST``
      * **Legacy:**          ``## SM_TASK_DIGEST`` then ``## SM_FULL_REPORT``

    Returns:
        (digest, report) — always in the same semantic order regardless of
        which markdown ordering the model used.
        (None, None) on any parse failure (missing heading / empty section).
    """
    if not text or not text.strip():
        return None, None

    lines = text.splitlines(keepends=True)
    digest_line_idx: int | None = None
    report_line_idx: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == DIGEST_HEADING and digest_line_idx is None:
            digest_line_idx = i
        elif stripped == REPORT_HEADING and report_line_idx is None:
            report_line_idx = i

    if digest_line_idx is None or report_line_idx is None:
        return None, None

    if report_line_idx < digest_line_idx:
        # New order: REPORT first, DIGEST second
        first_idx, second_idx = report_line_idx, digest_line_idx
        report = "".join(lines[first_idx + 1 : second_idx]).strip()
        digest = "".join(lines[second_idx + 1 :]).strip()
    else:
        # Legacy order: DIGEST first, REPORT second
        first_idx, second_idx = digest_line_idx, report_line_idx
        digest = "".join(lines[first_idx + 1 : second_idx]).strip()
        report = "".join(lines[second_idx + 1 :]).strip()

    if not digest or not report:
        return None, None

    return digest, report


def heuristic_subagent_sse_visible(full: str) -> str:
    """LLM-free short string for subagent ``llm_delta`` channel=text when anchors are absent."""
    full_stripped = full.strip()
    if not full_stripped:
        return ""

    if "\n\n" in full_stripped:
        first, _rest = full_stripped.split("\n\n", 1)
        first = first.strip()
        if first and len(first) <= _MAX_SUBAGENT_WRAPUP_HEURISTIC_CHARS:
            return first

    if len(full_stripped) <= _MAX_SUBAGENT_WRAPUP_HEURISTIC_CHARS:
        return full_stripped

    return full_stripped[:_TRUNCATE_SUBAGENT_WRAPUP_CHARS].rstrip() + "\n..."


def split_subagent_wrapup_and_full(text: str) -> tuple[str | None, str | None]:
    """Parse subagent WRAPUP (for SSE) and full report body (for parent / conclusion).

    Two layouts (both supported):

    1. **Body-first (preferred):** full markdown report, then ``## SM_SUBAGENT_WRAPUP``,
       then a short summary. Optional legacy ``## SM_SUBAGENT_FULL_REPORT`` tail is ignored
       when the prefix before WRAPUP is substantial — avoids duplicating the report under
       FULL_REPORT.

    2. **Classic:** only ``WRAPUP`` then ``FULL_REPORT`` sections (no substantive prefix).
    """
    if not text or not text.strip():
        return None, None

    lines = text.splitlines(keepends=True)
    wrap_line_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == SUBAGENT_WRAPUP_HEADING and wrap_line_idx is None:
            wrap_line_idx = i
            break

    if wrap_line_idx is None:
        return None, None

    prefix = "".join(lines[:wrap_line_idx]).strip()

    full_line_idx: int | None = None
    for j in range(wrap_line_idx + 1, len(lines)):
        if lines[j].strip() == SUBAGENT_FULL_HEADING:
            full_line_idx = j
            break

    if _substantial_prefix_for_body_first(prefix):
        if full_line_idx is not None:
            wrapup = "".join(lines[wrap_line_idx + 1 : full_line_idx]).strip()
        else:
            wrapup = "".join(lines[wrap_line_idx + 1 :]).strip()
        if not wrapup:
            wrapup = heuristic_subagent_sse_visible(prefix).strip()
        if not wrapup:
            return None, None
        return wrapup, prefix

    if full_line_idx is None or full_line_idx <= wrap_line_idx:
        return None, None

    wrapup = "".join(lines[wrap_line_idx + 1 : full_line_idx]).strip()
    full_report = "".join(lines[full_line_idx + 1 :]).strip()
    if not wrapup or not full_report:
        return None, None

    return wrapup, full_report


def subagent_sse_visible_text(visible_markdown: str) -> str:
    """Text to stream as subagent visible reply (not the full report).

    When the model uses body-first layout or classic ``WRAPUP``/``FULL_REPORT`` anchors,
    only the WRAPUP section is returned. Otherwise a bounded heuristic excerpt is used
    so the UI does not mirror the entire final report during streaming.

    Handles three layouts:
    1. Body-first: ``[full report]\n\n## SM_SUBAGENT_WRAPUP\n\n[summary]``
    2. Classic:    ``## SM_SUBAGENT_WRAPUP\n\n[summary]\n\n## SM_SUBAGENT_FULL_REPORT\n\n[full]``
    3. Wrapup-only: ``## SM_SUBAGENT_WRAPUP\n\n[summary]`` (no FULL_REPORT anchor)
    """
    raw = (visible_markdown or "").strip()
    if not raw:
        return ""

    wrapup, _full = split_subagent_wrapup_and_full(raw)
    if wrapup is not None and wrapup.strip():
        # Strip the machine-only stats payload (sentinel + fenced JSON) before
        # the wrapup is streamed to the chat UI.
        return _strip_stats_payload_tail(wrapup).strip()

    # Wrapup-only format: WRAPUP heading present but no FULL_REPORT anchor and no
    # substantial body prefix.  split_subagent_wrapup_and_full returns (None, None)
    # here, and the heuristic fallback would incorrectly return the heading line
    # itself ("## SM_SUBAGENT_WRAPUP") as the first paragraph.
    # Extract the text after the heading directly instead.
    lines = raw.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == SUBAGENT_WRAPUP_HEADING:
            after = "".join(lines[i + 1:]).strip()
            if after:
                trimmed = _strip_stats_payload_tail(after).strip()
                return heuristic_subagent_sse_visible(trimmed) if trimmed else ""
            break

    return heuristic_subagent_sse_visible(_strip_stats_payload_tail(raw))


def strip_digest_tail(text: str) -> str:
    """Remove a trailing ``## SM_TASK_DIGEST`` section from conclusion content.

    For complex-task flows the digest is already split into ``task_summary``;
    for simple chat-only replies the digest tail is redundant and should not
    appear in the user-visible conclusion.
    """
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == DIGEST_HEADING:
            return "".join(lines[:i]).rstrip()
    return text


def strip_conclusion_machine_tails(text: str) -> str:
    """Remove all machine-only tails before forwarding ``text`` to chat / persistence.

    The conclusion event content must never carry the ``### SM_STATS_PAYLOAD``
    sentinel + fenced JSON tail (machine-readable stats) or the
    ``## SM_TASK_DIGEST`` digest tail (split off into ``task_summary`` already).
    Both can survive ``heuristic_digest_and_report`` when subagents emit a
    body+sentinel layout *without* the canonical ``## SM_SUBAGENT_WRAPUP``
    heading, which is the regression observed when deep-research agents put the
    sentinel directly after their prose. Strip the earliest of the two markers
    so whichever tail comes first wins, and the other is removed naturally as
    part of the dropped suffix.
    """
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    cut: int | None = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s == SUBAGENT_STATS_PAYLOAD_HEADING or s == DIGEST_HEADING:
            cut = i
            break
    if cut is None:
        return text
    return "".join(lines[:cut]).rstrip()


def strip_leading_preface_before_cjk_report_body(
    text: str,
    *,
    min_cjk_in_paragraph: int = 10,
) -> str:
    """Drop leading English/thinking paragraphs when a later paragraph is clearly CJK body.

    Models often prepend chain-of-thought prose (e.g. \"Analyzing…\") before the real
    user-facing report in Chinese. No-op when no paragraph reaches ``min_cjk_in_paragraph``.
    """
    t = (text or "").strip()
    if not t:
        return t
    parts = re.split(r"\n\s*\n+", t)
    for i, para in enumerate(parts):
        p = para.strip()
        if not p:
            continue
        cjk_n = len(_CJK_RE.findall(p))
        if cjk_n >= min_cjk_in_paragraph:
            return "\n\n".join(x.strip() for x in parts[i:] if x.strip()).strip()
    return t


def heuristic_digest_and_report(full: str) -> tuple[str, str]:
    """LLM-free fallback: derive a short digest and keep full text as report body.

    Used when ``split_final_assistant_message`` fails. Logs are emitted by caller.
    """
    full_stripped = full.strip()
    if not full_stripped:
        return "", ""

    if "\n\n" not in full_stripped:
        if len(full_stripped) <= _MAX_DIGEST_BLOCK_CHARS:
            return full_stripped, full_stripped
        return (
            full_stripped[:_TRUNCATE_DIGEST_CHARS].rstrip() + "\n...",
            full_stripped,
        )

    first, rest = full_stripped.split("\n\n", 1)
    first = first.strip()
    rest = rest.strip()

    if len(first) <= _MAX_DIGEST_BLOCK_CHARS and rest:
        return first, rest

    if len(first) > _MAX_DIGEST_BLOCK_CHARS:
        return first[:_TRUNCATE_DIGEST_CHARS].rstrip() + "\n...", full_stripped

    if not rest:
        return first, full_stripped

    return first, rest


def subagent_output_metrics(text: str) -> dict[str, Any]:
    """Structured lengths for research run logs and diagnostics (JSON-serializable).

    ``subagent_full_report_char_count`` reflects the parsed conclusion body (body-first
    prefix or classic FULL section). ``content_before_first_wrapup_char_count`` is the raw
    prefix length before the first WRAPUP heading (diagnostics only).
    """
    raw = (text or "").strip()
    out: dict[str, Any] = {
        "final_text_char_count": len(raw),
        "first_wrapup_heading_found": False,
        "content_before_first_wrapup_char_count": None,
        "subagent_anchors_parsed": False,
        "subagent_wrapup_char_count": None,
        "subagent_full_report_char_count": None,
    }
    if not raw:
        return out

    lines = raw.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == SUBAGENT_WRAPUP_HEADING:
            out["first_wrapup_heading_found"] = True
            before = "".join(lines[:i]).strip()
            out["content_before_first_wrapup_char_count"] = len(before)
            break

    wrapup, full_report = split_subagent_wrapup_and_full(raw)
    if wrapup is not None and full_report is not None:
        out["subagent_anchors_parsed"] = True
        out["subagent_wrapup_char_count"] = len(wrapup)
        out["subagent_full_report_char_count"] = len(full_report)

    return out
