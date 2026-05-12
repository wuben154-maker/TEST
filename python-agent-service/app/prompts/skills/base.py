"""Skill Specification - Based on LangChain DeepAgents and Anthropic Skills.

This module implements the skill pattern from:
- Anthropic's agent skills: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world
- LangChain DeepAgents: https://blog.langchain.com/using-skills-with-deep-agents/

Key principles:
1. Progressive Disclosure - Only load full skill content when needed
2. Token Efficiency - YAML frontmatter loads by default, full instructions on-demand
3. Dynamic Discovery - Skills can be discovered and loaded at runtime
4. Composability - Multiple skills can be combined in a session
"""

from dataclasses import dataclass, field
from typing import Sequence, Callable, Any, Optional
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool


@dataclass
class WorkflowStep:
    """A single step in a skill's workflow with optional tool binding.
    
    This allows SKILL.md to define structured workflows where each step
    can be mapped to a specific tool for execution.
    """
    id: str                          # Unique step identifier (e.g., "parse_headers")
    label: str                       # Display label (e.g., "解析邮件头 / Parse Headers")
    tool: Optional[str] = None       # Tool name to execute (None = LLM analysis only)
    description: str = ""            # Detailed description of what this step does
    required: bool = True            # Whether this step is required
    tool_args_template: dict = field(default_factory=dict)  # Default args for the tool
    
    def get_label(self, language: str = "en") -> str:
        """Get localized label."""
        if " / " in self.label:
            parts = self.label.split(" / ")
            if language == "zh":
                return parts[0]
            return parts[-1]
        return self.label
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "tool": self.tool,
            "description": self.description,
            "required": self.required,
        }


@dataclass
class SkillMetadata:
    """Skill metadata (equivalent to YAML frontmatter in SKILL.md).
    
    This is loaded by default for all skills - lightweight summary for discovery.
    """
    name: str
    display_name: str
    description: str  # Brief description for agent selection
    triggers: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    priority: int = 0
    version: str = "1.0.0"
    author: str = "system"
    
    def to_frontmatter(self) -> str:
        """Generate YAML-like frontmatter string."""
        triggers_str = ", ".join(f'"{t}"' for t in self.triggers)
        tags_str = ", ".join(f'"{t}"' for t in self.tags)
        return f"""---
name: {self.name}
display_name: {self.display_name}
description: {self.description}
triggers: [{triggers_str}]
tags: [{tags_str}]
priority: {self.priority}
version: {self.version}
---"""


@dataclass
class SkillInstructions:
    """Skill instructions (equivalent to Markdown content in SKILL.md).
    
    This is loaded on-demand when the skill is actually used.
    Follows progressive disclosure pattern for token efficiency.
    """
    system_prompt: str
    examples: list[str] = field(default_factory=list)
    workflow: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    output_format: str = ""
    
    def get_full_prompt(self) -> str:
        """Get the full system prompt with all instructions."""
        return self.system_prompt


