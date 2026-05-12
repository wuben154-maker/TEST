"""Integration tests for orchestrator skill routing (P1 · ADR-DOC-10).

Verifies that the Skill-driven mode-switch mechanism declared in
:data:`BINARY_ANALYST_SYSTEM_PROMPT` (§1 routing of ``agent.md``)
correctly routes to ``document-analysis-e2e-orchestrator/SKILL.md`` when
``file_identify`` returns ``document_tier ∈ {P0, P1, P2}``.

The earlier base/patch split (``<!-- system_prompt:document_mode_patch -->``
marker plus exported ``DOCUMENT_MODE_PROMPT_PATCH`` constant) was removed;
the same routing rules now live inline in the single rendered system prompt.

Coverage:
- The system prompt embeds the exact document-orchestrator skill path.
- The skill file is readable via FilesystemBackend (structural assertion).
- The ``binary-analysis-e2e-orchestrator`` SKILL.md contains the mutual-
  exclusion guard ("DO NOT call document_extract") introduced in P1.
- The ``document-analysis-e2e-orchestrator`` SKILL.md contains a valid YAML
  frontmatter with the correct ``name``, ``id: Proto-02``, and all 9 FRs.
- A fake agent built with ``FakeListChatModel`` receives a system prompt that
  references the skill path, simulating a ``document_tier=P0`` routing trigger.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from analyst_graph import build_binary_analyst_agent
from budget_guards import (
    BudgetCoordinator,
    RecursionDepthGuard,
    RoundBudgetGuard,
    TokenBudgetGuard,
)
from evidence_chain.store import EvidenceChainStore
from prompts.system_prompt import BINARY_ANALYST_SYSTEM_PROMPT
from schema.evidence_chain import Bucket
from schema.indicator import Indicator, Severity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
DOC_SKILL_REL = "document-analysis-e2e-orchestrator/SKILL.md"
BIN_SKILL_REL = "binary-analysis-e2e-orchestrator/SKILL.md"
DOC_SKILL_PATH = SKILLS_DIR / DOC_SKILL_REL
BIN_SKILL_PATH = SKILLS_DIR / BIN_SKILL_REL

_EXPECTED_SKILL_PATH_IN_PATCH = (
    "examples/binary_analysis/skills/document-analysis-e2e-orchestrator/SKILL.md"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_markdown_h2(content: str, headings: tuple[str, ...]) -> int:
    """Return start index of the first present H2 heading, or -1."""
    for h in headings:
        idx = content.find(h)
        if idx != -1:
            return idx
    return -1


def _extract_stage_block(content: str, stage_heading: str) -> str:
    """Return markdown text from *stage_heading* to the next stage heading."""
    start = content.find(stage_heading)
    if start == -1:
        return ""
    end = content.find("\n### ", start + len(stage_heading))
    return content[start:end] if end != -1 else content[start:]


class _DummySandboxClient:
    """Minimal SandboxClient stand-in for agent construction."""


def _make_store(analysis_id: str = "aid-routing") -> EvidenceChainStore:
    store = EvidenceChainStore(analysis_id=analysis_id)
    ind = Indicator(
        source_fr="FR-01",
        indicator_type="file_meta",
        severity=Severity.INFO,
        kind="fact",
        data={
            "absolute_path": f"/workspace/{analysis_id}/sample.xlsm",
            "size_bytes": 4096,
            "format": "OOXML_XLSX_MACRO",
            "document_format": "ooxml_xlsx_macro",
            "document_tier": "P0",
            "fingerprints": {"sha256": "a" * 64, "md5": "b" * 32, "sha1": "c" * 40},
        },
    )
    store.append(Bucket.file_meta, ind)
    return store


def _make_coordinator() -> BudgetCoordinator:
    return BudgetCoordinator(
        token_guard=TokenBudgetGuard(budget=80_000),
        round_guard=RoundBudgetGuard(max_rounds=15),
        depth_guard=RecursionDepthGuard(max_depth=2),
        child_floor=50_000,
    )


# ---------------------------------------------------------------------------
# TestSystemPromptDocumentRouting — static assertions on BINARY_ANALYST_SYSTEM_PROMPT
# ---------------------------------------------------------------------------


class TestSystemPromptDocumentRouting:
    """Verify the rendered system prompt encodes the correct document-mode skill-read trigger.

    Document routing rules now live inline in agent.md §1 (the previous base/patch
    split was removed); these assertions run against the single rendered prompt.
    """

    def test_prompt_embeds_exact_skill_path(self) -> None:
        """ADR-DOC-10: the prompt must tell the agent to Read the exact skill path."""
        assert _EXPECTED_SKILL_PATH_IN_PATCH in BINARY_ANALYST_SYSTEM_PROMPT, (
            f"BINARY_ANALYST_SYSTEM_PROMPT must contain '{_EXPECTED_SKILL_PATH_IN_PATCH}'"
        )

    def test_prompt_references_document_tier_condition(self) -> None:
        """ADR-DOC-10: document routing is gated on document_tier ∈ {P0,P1,P2}."""
        assert "document_tier" in BINARY_ANALYST_SYSTEM_PROMPT
        assert "P0" in BINARY_ANALYST_SYSTEM_PROMPT

    def test_prompt_bootstraps_document_mode_without_stage_map(self) -> None:
        """ADR-DOC-10: prompt only bootstraps document mode; details live in the skill."""
        prompt_lower = BINARY_ANALYST_SYSTEM_PROMPT.lower()
        assert "document_extract" in prompt_lower
        assert "pe" in prompt_lower or "elf" in prompt_lower or "mach-o" in prompt_lower
        assert "## 5. 文档模式" not in BINARY_ANALYST_SYSTEM_PROMPT
        assert "document stage map" in prompt_lower

    def test_prompt_is_within_summary_layer_budget(self) -> None:
        """NFR-05 摘要层预算: full system prompt must stay compact (≤ ~1100 tokens ≈ 4500 chars).

        agent.md is the thin control plane; long stage maps and degradation
        details live in the orchestrator skills (build-contracts §A.3).
        """
        assert len(BINARY_ANALYST_SYSTEM_PROMPT) <= 4500, (
            f"BINARY_ANALYST_SYSTEM_PROMPT exceeds the summary-layer budget "
            f"(>4500 chars; got {len(BINARY_ANALYST_SYSTEM_PROMPT)})"
        )


# ---------------------------------------------------------------------------
# TestDocumentSkillFile — structural assertions on the new skill file
# ---------------------------------------------------------------------------


class TestDocumentSkillFile:
    """Verify SKILL.md and frontmatter for document-analysis-e2e-orchestrator."""

    def test_skill_file_exists(self) -> None:
        assert DOC_SKILL_PATH.is_file(), f"missing skill file: {DOC_SKILL_PATH}"

    def test_frontmatter_is_valid_yaml(self) -> None:
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert content.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
        _, fm_block, _ = content.split("---\n", 2)
        data = yaml.safe_load(fm_block)
        assert isinstance(data, dict), "frontmatter must be a YAML mapping"

    def test_frontmatter_name_matches_directory(self) -> None:
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        _, fm_block, _ = content.split("---\n", 2)
        data = yaml.safe_load(fm_block)
        assert data["name"] == "document-analysis-e2e-orchestrator"

    def test_frontmatter_proto_id(self) -> None:
        """IMPL-GUIDE §📚: document orchestrator must carry id: Proto-02."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        _, fm_block, _ = content.split("---\n", 2)
        data = yaml.safe_load(fm_block)
        assert data["metadata"]["id"] == "Proto-02"

    def test_frontmatter_covers_all_nine_frs(self) -> None:
        """IMPL-GUIDE §📚: 9 stages FR-01/03/06/08/09/13/14/15/30 must be listed."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        _, fm_block, _ = content.split("---\n", 2)
        data = yaml.safe_load(fm_block)
        fr_field: str = data["metadata"]["fr"]
        for fr in (
            "FR-01",
            "FR-03",
            "FR-06",
            "FR-08",
            "FR-09",
            "FR-13",
            "FR-14",
            "FR-15",
            "FR-30",
        ):
            assert fr in fr_field, f"frontmatter.fr missing {fr}"

    def test_frontmatter_includes_document_extract_in_allowed_tools(self) -> None:
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        _, fm_block, _ = content.split("---\n", 2)
        data = yaml.safe_load(fm_block)
        assert "document_extract" in data["allowed-tools"]

    def test_body_contains_stage_map_heading(self) -> None:
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "Stage Map" in content or "阶段图" in content

    def test_body_contains_operating_principles(self) -> None:
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "Operating Principles" in content or "运行原则" in content

    def test_body_contains_sandbox_only_vba_principle(self) -> None:
        """IMPL-GUIDE §📚 Operating Principle 6: Sandbox-only VBA simulation."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "Sandbox" in content or "沙箱" in content
        assert "vmonkey" in content or "VBA" in content

    def test_body_contains_mutual_exclusion_principle(self) -> None:
        """IMPL-GUIDE §📚 Operating Principle 7: document/binary mode mutual exclusion."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "mutually exclusive" in content or "互斥" in content

    def test_body_contains_document_sample_filter_guard(self) -> None:
        """Document path must not fall back to shell filters over raw samples."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        fr06 = _extract_stage_block(content, "### Stage FR-06")

        assert "grep" in content
        assert "raw sample bytes" in content
        assert "document_extract" in fr06
        assert "shell" in fr06
        assert "python_exec" in fr06

    def test_body_contains_downgrade_paths_section(self) -> None:
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "Downgrade" in content or "降级" in content

    def test_body_mentions_five_downgrade_scenarios(self) -> None:
        """IMPL-GUIDE §📚 Downgrade Paths: 5 named scenarios must appear."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        for scenario in (
            "document_parser_failed",
            "vba_simulation_timeout",
            "encrypted_office_no_password",
            "onenote_parser_unavailable",
            "recursion_budget_exceeded",
        ):
            assert scenario in content, (
                f"downgrade scenario '{scenario}' missing from SKILL.md"
            )

    def test_body_mentions_fr08_ac5_budget_strategy(self) -> None:
        """FR-08 AC-5 保子砍父 must appear in Stage FR-30 or FR-08 section."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "doc_analysis_partial" in content

    def test_body_mentions_fr08_ac9_self_consistency(self) -> None:
        """FR-08 AC-9 IOC self-consistency must be declared."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "self-consistency" in content.lower() or "自洽" in content

    def test_body_owns_document_fr08_phase_contract(self) -> None:
        """Document FR-08 reasoning details live in the document orchestrator."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        assert "### Stage FR-08" in content
        assert "Quick scan" in content
        assert "Deep dive" in content
        assert "Synthesis" in content
        assert "doc_analysis_partial" in content
        assert "confidence downgrade" in content

    def test_body_mentions_when_to_use_document_tier(self) -> None:
        """ADR-DOC-10: When to Use must reference document_tier routing."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        when_start = _find_markdown_h2(content, ("## When to Use", "## 何时使用"))
        assert when_start != -1, "SKILL.md missing When to Use / 何时使用 section"
        when_section = content[when_start : when_start + 600]
        assert "document_tier" in when_section

    def test_fr01_consumes_existing_file_identify_result(self) -> None:
        """FR-01 belongs in the Stage Map but must not repeat the first-hop call."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        fr01 = _extract_stage_block(content, "### Stage FR-01")
        assert "file_identify" in fr01
        assert "agent.md" in fr01
        assert "without calling again" in fr01
        assert "file_meta" in fr01

    def test_fr15_requires_detailed_report_appendix(self) -> None:
        """Final visible document reports must append report_gen Markdown content."""
        content = DOC_SKILL_PATH.read_text(encoding="utf-8")
        fr15 = _extract_stage_block(content, "### Stage FR-15")
        assert "## Appendix: Detailed report" in fr15
        assert "markdown_content" in fr15
        assert "detailed report written to" in fr15.lower()


