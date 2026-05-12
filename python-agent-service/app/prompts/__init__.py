"""Prompts package.

This package provides prompt management for the security agent system.
- Master agent prompt: MASTER_AGENT.md
- Sub-agent skills: loaded from skills/ directory via SKILL.md files
"""

from .loader import (
    MASTER_SYSTEM_PROMPT,
    load_prompt,
    load_prompt_with_metadata,
)
from .skills import (
    get_skill_registry,
    get_skill,
    get_all_skills,
    find_skill_for_query,
    get_skill_for_input_type,
    INPUT_TYPE_TO_SKILL,
)

__all__ = [
    # Master prompt
    "MASTER_SYSTEM_PROMPT",
    "load_prompt",
    "load_prompt_with_metadata",
    # Skills
    "get_skill_registry",
    "get_skill",
    "get_all_skills",
    "find_skill_for_query",
    "get_skill_for_input_type",
    "INPUT_TYPE_TO_SKILL",
]