@dataclass
class SkillSpec:
    """Complete skill specification for a sub-agent.
    
    Based on the skill pattern from LangChain DeepAgents where:
    - Skills are progressively disclosed (metadata first, full content on-demand)
    - Skills can be dynamically discovered and loaded
    - Skills are composable within sessions
    
    Structure mirrors SKILL.md files:
    - metadata: YAML frontmatter (always loaded, used for discovery)
    - instructions: Markdown content (loaded on-demand when skill is used)
    - workflow_steps: Structured SOP with tool bindings
    - tools: Additional tools specific to this skill
    - resources: Associated files, scripts, or documents
    
    Attributes:
        metadata: Skill metadata for discovery and selection.
        instructions: Detailed instructions loaded on-demand.
        workflow_steps: Structured workflow with tool bindings for step-by-step execution.
        tools: Additional tools specific to this skill.
        resources: Paths to associated files (scripts, docs, etc).
        model: Optional specific model for this skill.
        max_iterations: Maximum tool-calling iterations.
        timeout_seconds: Maximum execution time.
    """
    
    metadata: SkillMetadata
    instructions: SkillInstructions
    workflow_steps: list[WorkflowStep] = field(default_factory=list)
    tools: Sequence[BaseTool | Callable] = field(default_factory=list)
    resources: list[Path] = field(default_factory=list)
    model: BaseChatModel | None = None
    max_iterations: int = 10
    timeout_seconds: int = 120
    
    # Cached state
    _loaded: bool = field(default=False, repr=False)
    
    # Convenience properties for backward compatibility
    @property
    def name(self) -> str:
        return self.metadata.name
    
    @property
    def display_name(self) -> str:
        return self.metadata.display_name
    
    @property
    def description(self) -> str:
        return self.metadata.description
    
    @property
    def triggers(self) -> list[str]:
        return self.metadata.triggers
    
    @property
    def priority(self) -> int:
        return self.metadata.priority
    
    @property
    def system_prompt(self) -> str:
        """Get full system prompt (loads instructions if needed)."""
        return self.instructions.get_full_prompt()
    
    def get_summary(self) -> str:
        """Get lightweight summary for agent selection (metadata only)."""
        return f"{self.display_name}: {self.description}"
    
    def get_frontmatter(self) -> str:
        """Get YAML frontmatter representation."""
        return self.metadata.to_frontmatter()
    
    def matches(self, query: str) -> bool:
        """Check if query matches any trigger patterns."""
        query_lower = query.lower()
        return any(trigger.lower() in query_lower for trigger in self.triggers)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "triggers": self.triggers,
            "tags": self.metadata.tags,
            "priority": self.priority,
            "version": self.metadata.version,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
        }
    
    def to_skill_md(self) -> str:
        """Generate SKILL.md compatible content."""
        return f"""{self.get_frontmatter()}

# {self.display_name}

{self.description}

## Instructions

{self.system_prompt}
"""


class SkillRegistry:
    """Registry for discovering and managing skills.
    
    Implements the dynamic discovery pattern from DeepAgents:
    - Skills are discovered at startup
    - Metadata is loaded for all skills (lightweight)
    - Full instructions are loaded on-demand
    """
    
    def __init__(self):
        self._skills: dict[str, SkillSpec] = {}
        self._by_tag: dict[str, list[str]] = {}
    
    def register(self, skill: SkillSpec) -> None:
        """Register a skill."""
        self._skills[skill.name] = skill
        
        # Index by tags
        for tag in skill.metadata.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            self._by_tag[tag].append(skill.name)
    
    def get(self, name: str) -> SkillSpec | None:
        """Get a skill by name."""
        return self._skills.get(name)
    
    def list_skills(self) -> list[SkillSpec]:
        """List all registered skills."""
        return list(self._skills.values())
    
    def list_summaries(self) -> list[str]:
        """List skill summaries (metadata only, token efficient)."""
        return [skill.get_summary() for skill in self._skills.values()]
    
    def find_by_tag(self, tag: str) -> list[SkillSpec]:
        """Find skills by tag."""
        skill_names = self._by_tag.get(tag, [])
        return [self._skills[name] for name in skill_names if name in self._skills]
    
    def find_by_query(self, query: str) -> list[tuple[int, SkillSpec]]:
        """Find skills matching a query, sorted by priority."""
        matches = []
        for skill in self._skills.values():
            if skill.matches(query):
                matches.append((skill.priority, skill))
        
        # Sort by priority (descending)
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches
    
    def get_best_match(self, query: str) -> SkillSpec | None:
        """Get the best matching skill for a query."""
        matches = self.find_by_query(query)
        return matches[0][1] if matches else None


# Helper function to create skills with less boilerplate
def create_skill(
    name: str,
    display_name: str,
    description: str,
    system_prompt: str,
    triggers: list[str] | None = None,
    tags: list[str] | None = None,
    tools: Sequence[BaseTool | Callable] | None = None,
    priority: int = 0,
    max_iterations: int = 10,
    timeout_seconds: int = 120,
) -> SkillSpec:
    """Create a SkillSpec with sensible defaults."""
    return SkillSpec(
        metadata=SkillMetadata(
            name=name,
            display_name=display_name,
            description=description,
            triggers=triggers or [],
            tags=tags or [],
            priority=priority,
        ),
        instructions=SkillInstructions(
            system_prompt=system_prompt,
        ),
        tools=tools or [],
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
    )
