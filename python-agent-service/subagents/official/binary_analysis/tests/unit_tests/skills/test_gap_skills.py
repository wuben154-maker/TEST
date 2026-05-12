"""Gap skills integrity tests (C9 · Gap-01/02/03/04 · DESIGN §9.3).

Validates that the four project-written gap-fill skills introduced in batch
C9 are discovered by the upstream ``deepagents.middleware.skills`` Progressive
Disclosure machinery with zero project-side reinvention (per ADR-14):

- ``_list_skills`` returns each of the four gap skills.
- ``SkillMetadata.name`` matches the parent directory name (Agent Skills
  spec compliance + ``_validate_skill_name`` rules).
- Each SKILL.md's YAML frontmatter is ``yaml.safe_load``-able and declares
  ``name`` and ``description``.
- Each ``description`` carries the trigger keywords that drive LLM skill
  selection at runtime (so the Agent activates the skill on the right
  FR-04 / FR-05 / FR-17 prompts).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import (
    _list_skills,
    _validate_skill_name,
)

from schema.indicator import Indicator

SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
"""Absolute path to ``examples/binary_analysis/skills/``."""

GAP_SKILLS: dict[str, tuple[str, ...]] = {
    "analyzing-macho-structure": ("mach-o", "mach header"),
    "pe-structural-anomaly-checklist": (
        "tls callback",
        "overlay",
        "rich header",
    ),
    "detecting-commercial-packers-with-die": (
        "themida",
        "vmprotect",
        "die",
    ),
    "two-phase-behavior-chain-reconstruction": (
        "behavior chain",
        "two-phase",
    ),
    # Batch S-02 (FR-07 priority queue workflow): methodology skill that
    # gates every `analyzeHeadless` invocation on a `decompile_priority`
    # fact (IR-05) and paginated per-function reads (IR-04). Trigger
    # keywords must let the LLM find this skill whenever it is about to
    # drive FR-07 decompilation.
    "ghidra-priority-queue-workflow": (
        "priority",
        "analyzeheadless",
        "decompile_priority",
    ),
    # Batch C10 / Gap-05 (FR-04 ELF structural parity): scope-limited
    # ELF structural-parsing skill that is parity with Gap-01 (Mach-O)
    # and Gap-02 (PE). Trigger keywords drive LLM activation on any
    # FR-04 ELF structural-parsing prompt. The broad upstream skill
    # `analyzing-linux-elf-malware` is re-routed to FR-07 via the
    # orchestrator scope-limiter note; this skill owns FR-04.
    "analyzing-elf-structure": (
        "elf header",
        "program header",
        ".init_array",
        "fr-04",
    ),
}
"""Gap skill directory name -> lowercase trigger keywords that MUST appear in
``description`` so the Agent LLM activates the skill for the right prompts.

Per DESIGN §9.3 (batch C9): Gap-01 (FR-04 Mach-O parity), Gap-02 (FR-04 PE
anomaly checklist), Gap-03 (FR-05 commercial packers), Gap-04 (FR-17 two-phase
behavior chain).

Batch S-02 adds `ghidra-priority-queue-workflow` which wraps FR-07 invocations
under IR-04 / IR-05 / FR-07 AC-7; see `examples/binary_analysis/specs/
e2e01-backend/IMPL-PLAYBOOK.md` → "S-02-fr07-priority-queue".

Batch C10 adds `analyzing-elf-structure` (Gap-05) which fills the FR-04 ELF
structural-parsing gap (IR-09 parity requirement). The broader
`analyzing-linux-elf-malware` skill is re-routed to FR-07 via the
orchestrator's scope-limiter note. Per ADR-15 v0.7 the former "do not edit
upstream body" restriction has been removed; this test only verifies the
FR-04 vs FR-07 workflow split encoded in the orchestrator.
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