# ---------------------------------------------------------------------------
# TestBinaryOrchestratorGuard — verify mutual-exclusion guard was added
# ---------------------------------------------------------------------------


class TestBinaryOrchestratorGuard:
    """Verify binary-analysis-e2e-orchestrator SKILL.md received the P1 guard."""

    def test_binary_skill_exists(self) -> None:
        assert BIN_SKILL_PATH.is_file(), (
            f"binary orchestrator skill missing: {BIN_SKILL_PATH}"
        )

    def test_do_not_call_document_extract_guard(self) -> None:
        """P1 guard: 'DO NOT call document_extract' must be in Operating Principles."""
        content = BIN_SKILL_PATH.read_text(encoding="utf-8")
        assert "document_extract" in content
        assert "DO NOT" in content or "禁止" in content

    def test_when_to_use_document_tier_branch(self) -> None:
        """P1 guard: When to Use must direct reader to document orchestrator."""
        content = BIN_SKILL_PATH.read_text(encoding="utf-8")
        when_start = _find_markdown_h2(content, ("## When to Use", "## 何时使用"))
        assert when_start != -1, "binary SKILL.md missing When to Use / 何时使用"
        when_section = content[when_start : when_start + 600]
        assert "document_tier" in when_section
        assert "document-analysis-e2e-orchestrator" in when_section

    def test_binary_skill_has_document_extract_guard(self) -> None:
        """Runtime skill must carry the mutual-exclusion guard for document_extract."""
        content = BIN_SKILL_PATH.read_text(encoding="utf-8")
        assert "document_extract" in content
        assert "DO NOT" in content

    def test_body_owns_binary_fr08_phase_contract(self) -> None:
        """Binary FR-08 reasoning details live in the binary orchestrator."""
        content = BIN_SKILL_PATH.read_text(encoding="utf-8")
        assert "### Stage FR-08" in content
        assert "Quick scan" in content
        assert "Deep dive" in content
        assert "Synthesis" in content
        assert "behavior_chain" in content
        assert "self-consistency" in content.lower()
        assert "confidence downgrade" in content

    def test_fr01_consumes_existing_file_identify_result(self) -> None:
        """FR-01 belongs in the Stage Map but must not repeat the first-hop call."""
        content = BIN_SKILL_PATH.read_text(encoding="utf-8")
        fr01 = _extract_stage_block(content, "### Stage FR-01")
        assert "file_identify" in fr01
        assert "agent.md" in fr01
        assert "without calling again" in fr01
        assert "file_meta" in fr01

    def test_fr15_requires_detailed_report_appendix(self) -> None:
        """Final visible binary reports must append report_gen Markdown content."""
        content = BIN_SKILL_PATH.read_text(encoding="utf-8")
        fr15 = _extract_stage_block(content, "### Stage FR-15")
        assert "## Appendix: Detailed report" in fr15
        assert "markdown_content" in fr15
        assert "detailed report written to" in fr15.lower()


