"""Official SubAgent specs for create_deep_agent.

Registry-only: ``config/subagents.registry.yaml`` plus bundles under
``subagents/official/<id>/`` (``AGENT.md``, ``skills/<package>/SKILL.md``).
"""

from __future__ import annotations

from typing import Any, Callable

from app.agents.subagent_registry import build_subagent_specs_from_registry


def build_subagent_specs(
    backend_factory: Callable[[Any], Any] | None = None,
    default_subagent_model: Any | None = None,
) -> list[dict[str, Any]]:
    """Build SubAgent spec dicts for create_deep_agent from the YAML registry."""
    return build_subagent_specs_from_registry(
        backend_factory=backend_factory,
        default_subagent_model=default_subagent_model,
    )