class TestGapSkillsDiscovered:
    """C9-AC5 · ``_list_skills`` must return all four gap skills."""

    @pytest.mark.parametrize("skill_name", list(GAP_SKILLS))
    def test_skill_md_present(self, skill_name: str) -> None:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_md.is_file(), f"missing: {skill_md}"

    def test_all_gap_skills_loaded(self, loaded_skills: list[dict]) -> None:
        names = {skill["name"] for skill in loaded_skills}
        missing = set(GAP_SKILLS) - names
        assert not missing, f"missing gap skills: {sorted(missing)}"

    def test_gap_skill_names_match_directory(self, loaded_skills: list[dict]) -> None:
        for skill in loaded_skills:
            if skill["name"] not in GAP_SKILLS:
                continue
            directory_name = Path(skill["path"]).parent.name
            is_valid, error = _validate_skill_name(skill["name"], directory_name)
            assert is_valid, f"invalid skill name for {skill['path']}: {error}"


class TestGapFrontmatter:
    """C9-AC5 · SKILL.md YAML frontmatter must be ``yaml.safe_load``-able."""

    @pytest.mark.parametrize("skill_name", list(GAP_SKILLS))
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


class TestGapDescriptionTriggers:
    """C9-AC5 · ``description`` must carry trigger keywords (LLM activation)."""

    @pytest.mark.parametrize(
        ("skill_name", "keywords"),
        list(GAP_SKILLS.items()),
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


ORCHESTRATOR_SKILL = SKILLS_DIR / "binary-analysis-e2e-orchestrator" / "SKILL.md"
"""Absolute path to the EN orchestrator SKILL.md (Proto-01)."""

class TestElfStructureScopeLimiter:
    """C10-AC1 · Verify the FR-04 / FR-07 scope-limiter for ELF (Gap-05).

    Per ADR-15 v0.7 the "do not edit upstream skill body" restriction has
    been removed — `skills/` is a single flat directory of editable project
    assets. The ELF scope-limiter is now purely a *workflow* contract: the
    orchestrator routes FR-04 to `analyzing-elf-structure` (structural
    parsing) and FR-07 to `analyzing-linux-elf-malware` (full reverse
    engineering). These tests confirm that split:

    1. `analyzing-elf-structure` is referenced in the FR-04 stage block of
       the runtime orchestrator.
    2. `analyzing-linux-elf-malware` is **absent** from the FR-04 stage block
       (the scope-limiter re-routes it to FR-07).
    3. `analyzing-linux-elf-malware` is present in the FR-07 stage block.
    """

    @staticmethod
    def _extract_stage_block(text: str, stage_heading: str) -> str:
        """Return the markdown text from *stage_heading* to the next ``###``."""
        start = text.find(stage_heading)
        if start == -1:
            return ""
        end = text.find("\n### ", start + len(stage_heading))
        return text[start:end] if end != -1 else text[start:]

    def test_elf_structure_in_fr04_runtime_skill(self) -> None:
        text = ORCHESTRATOR_SKILL.read_text(encoding="utf-8")
        fr04 = self._extract_stage_block(text, "### Stage FR-04")
        assert "analyzing-elf-structure" in fr04, (
            "runtime orchestrator FR-04 block must reference `analyzing-elf-structure`"
        )

    def test_linux_elf_malware_absent_from_fr04_runtime_skill(self) -> None:
        text = ORCHESTRATOR_SKILL.read_text(encoding="utf-8")
        fr04 = self._extract_stage_block(text, "### Stage FR-04")
        # The scope-limiter blockquote may *mention* the skill by name to
        # explain why it is excluded — that is expected prose, not a
        # recommendation. We assert it does NOT appear in the recommended-skills
        # bullet list (lines starting with "  - ELF →").
        for line in fr04.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ELF") or stripped.startswith("- ELF →"):
                assert "analyzing-linux-elf-malware" not in stripped, (
                    "runtime orchestrator FR-04 ELF recommended-skills bullet must NOT "
                    "reference `analyzing-linux-elf-malware` (re-routed to FR-07)"
                )

    def test_linux_elf_malware_in_fr07_runtime_skill(self) -> None:
        text = ORCHESTRATOR_SKILL.read_text(encoding="utf-8")
        fr07 = self._extract_stage_block(text, "### Stage FR-07")
        assert "analyzing-linux-elf-malware" in fr07, (
            "runtime orchestrator FR-07 block must reference `analyzing-linux-elf-malware` "
            "(re-routed from FR-04)"
        )

_JSON_FENCE_RE = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)
"""Matches every ```json fenced block in a markdown file.

Non-greedy ``.*?`` plus ``re.DOTALL`` keeps each fence scoped to its
opening / closing pair even when the markdown embeds multiple blocks.
"""