# ---------------------------------------------------------------------------
# TestAgentRoutingTrigger — fake-model agent with document_tier=P0 result
# ---------------------------------------------------------------------------


class TestAgentRoutingTrigger:
    """Verify that a document_tier=P0 file_identify result triggers the skill read.

    We cannot verify that the LLM *actually* reads the file (that is LLM
    behaviour, not unit-testable), but we CAN verify:
    1. The system prompt injected into the agent contains the skill path.
    2. The FilesystemBackend can resolve the skill path to a readable file
       within the standard ``examples/binary_analysis/`` root.
    This combination confirms the routing chain is wired end-to-end.
    """

    def test_system_prompt_contains_skill_path(self, tmp_path: Path) -> None:
        """When the agent is built, the concatenated system prompt references
        the document orchestrator skill path from the §1 document route."""
        skills_root = tmp_path / "skills"
        skills_root.mkdir()

        with patch("analyst_graph.create_deep_agent") as mock_create:
            mock_create.return_value = MagicMock()
            store = _make_store()
            build_binary_analyst_agent(
                model=FakeListChatModel(responses=["done"]),
                store=store,
                sandbox_client=_DummySandboxClient(),
                skills_root=skills_root,
            )
            kwargs = mock_create.call_args.kwargs
            system_prompt: str = kwargs["system_prompt"]

        assert _EXPECTED_SKILL_PATH_IN_PATCH in system_prompt, (
            "System prompt must contain the document orchestrator skill path "
            f"'{_EXPECTED_SKILL_PATH_IN_PATCH}' so that a document_tier=P0 result "
            "triggers a Read call to the correct SKILL.md"
        )

    def test_skill_path_is_resolvable_from_workspace_root(self) -> None:
        """The skill path declared in BINARY_ANALYST_SYSTEM_PROMPT must resolve
        to an existing file relative to the deepagents workspace root.

        File: tests/integration_tests/test_orchestrator_skill_routing.py
        parents[0]=integration_tests [1]=tests [2]=binary_analysis
        parents[3]=examples [4]=deepagents (workspace root)
        """
        workspace_root = Path(__file__).resolve().parents[4]
        resolved = workspace_root / _EXPECTED_SKILL_PATH_IN_PATCH
        assert resolved.is_file(), (
            f"Skill path '{_EXPECTED_SKILL_PATH_IN_PATCH}' declared in "
            f"BINARY_ANALYST_SYSTEM_PROMPT does not resolve to an existing file "
            f"(looked at: {resolved})"
        )

    def test_document_tier_p0_routes_to_document_orchestrator(self) -> None:
        """Routing table test: §1 must direct document_tier samples to the document
        orchestrator skill, and (ADR-DOC-10) only the binary route may name the
        binary orchestrator (in §1)."""
        assert "document-analysis-e2e-orchestrator" in BINARY_ANALYST_SYSTEM_PROMPT
        assert (
            BINARY_ANALYST_SYSTEM_PROMPT.count("document-analysis-e2e-orchestrator")
            == 1
        ), "document orchestrator path should appear exactly once (§1 document route)"
        assert (
            BINARY_ANALYST_SYSTEM_PROMPT.count("binary-analysis-e2e-orchestrator") == 1
        ), "binary orchestrator path should appear exactly once (§1 binary route)"

    def test_file_identify_result_with_document_tier_p0_stored_in_evidence_chain(
        self,
    ) -> None:
        """A file_meta Indicator with document_tier=P0 can be written to the
        evidence chain, confirming the routing trigger is expressible."""
        store = _make_store(analysis_id="aid-p0-routing")
        snapshot = store.snapshot()
        assert len(snapshot.file_meta) == 1
        meta = snapshot.file_meta[0]
        assert meta.data.get("document_tier") == "P0"
