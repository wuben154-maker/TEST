"""Normalized session language and prompt blocks for open_deep_research nodes.

Reads the same configurable keys as SubAgentMiddleware (subagent_response_language,
sse_ui_language) so supervisor / researcher / compression / final report stay aligned.
"""

from __future__ import annotations


def normalize_research_response_language(raw: str | None) -> str:
    """Map raw locale string to en | zh | zh-hant | ja | ko (mirrors subagents middleware)."""
    if not raw:
        return "en"
    s = str(raw).strip().lower()
    if s.startswith("zh-hant") or s in {"zh-tw", "zh-hk", "zh_tw"}:
        return "zh-hant"
    base = s.split("-", 1)[0]
    if base == "zh":
        return "zh"
    if base in {"ja", "jp"}:
        return "ja"
    if base in {"ko", "kr"}:
        return "ko"
    if base == "en":
        return "en"
    return "en"


def research_prompt_language_block(lang: str) -> str:
    """English XML-tagged block injected at the top of every deep-research LLM prompt."""
    code = normalize_research_response_language(lang)
    if code == "zh":
        return (
            "<OutputLanguage>\n"
            "The user's session language is **Simplified Chinese (简体中文)**.\n"
            "- Write every user-visible natural-language string in this step in **Simplified Chinese**: "
            "including JSON string values (`question`, `verification`, `research_brief`), "
            "tool arguments meant for the user, `think_tool` reflections, compressed findings prose, "
            "and final report body text. Do not switch to English unless the user explicitly asked.\n"
            "- Keep URLs, code, IOCs, proper names, and quoted source excerpts in their original form.\n"
            "- When a system rule requires a fixed English heading line (e.g. SM_SUBAGENT markers), "
            "keep that line verbatim; all other prose must be Chinese.\n"
            "</OutputLanguage>\n"
        )
    if code == "zh-hant":
        return (
            "<OutputLanguage>\n"
            "The user's session language is **Traditional Chinese (繁體中文)**.\n"
            "- Write all user-visible natural language in this step in **Traditional Chinese**, "
            "including JSON string values (`question`, `verification`, `research_brief`), "
            "tool arguments, `think_tool` text, compressed findings, and report bodies.\n"
            "- Keep URLs, code, IOCs, proper names, and quoted excerpts as-is.\n"
            "- Keep required fixed English heading lines verbatim; all other prose in Traditional Chinese.\n"
            "</OutputLanguage>\n"
        )
    if code == "ja":
        return (
            "<OutputLanguage>\n"
            "The user's session language is **Japanese**.\n"
            "- Write all user-visible natural language in **Japanese** for this step, including "
            "JSON string values, tool arguments, `think_tool` text, compressed findings, and report bodies.\n"
            "- Keep URLs, code, IOCs, proper names, and quoted excerpts as-is.\n"
            "- Keep required fixed English heading lines verbatim.\n"
            "</OutputLanguage>\n"
        )
    if code == "ko":
        return (
            "<OutputLanguage>\n"
            "The user's session language is **Korean**.\n"
            "- Write all user-visible natural language in **Korean** for this step, including "
            "JSON string values, tool arguments, `think_tool` text, compressed findings, and report bodies.\n"
            "- Keep URLs, code, IOCs, proper names, and quoted excerpts as-is.\n"
            "- Keep required fixed English heading lines verbatim.\n"
            "</OutputLanguage>\n"
        )
    return (
        "<OutputLanguage>\n"
        "The user's session language is **English**.\n"
        "- Write all user-visible natural language in **English** for this step, including "
        "JSON string values, tool arguments, `think_tool` text, compressed findings, and report bodies.\n"
        "- Keep URLs, code, IOCs, proper names, and non-English quoted excerpts as needed.\n"
        "- Keep required fixed English heading lines verbatim.\n"
        "</OutputLanguage>\n"
    )
