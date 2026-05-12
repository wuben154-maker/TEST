"""Skills directory integrity tests (C8 · ADR-15 · NFR-14).

Validates that ``examples/binary_analysis/skills/`` is discoverable by the
upstream ``deepagents.middleware.skills`` Progressive Disclosure machinery
with zero project-side reinvention (per ADR-14):

- ``_list_skills`` returns the active E2E-01 / E2E-02 skill set (flat
  ``skills/`` root only; see ``skills/_archive/README.md`` for skills excluded
  from discovery).
- Every returned ``SkillMetadata.name`` passes ``_validate_skill_name``, i.e.
  lowercase alphanumeric + single hyphens AND matches its parent directory
  name (Agent Skills spec compliance).
- The three Proto skills (``binary-analysis-e2e-orchestrator``,
  ``binary-analysis-evidence-chain-protocol``,
  ``binary-analysis-sanitize-untrusted-strings``) are present so that the
  Agent System Prompt can rely on them in downstream batches (C14).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import (
    SkillMetadata,
    _list_skills,
    _validate_skill_name,
)

SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
"""Absolute path to ``examples/binary_analysis/skills/``."""

PROTO_SKILLS: tuple[str, ...] = (
    "binary-analysis-e2e-orchestrator",
    "binary-analysis-evidence-chain-protocol",
    "binary-analysis-sanitize-untrusted-strings",
)
"""Project-written protocol skills introduced in batch C8 (DESIGN §9.3)."""

DOCUMENT_WORKFLOW_SKILLS: dict[str, tuple[str, ...]] = {
    "analyzing-macro-malware-in-office-documents": (
        "office",
        "document_extract",
        "vba",
    ),
    "analyzing-pdf-malware-with-pdfid": (
        "pdf",
        "document_extract",
        "/openaction",
    ),
}
"""E2E-02 document workflows restored to active discovery."""

DOCUMENT_ORCHESTRATOR_REQUIRED_READS: dict[str, tuple[str, ...]] = {
    "FR-06": (
        "/subagent-skills/binary-analysis/binary-analysis-ioc-extraction-workflow/SKILL.md",
        "/subagent-skills/binary-analysis/binary-analysis-sanitize-untrusted-strings/SKILL.md",
    ),
    "FR-08": (
        "/subagent-skills/binary-analysis/binary-analysis-evidence-chain-protocol/SKILL.md",
        "/subagent-skills/binary-analysis/binary-analysis-sanitize-untrusted-strings/SKILL.md",
    ),
    "FR-09": (
        "/subagent-skills/binary-analysis/binary-analysis-evidence-chain-protocol/SKILL.md",
    ),
}
"""Stage-gated skill reads that must remain explicit for Progressive Disclosure."""

MIN_SKILL_COUNT = 38
"""Active skills under ``skills/`` after 2026-04-23 batch S-02 added
``ghidra-priority-queue-workflow`` (37 → 38). Prior baseline 37 was set on
2026-04-21 by the ``_archive/`` move (from 54)."""

ARCHIVED_SKILL_DIRS: frozenset[str] = frozenset(
    {
        "analyzing-android-malware-with-apktool",
        "analyzing-heap-spray-exploitation",
        "analyzing-malicious-pdf-with-peepdf",
        "analyzing-malware-behavior-with-cuckoo-sandbox",
        "analyzing-memory-dumps-with-volatility",
        "analyzing-network-traffic-of-malware",
        "analyzing-supply-chain-malware-artifacts",
        "deobfuscating-javascript-malware",
        "deobfuscating-powershell-obfuscated-malware",
        "detecting-rootkit-activity",
        "performing-automated-malware-analysis-with-cape",
        "performing-dynamic-analysis-with-any-run",
        "performing-firmware-malware-analysis",
        "performing-memory-forensics-with-volatility3-plugins",
        "reverse-engineering-android-malware-with-jadx",
    }
)
"""Vendor-in skills parked under ``skills/_archive/`` — excluded from ``_list_skills``."""


@pytest.fixture(scope="module")
def loaded_skills() -> list[SkillMetadata]:
    """Return ``SkillMetadata`` entries discovered under ``skills/``.

    Uses the real ``FilesystemBackend`` + ``_list_skills`` to exercise the
    exact Progressive Disclosure code path that runs in production.
    """
    backend = FilesystemBackend(root_dir=str(SKILLS_DIR.parent), virtual_mode=False)
    return _list_skills(backend, source_path=str(SKILLS_DIR))


class TestDirectoryLayout:
    """ADR-15 v0.5 single flat directory integrity."""

    def test_skills_directory_exists(self):
        assert SKILLS_DIR.is_dir(), f"missing skills directory: {SKILLS_DIR}"

    def test_changelog_present(self):
        changelog = SKILLS_DIR / "CHANGELOG.md"
        assert changelog.is_file(), (
            "skills/CHANGELOG.md is expected as the initial audit anchor "
            "(ADR-15 §9.5.4 · v0.7: optional engineering practice — writing "
            "new entries is recommended, not required, but keep the file as "
            "the starting reference point)"
        )


class TestSkillsInventory:
    """NFR-14 · SkillsMiddleware must load the full flat directory."""

    def test_returns_at_least_min_skills(
        self, loaded_skills: list[SkillMetadata]
    ) -> None:
        assert len(loaded_skills) >= MIN_SKILL_COUNT, (
            f"expected >= {MIN_SKILL_COUNT} active skills under skills/, "
            f"got {len(loaded_skills)}: {[s['name'] for s in loaded_skills]}"
        )

    def test_archived_skills_not_listed(
        self, loaded_skills: list[SkillMetadata]
    ) -> None:
        names = {skill["name"] for skill in loaded_skills}
        overlap = names & ARCHIVED_SKILL_DIRS
        assert not overlap, f"archived skills must not appear in metadata: {overlap}"

    def test_archive_readme_documents_restore(self) -> None:
        readme = SKILLS_DIR / "_archive" / "README.md"
        assert readme.is_file(), f"missing archive readme: {readme}"
        text = readme.read_text(encoding="utf-8")
        assert "git mv" in text
        assert "performing-dynamic-analysis-with-any-run" in text

    def test_every_name_matches_directory(
        self, loaded_skills: list[SkillMetadata]
    ) -> None:
        for skill in loaded_skills:
            directory_name = Path(skill["path"]).parent.name
            is_valid, error = _validate_skill_name(skill["name"], directory_name)
            assert is_valid, f"invalid skill name for {skill['path']}: {error}"

    def test_all_proto_skills_loaded(
        self, loaded_skills: list[SkillMetadata]
    ) -> None:
        names = {skill["name"] for skill in loaded_skills}
        missing = set(PROTO_SKILLS) - names
        assert not missing, f"missing Proto skills: {sorted(missing)}"

    def test_proto_skills_have_descriptions(
        self, loaded_skills: list[SkillMetadata]
    ) -> None:
        """FR-09 · ``description`` drives the LLM's skill selection."""
        proto = {s["name"]: s for s in loaded_skills if s["name"] in PROTO_SKILLS}
        for name in PROTO_SKILLS:
            assert name in proto, f"proto skill not loaded: {name}"
            assert proto[name]["description"].strip(), (
                f"proto skill {name} has empty description"
            )

    @pytest.mark.parametrize(
        ("skill_name", "keywords"),
        list(DOCUMENT_WORKFLOW_SKILLS.items()),
    )
    def test_document_workflow_skills_loaded(
        self,
        loaded_skills: list[SkillMetadata],
        skill_name: str,
        keywords: tuple[str, ...],
    ) -> None:
        """E2E-02 document workflows must remain active and discoverable."""
        target = next(
            (skill for skill in loaded_skills if skill["name"] == skill_name),
            None,
        )
        assert target is not None, f"document workflow skill not loaded: {skill_name}"

        description = target["description"].lower()
        missing = [kw for kw in keywords if kw not in description]
        assert not missing, (
            f"{skill_name} description missing trigger keywords {missing}; "
            f"got: {target['description']!r}"
        )


class TestProtoFrontmatter:
    """FR-08 · Proto SKILL.md YAML frontmatter must be ``yaml.safe_load``-able."""

    @pytest.mark.parametrize("skill_name", PROTO_SKILLS)
    def test_frontmatter_parses(self, skill_name: str) -> None:
        skill_path = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_path.is_file(), f"missing: {skill_path}"

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


class TestDocumentOrchestratorStageGates:
    """E2E-02 stage gates must force full SKILL.md reads before dependent work."""

    @pytest.mark.parametrize(
        ("stage", "required_paths"),
        list(DOCUMENT_ORCHESTRATOR_REQUIRED_READS.items()),
    )
    def test_required_skill_reads_are_explicit(
        self,
        stage: str,
        required_paths: tuple[str, ...],
    ) -> None:
        skill_path = SKILLS_DIR / "document-analysis-e2e-orchestrator" / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")

        assert f"Required skill reads before {stage}" in text
        for path in required_paths:
            assert f"Read `{path}`" in text
