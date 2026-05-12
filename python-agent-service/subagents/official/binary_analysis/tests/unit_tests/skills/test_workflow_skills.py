"""Workflow skills integrity tests (C10 · Workflow-01/02 · DESIGN §9.5.2).

Validates that the two project-written workflow skills introduced in batch
C10 are discovered by the upstream ``deepagents.middleware.skills`` Progressive
Disclosure machinery with zero project-side reinvention (per ADR-14):

- ``_list_skills`` returns both workflow skills.
- ``SkillMetadata.name`` matches the parent directory name (Agent Skills
  spec compliance + ``_validate_skill_name`` rules).
- Each SKILL.md's YAML frontmatter is ``yaml.safe_load``-able and declares
  ``name`` and ``description``.
- Each ``description`` carries the trigger keywords that drive LLM skill
  selection at runtime (so the Agent activates the workflow on the right
  FR-06 / FR-13 prompts).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import (
    _list_skills,
    _validate_skill_name,
)

SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
"""Absolute path to ``examples/binary_analysis/skills/``."""

WORKFLOW_SKILLS: dict[str, tuple[str, ...]] = {
    "binary-analysis-ioc-extraction-workflow": (
        "ioc",
        "floss",
        "strings_iocs",
        "defang",
    ),
    "binary-analysis-family-triage-workflow": (
        "family",
        "cobalt strike",
        "agent tesla",
        "ransomware",
        "llm_inferences",
    ),
}
"""Workflow skill directory name -> lowercase trigger keywords that MUST appear
in ``description`` so the Agent LLM activates the workflow for the right
prompts.

Per DESIGN §9.5.2 (batch C10): Workflow-01 wraps FR-06 IOC extraction (upstream
``extracting-iocs-from-malware-samples`` + ``performing-malware-ioc-extraction``
+ Proto-03 sanitisation) writing facts into ``strings_iocs``; Workflow-02 wraps
FR-13 family triage (malpedia + family specialists) writing inferences into
``llm_inferences``.
"""


@pytest.fixture(scope="module")
def loaded_skills() -> list[dict]:
    """Return ``SkillMetadata`` entries discovered under ``skills/``.

    Uses the real ``FilesystemBackend`` + ``_list_skills`` so this test
    exercises the exact Progressive Disclosure code path that runs in
    production.
    """
    backend = FilesystemBackend(root_dir=str(SKILLS_DIR.parent), virtual_mode=False)
    return _list_skills(backend, source_path=str(SKILLS_DIR))


class TestWorkflowSkillsDiscovered:
    """C10-AC3 · ``_list_skills`` must return both workflow skills."""

    @pytest.mark.parametrize("skill_name", list(WORKFLOW_SKILLS))
    def test_skill_md_present(self, skill_name: str) -> None:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_md.is_file(), f"missing: {skill_md}"

    def test_all_workflow_skills_loaded(self, loaded_skills: list[dict]) -> None:
        names = {skill["name"] for skill in loaded_skills}
        missing = set(WORKFLOW_SKILLS) - names
        assert not missing, f"missing workflow skills: {sorted(missing)}"

    def test_workflow_skill_names_match_directory(
        self, loaded_skills: list[dict]
    ) -> None:
        for skill in loaded_skills:
            if skill["name"] not in WORKFLOW_SKILLS:
                continue
            directory_name = Path(skill["path"]).parent.name
            is_valid, error = _validate_skill_name(skill["name"], directory_name)
            assert is_valid, f"invalid skill name for {skill['path']}: {error}"


class TestWorkflowFrontmatter:
    """C10-AC3 · SKILL.md YAML frontmatter must be ``yaml.safe_load``-able."""

    @pytest.mark.parametrize("skill_name", list(WORKFLOW_SKILLS))
    def test_frontmatter_parses(self, skill_name: str) -> None:
        skill_path = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        assert content.startswith("---\n"), (
            f"{skill_path} must begin with YAML frontmatter delimiter"
        )

        _, frontmatter_block, _ = content.split("---\n", 2)
        data = yaml.safe_load(frontmatter_block)

        assert isinstance(data, dict), "frontmatter must be a YAML mapping"
        assert data.get("name") == skill_name, (
            f"frontmatter name must equal directory name ({skill_name})"
        )
        assert data.get("description"), "description is required"


class TestWorkflowDescriptionTriggers:
    """C10-AC3 · ``description`` must carry trigger keywords (LLM activation)."""

    @pytest.mark.parametrize(
        ("skill_name", "keywords"),
        list(WORKFLOW_SKILLS.items()),
    )
    def test_description_contains_trigger_keywords(
        self,
        loaded_skills: list[dict],
        skill_name: str,
        keywords: tuple[str, ...],
    ) -> None:
        target = next(
            (skill for skill in loaded_skills if skill["name"] == skill_name),
            None,
        )
        assert target is not None, f"skill not loaded: {skill_name}"

        description = target["description"].lower()
        missing = [kw for kw in keywords if kw not in description]
        assert not missing, (
            f"{skill_name} description missing trigger keywords {missing}; "
            f"got: {target['description']!r}"
        )
