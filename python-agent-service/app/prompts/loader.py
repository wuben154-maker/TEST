"""Prompt loading utilities.

This module provides functions to load prompts from .md files,
following the same pattern as the skills loader.
"""

import re
from pathlib import Path

import yaml

PROMPTS_DIR = Path(__file__).parent


def parse_prompt_md(content: str) -> tuple[dict, str]:
    """Parse a prompt .md file into frontmatter and body.

    Args:
        content: Full .md file content

    Returns:
        Tuple of (frontmatter_dict, markdown_body)
    """
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)

    if match:
        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)
        return frontmatter or {}, body.strip()

    return {}, content.strip()


def load_prompt(name: str) -> str:
    """Load a prompt from a .md file.

    Args:
        name: Prompt name (without extension), e.g., "MASTER_AGENT"

    Returns:
        The prompt body content
    """
    prompt_file = PROMPTS_DIR / f"{name}.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    content = prompt_file.read_text(encoding="utf-8")
    _, body = parse_prompt_md(content)

    return body


def load_prompt_with_metadata(name: str) -> tuple[dict, str]:
    """Load a prompt with its metadata.

    Args:
        name: Prompt name (without extension)

    Returns:
        Tuple of (metadata_dict, prompt_body)
    """
    prompt_file = PROMPTS_DIR / f"{name}.md"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    content = prompt_file.read_text(encoding="utf-8")
    return parse_prompt_md(content)


# Load master agent prompt
MASTER_SYSTEM_PROMPT = load_prompt("MASTER_AGENT")


__all__ = [
    "load_prompt",
    "load_prompt_with_metadata",
    "parse_prompt_md",
    "MASTER_SYSTEM_PROMPT",
]