_INDICATOR_ROUTING_KEYS: frozenset[str] = frozenset({"bucket"})
"""Keys that SKILL.md examples add to Indicator payloads for tool routing.

The evidence_chain tool accepts ``bucket`` at the top level of its input
schema (see :class:`~evidence_chain.tool.EvidenceChainInput`),
but ``bucket`` is NOT a field of :class:`Indicator`.  Skill authors tend
to inline it into the example block for clarity; this test strips it
before running ``Indicator.model_validate`` so the skill example is
validated against the *Indicator* schema proper.
"""

_INDICATOR_SHAPE_KEYS: frozenset[str] = frozenset({"indicator_type", "kind"})
"""Minimum key-set that marks a ``json`` block as an Indicator example.

Skill authors also paste raw ``data`` payload snippets and tool-call
request/response examples inside ``json`` fences; those lack both
``indicator_type`` and ``kind`` and are intentionally skipped so this
test focuses strictly on the Indicator contract.
"""


def _iter_json_blocks(markdown_path: Path) -> list[tuple[int, str]]:
    """Yield ``(ordinal, body)`` for every ```json fenced block in a file."""
    text = markdown_path.read_text(encoding="utf-8")
    return list(enumerate(_JSON_FENCE_RE.findall(text)))


class TestSkillIndicatorExamples:
    """Every ``json`` block in ``skills/**/SKILL.md`` whose shape matches an
    Indicator example (``indicator_type`` + ``kind`` keys present) MUST
    round-trip through :meth:`Indicator.model_validate` without error.

    Motivation — prevent schema drift in agent-facing documentation
    (Proto-02 / P1 root cause; see IMPL-PROGRESS "Spec 反馈登记" P1 🔴
    entry): skill examples teach the LLM how to write Indicators.  When
    a skill example uses an obsolete field name (e.g. ``tag``/``value``),
    five-level ``Severity``, or places the record in a bucket that does
    not exist, the LLM mirrors the mistake at runtime and the
    ``evidence_chain`` tool rejects the write.  This suite catches the
    drift at test time instead of at F-manual time.
    """

    def test_at_least_one_indicator_example_exists(self) -> None:
        """Smoke guard: the documentation corpus must contain ≥1 example."""
        total = 0
        for markdown_path in sorted(SKILLS_DIR.glob("**/SKILL.md")):
            if "_archive" in markdown_path.parts:
                continue
            for _, body in _iter_json_blocks(markdown_path):
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and _INDICATOR_SHAPE_KEYS <= set(obj):
                    total += 1
        assert total > 0, (
            "no Indicator-shaped json blocks found under skills/; the "
            "regex pattern or _INDICATOR_SHAPE_KEYS heuristic likely "
            "needs updating"
        )

    def test_every_indicator_example_parses(self) -> None:
        """For every Indicator-shaped ``json`` block, ``Indicator.model_validate``
        must succeed after stripping evidence_chain tool routing keys.
        """
        failures: list[str] = []
        for markdown_path in sorted(SKILLS_DIR.glob("**/SKILL.md")):
            if "_archive" in markdown_path.parts:
                continue
            rel = markdown_path.relative_to(SKILLS_DIR)
            for ordinal, body in _iter_json_blocks(markdown_path):
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError as exc:
                    failures.append(
                        f"{rel}: block #{ordinal} is not valid JSON "
                        f"({exc.msg} at line {exc.lineno})",
                    )
                    continue
                if not isinstance(obj, dict):
                    continue
                if not _INDICATOR_SHAPE_KEYS <= set(obj):
                    continue
                payload = {
                    k: v for k, v in obj.items() if k not in _INDICATOR_ROUTING_KEYS
                }
                try:
                    Indicator.model_validate(payload)
                except Exception as exc:  # noqa: BLE001 — pydantic raises many types
                    failures.append(
                        f"{rel}: block #{ordinal} — "
                        f"Indicator.model_validate rejected: {exc}",
                    )
        assert not failures, (
            "skill Indicator examples failed validation:\n"
            + "\n".join(
                failures,
            )
        )
