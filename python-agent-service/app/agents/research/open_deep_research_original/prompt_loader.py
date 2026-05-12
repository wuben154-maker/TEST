"""Load deep-research prompt templates from ``prompt_md/*.md``."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompt_md"


def load_deep_research_prompt(stem: str) -> str:
    """Return UTF-8 text of ``prompt_md/{stem}.md`` (trailing newline stripped for stable .format)."""
    path = _PROMPTS_DIR / f"{stem}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Deep research prompt not found: {path}")
    return path.read_text(encoding="utf-8")
