"""LangChain message content normalization.

Two concerns:

1. **Handoff** — ``AIMessage`` thinking + visible text for parent tool results.
2. **LLM visible content normalization** — LLMs sometimes emit structured JSON
   (e.g. ``{"need_clarification": …}``) instead of plain prose.  A registry of
   known envelope patterns extracts the user-visible text so raw JSON never
   leaks to the UI.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import AIMessage


def reasoning_text_from_reasoning_block(block: dict) -> str:
    """Extract plaintext reasoning from LangChain/OpenRouter Gemini-style blocks.

    Structured as ``{\"type\": \"reasoning\", \"content\": [{\"type\": \"reasoning_text\", \"text\": ...}]}``.
    Encrypted tails are omitted (no plaintext).
    """
    if block.get("type") != "reasoning":
        return ""
    pieces: list[str] = []
    inner = block.get("content")
    if isinstance(inner, list):
        for item in inner:
            if not isinstance(item, dict):
                continue
            typ = item.get("type")
            if typ in ("reasoning_text", "reasoning.text"):
                tx = item.get("text")
                if isinstance(tx, str):
                    pieces.append(tx)
            elif isinstance(item.get("text"), str):
                pieces.append(item["text"])
    summary = block.get("summary")
    if isinstance(summary, list):
        for s in summary:
            if isinstance(s, str) and s.strip():
                pieces.append(s)
            elif isinstance(s, dict):
                tx = s.get("text")
                if isinstance(tx, str) and tx.strip():
                    pieces.append(tx)
    return "".join(pieces).strip()


def _reasoning_details_plaintext(reasoning_details: Any) -> str:
    """OpenRouter ``message.reasoning_details``: use ``reasoning.text`` entries only."""
    if not isinstance(reasoning_details, list):
        return ""
    chunks: list[str] = []
    for item in reasoning_details:
        if isinstance(item, dict) and item.get("type") == "reasoning.text":
            tx = item.get("text")
            if isinstance(tx, str) and tx.strip():
                chunks.append(tx.strip())
    return "\n\n".join(chunks).strip()


def additional_kwargs_reasoning_text(additional: Any) -> str:
    """Return chain-of-thought string from ``AIMessage.additional_kwargs``.

    Covers OpenAI ``reasoning_content``, OpenRouter ``reasoning`` (plaintext;
    documented alias of ``reasoning_content``), optional ``reasoning_details``
    (``reasoning.text`` items), and rare structured payloads.
    """
    if not isinstance(additional, dict):
        return ""
    rc = additional.get("reasoning_content")
    if isinstance(rc, str) and rc.strip():
        return rc.strip()
    rn = additional.get("reasoning")
    if isinstance(rn, str) and rn.strip():
        return rn.strip()
    if isinstance(rn, dict):
        summary = rn.get("summary") or rn.get("text") or rn.get("content")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    rd_plain = _reasoning_details_plaintext(additional.get("reasoning_details"))
    if rd_plain:
        return rd_plain
    return ""


# ---------------------------------------------------------------------------
# Pattern registry for ``normalize_llm_visible_content``
# ---------------------------------------------------------------------------
# Each entry is (predicate, extractor).
#   predicate(data: dict) -> bool   — does this dict match the pattern?
#   extractor(data: dict) -> str    — pull user-visible text out of it.
# Order matters: first match wins.

_JsonPatternEntry = tuple[Callable[[dict], bool], Callable[[dict], str]]


def _is_clarification_envelope(data: dict) -> bool:
    return "need_clarification" in data


def _extract_clarification_text(data: dict) -> str:
    need = bool(data.get("need_clarification", False))
    question = str(data.get("question", "") or "").strip()
    verification = str(data.get("verification", "") or "").strip()
    if need:
        return question
    return verification


def _is_intent_understanding(data: dict) -> bool:
    return "task_category" in data or (
        "input_type" in data and "context_reasoning" in data
    )


def _extract_intent_text(_data: dict) -> str:
    return ""


_JSON_PATTERNS: list[_JsonPatternEntry] = [
    (_is_clarification_envelope, _extract_clarification_text),
    (_is_intent_understanding, _extract_intent_text),
]


def _try_extract_json_object(text: str) -> dict | None:
    """Best-effort extraction of a JSON object from ``text``.

    Handles leading prose before ``{``, trailing text after ``}``, and
    nested braces inside JSON string values.  Iterates closing-brace
    positions from left to right until ``json.loads`` succeeds.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    start = 0
    if not raw.startswith("{"):
        start = raw.find("{")
        if start < 0:
            return None

    search_from = start + 1
    while search_from < len(raw):
        idx = raw.find("}", search_from)
        if idx < 0:
            break
        candidate = raw[start:idx + 1]
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            search_from = idx + 1
            continue
        if isinstance(data, dict):
            return data
        search_from = idx + 1
    return None


def normalize_llm_visible_content(text: str) -> str:
    """Normalize LLM output to user-visible plain text.

    Walks ``_JSON_PATTERNS``; if the text contains a recognized JSON envelope
    the corresponding extractor returns the user-facing string.  Otherwise
    the original text is returned unchanged (safe default / idempotent).
    """
    if not text or not isinstance(text, str):
        return text or ""
    stripped = text.strip()
    if not stripped:
        return ""

    data = _try_extract_json_object(stripped)
    if data is None:
        return stripped

    for predicate, extractor in _JSON_PATTERNS:
        if predicate(data):
            result = extractor(data)
            return result if result else ""

    return stripped


# Legacy aliases kept for call-sites that import by the old name.
parse_clarify_json = _try_extract_json_object  # broader; callers check key
clarify_user_visible_text = normalize_llm_visible_content


def split_aimessage_thinking_and_visible(msg: AIMessage) -> tuple[str, str]:
    """Split AIMessage into chain-of-thought vs visible text."""
    thinking_parts: list[str] = []
    text_parts: list[str] = []

    additional = getattr(msg, "additional_kwargs", None) or {}
    if isinstance(additional, dict):
        rk = additional_kwargs_reasoning_text(additional)
        if rk:
            thinking_parts.append(rk)

    content = getattr(msg, "content", None)
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "thinking":
                thinking_parts.append(str(block.get("thinking", "")))
            elif block.get("type") == "reasoning":
                rr = reasoning_text_from_reasoning_block(block)
                if rr:
                    thinking_parts.append(rr)
            elif block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("thought") is True:
                thinking_parts.append(str(block.get("text", "")))
            elif "text" in block:
                text_parts.append(str(block.get("text", "")))

    return ("".join(thinking_parts).strip(), "".join(text_parts).strip())


def aimessage_to_handoff_plain_text(msg: AIMessage) -> str:
    """Thinking + visible text for parent ``ToolMessage`` (no extra LLM)."""
    thinking, text = split_aimessage_thinking_and_visible(msg)
    parts = [p for p in (thinking, text) if p]
    return "\n\n".join(parts).strip()


def content_blocks_to_plain_text(content: Any) -> str:
    """Normalize ``content`` (str, block list, or dict) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        thinking_blocks: list[str] = []
        text_blocks: list[str] = []
        other: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    other.append(item)
                continue
            if isinstance(item, dict):
                typ = item.get("type")
                if typ == "thinking":
                    th = item.get("thinking")
                    if isinstance(th, str) and th.strip():
                        thinking_blocks.append(th)
                    continue
                if typ == "text":
                    tx = item.get("text")
                    if isinstance(tx, str) and tx.strip():
                        text_blocks.append(tx)
                    continue
                text = item.get("text")
                if isinstance(text, str) and text:
                    other.append(text)
                    continue
                nested = item.get("content")
                if isinstance(nested, str) and nested:
                    other.append(nested)
        chunks: list[str] = []
        if thinking_blocks:
            chunks.append("\n\n".join(thinking_blocks))
        if text_blocks:
            chunks.append("\n\n".join(text_blocks))
        if other:
            chunks.append("\n".join(other))
        return "\n\n".join(chunks).strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        nested = content.get("content")
        if isinstance(nested, str):
            return nested
    return str(content)
