"""Skill Loader - Load skills from SKILL.md files.

This module implements the Anthropic Skills pattern for loading skills
from filesystem-based SKILL.md files with YAML frontmatter.
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import Any

from .base import SkillSpec, SkillMetadata, SkillInstructions, WorkflowStep


logger = logging.getLogger(__name__)


def _find_skills_dir() -> Path:
    """Find the skills directory, trying multiple possible locations.
    
    This handles different deployment scenarios where the working directory
    may differ from development.
    """
    # Try relative to this file (development mode)
    relative_path = Path(__file__).parent.parent.parent.parent / "skills"
    if relative_path.exists():
        logger.info(f"Found skills dir relative to file: {relative_path}")
        return relative_path
    
    # Try from current working directory
    cwd_path = Path.cwd() / "skills"
    if cwd_path.exists():
        logger.info(f"Found skills dir in cwd: {cwd_path}")
        return cwd_path
    
    # Try from SKILLS_DIR environment variable
    env_path = os.environ.get("SKILLS_DIR")
    if env_path:
        env_skills_path = Path(env_path)
        if env_skills_path.exists():
            logger.info(f"Found skills dir from env: {env_skills_path}")
            return env_skills_path
    
    # Try common deployment paths
    common_paths = [
        Path("/app/skills"),
        Path("/python-agent-service/skills"),
        Path("./python-agent-service/skills"),
    ]
    for path in common_paths:
        if path.exists():
            logger.info(f"Found skills dir at common path: {path}")
            return path
    
    # Fallback - return the relative path even if it doesn't exist
    logger.warning(f"Skills directory not found. Tried: {relative_path}, {cwd_path}, env={env_path}, common paths")
    return relative_path


SKILLS_DIR = _find_skills_dir()


def parse_skill_md(content: str) -> tuple[dict, str]:
    """Parse SKILL.md file content into frontmatter and body.
    
    Args:
        content: Full SKILL.md file content
        
    Returns:
        Tuple of (frontmatter_dict, markdown_body)
    """
    # Match YAML frontmatter
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)
    
    if match:
        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)
        return frontmatter, body
    
    return {}, content


def load_skill_from_file(skill_path: Path) -> SkillSpec | None:
    """Load a skill from a SKILL.md file.
    
    Args:
        skill_path: Path to skill directory containing SKILL.md
        
    Returns:
        SkillSpec or None if loading fails
    """
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return None
    
    try:
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = parse_skill_md(content)
        
        metadata = SkillMetadata(
            name=frontmatter.get("name", skill_path.name),
            display_name=frontmatter.get("display_name", skill_path.name),
            description=frontmatter.get("description", ""),
            triggers=frontmatter.get("triggers", []),
            tags=frontmatter.get("tags", []),
            priority=frontmatter.get("priority", 0),
            version=frontmatter.get("version", "1.0.0"),
        )
        
        instructions = SkillInstructions(system_prompt=body.strip())
        
        # Parse workflow_steps from frontmatter
        workflow_steps = []
        raw_steps = frontmatter.get("workflow_steps", [])
        for step_data in raw_steps:
            if isinstance(step_data, dict):
                workflow_steps.append(WorkflowStep(
                    id=step_data.get("id", ""),
                    label=step_data.get("label", ""),
                    tool=step_data.get("tool"),
                    description=step_data.get("description", ""),
                    required=step_data.get("required", True),
                    tool_args_template=step_data.get("tool_args", {}),
                ))
        
        # Find associated scripts
        scripts_dir = skill_path / "scripts"
        resources = list(scripts_dir.glob("*.py")) if scripts_dir.exists() else []
        
        return SkillSpec(
            metadata=metadata,
            instructions=instructions,
            workflow_steps=workflow_steps,
            resources=resources,
            max_iterations=frontmatter.get("max_iterations", 10),
            timeout_seconds=frontmatter.get("timeout_seconds", 120),
        )
    except Exception as e:
        print(f"Error loading skill from {skill_path}: {e}")
        return None


def discover_skills(skills_dir: Path | None = None) -> list[SkillSpec]:
    """Discover all skills from the skills directory.
    
    Args:
        skills_dir: Directory containing skill folders
        
    Returns:
        List of discovered SkillSpec objects
    """
    if skills_dir is None:
        skills_dir = SKILLS_DIR
    
    logger.info(f"Discovering skills from: {skills_dir} (exists: {skills_dir.exists()})")
    
    if not skills_dir.exists():
        logger.warning(f"Skills directory does not exist: {skills_dir}")
        return []
    
    skills = []
    try:
        for item in skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill = load_skill_from_file(item)
                if skill:
                    logger.info(f"Loaded skill: {skill.name}")
                    skills.append(skill)
    except Exception as e:
        logger.error(f"Error discovering skills: {e}")
    
    logger.info(f"Discovered {len(skills)} skills: {[s.name for s in skills]}")
    return skills


def get_skill_frontmatter(skill_path: Path) -> dict[str, Any] | None:
    """Get only the frontmatter (metadata) from a skill - for token efficiency.
    
    Args:
        skill_path: Path to skill directory
        
    Returns:
        Frontmatter dictionary or None
    """
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return None
    
    try:
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, _ = parse_skill_md(content)
        return frontmatter
    except Exception:
        return None
