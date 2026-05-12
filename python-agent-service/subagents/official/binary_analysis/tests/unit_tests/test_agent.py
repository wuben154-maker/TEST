"""Unit tests for BinaryAnalyst Agent (C14, FR-02/04/05/07/08/17).

These tests cover the three deliverables of C14:

1. Agent System Prompt (FR-08 AC-1/2/3/5/6/7/10).
2. Python-layer guard rails (FR-08 AC-9 token budget, NFR-07 round budget).
3. Facts-only degradation path (FR-08 AC-11 / E2E-01 E4).

End-to-end behaviour (FR-02/04/05/07/17 orchestration, FR-08 AC-10 audit
logging through a real LLM round) is validated by F-manual.  Here we mock
the LLM with `FakeListChatModel` so the unit suite stays hermetic.
"""

from __future__ import annotations

# Repo-wide ``pytest`` often runs with CWD = ``python-agent-service``, so ``sys.path[0]``
# is the service root and ``import tests`` resolves to the wrong package. Pin the bundle
# root at the front before any imports that need ``tests.fixtures`` (bundle-local).
import sys
from pathlib import Path as _Path

_BUNDLE_ROOT_STR = str(_Path(__file__).resolve().parents[2])
try:
    sys.path.remove(_BUNDLE_ROOT_STR)
except ValueError:
    pass
sys.path.insert(0, _BUNDLE_ROOT_STR)
_m_tests = sys.modules.get("tests")
if _m_tests is not None and getattr(_m_tests, "__file__", None):
    _tf = str(_Path(_m_tests.__file__).resolve())
    if not _tf.startswith(_BUNDLE_ROOT_STR):
        del sys.modules["tests"]
        for _k in list(sys.modules):
            if _k.startswith("tests.fixtures"):
                del sys.modules[_k]

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import ToolMessage

import prompts.system_prompt as system_prompt_module
from analyst_graph import build_binary_analyst_agent
from budget_guards import (
    BudgetCoordinator,
    RecursionDepthGuard,
    RoundBudgetGuard,
    TokenBudgetGuard,
)
from facts_report import build_facts_only_report
from tool_builder import build_binary_analyst_tools
from audit import analysis_context
from errors import BudgetExceeded
from evidence_chain.store import EvidenceChainStore
from prompts.sanitize import CLOSE_TAG, OPEN_TAG
from prompts.system_prompt import (
    BINARY_ANALYST_SYSTEM_PROMPT,
    CONVERGENCE_THRESHOLD_RATIO,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_TOKEN_BUDGET,
    DOC_DEFAULT_MAX_ROUNDS,
    DOC_DEFAULT_TOKEN_BUDGET,
    TOKEN_BUDGET_HARD_CAP,
)
from schema.evidence_chain import Bucket
from schema.indicator import Indicator, Severity
from schema.report import VerdictLabel
from tests.fixtures.evidence_chains import malicious

_EXPECTED_TOOL_NAMES: tuple[str, ...] = (
    "file_identify",
    "evidence_chain",
    "scoring",
    "decision_gate",
    "report_gen",
    "bash",
    "python_exec",
    "file_read",
    "sandbox_session",
    "document_extract",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _DummySandboxClient:
    """Stand-in SandboxClient — tests never actually invoke tools."""


def _make_file_meta_store(analysis_id: str = "aid-test") -> EvidenceChainStore:
    """Build a store with the minimal FR-01 `file_meta` required for report."""
    store = EvidenceChainStore(analysis_id=analysis_id)
    ind = Indicator(
        source_fr="FR-01",
        indicator_type="file_meta",
        severity=Severity.INFO,
        kind="fact",
        data={
            "absolute_path": "/workspace/aid/sample.bin",
            "size_bytes": 1024,
            "format": "PE32",
            "arch": "x86_64",
            "mime_type": "application/x-dosexec",
            "platform": "Windows",
            "fingerprints": {
                "sha256": "a" * 64,
                "md5": "b" * 32,
                "sha1": "c" * 40,
            },
        },
    )
    store.append(Bucket.file_meta, ind)
    return store


def _fake_model() -> FakeListChatModel:
    """Fake LLM — returns a canned string, supports bind_tools."""
    return FakeListChatModel(responses=["done"])


# ---------------------------------------------------------------------------
# System Prompt coverage (FR-08 AC-1/2/3/5/6/7 + IR-06 + ADR-04)
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """Declarative prompt assertions — the prompt is the test fixture."""

    def test_delegates_stage_maps_to_orchestrators(self) -> None:
        """The system prompt stays a thin control plane."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT
        assert "Stage Map" in prompt
        assert "FR-08" in prompt
        assert "binary-analysis-e2e-orchestrator" in prompt
        assert "document-analysis-e2e-orchestrator" in prompt

    def test_forbids_raw_sample_bytes(self) -> None:
        """FR-08 AC-2 / NFR-03: LLM consumes only the structured snapshot."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT
        assert "evidence_chain" in prompt
        # Must explicitly forbid raw bytes.
        assert "raw sample" in prompt.lower() or "sample.bin" in prompt

    def test_enforces_confidence_and_evidence_refs(self) -> None:
        """FR-08 AC-3 / NFR-11: LLM inferences carry HIGH/MEDIUM/LOW + refs."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT
        assert "HIGH" in prompt
        assert "MEDIUM" in prompt
        assert "LOW" in prompt
        assert "evidence_refs" in prompt

    def test_declares_gap_note(self) -> None:
        """FR-08 AC-5: LLM declares gaps when evidence is insufficient."""
        assert "gap_note" in BINARY_ANALYST_SYSTEM_PROMPT

    def test_does_not_inline_fr08_phase_details(self) -> None:
        """FR-08 phase details live in the selected orchestrator."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT
        assert "快速扫描" not in prompt
        assert "深入分析" not in prompt
        assert "综合研判" not in prompt
        assert "behavior_chain" not in prompt
        assert "self-consistency" not in prompt.lower()

    def test_declares_untrusted_tag(self) -> None:
        """IR-06 / ADR-08: <untrusted_sample_content> tag is declared."""
        assert OPEN_TAG in BINARY_ANALYST_SYSTEM_PROMPT

    def test_names_scoring_authority(self) -> None:
        """ADR-04: ScoringTool is the verdict authority, not the LLM."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT
        assert "scoring" in prompt.lower()
        assert "authority" in prompt.lower() or "权威" in prompt

    def test_mentions_budget_guard(self) -> None:
        """FR-08 AC-9: prompt must describe the token budget convergence rule."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT
        assert str(DEFAULT_TOKEN_BUDGET) in prompt or "token budget" in prompt.lower()

    def test_agent_md_template_matches_frozen_prompt(self) -> None:
        """Prose template is stored in agent.md; Python only substitutes placeholders.

        agent.md is loaded as a single continuous template (the previous
        base/patch split with ``<!-- system_prompt:document_mode_patch -->``
        has been removed — document routing rules now live in §1).
        """
        md_path = Path(system_prompt_module.__file__).resolve().parent / "agent.md"
        assert md_path.is_file()
        raw = md_path.read_text(encoding="utf-8")
        rendered = raw.rstrip("\n").format(
            open_tag=OPEN_TAG,
            close_tag=CLOSE_TAG,
            max_rounds=DEFAULT_MAX_ROUNDS,
            token_budget=DEFAULT_TOKEN_BUDGET,
            threshold_pct=int(CONVERGENCE_THRESHOLD_RATIO * 100),
        )
        assert rendered == BINARY_ANALYST_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Tool assembly (FR-02/04/05/07/17 orchestration contract)
# ---------------------------------------------------------------------------


class TestToolAssembly:
    def test_returns_ten_tools_in_canonical_order(self) -> None:
        """All 5 self-authored + 4 primitive + 1 document tool are registered (ADR-DOC-10)."""
        store = EvidenceChainStore(analysis_id="aid-x")
        tools = build_binary_analyst_tools(
            store=store,
            sandbox_client=_DummySandboxClient(),
        )
        assert len(tools) == len(_EXPECTED_TOOL_NAMES)
        names = tuple(t.name for t in tools)
        assert names == _EXPECTED_TOOL_NAMES

    def test_document_extract_tool_registered(self) -> None:
        """ADR-DOC-10: 'document_extract' must appear in build_binary_analyst_tools output."""
        store = EvidenceChainStore(analysis_id="aid-doc")
        tools = build_binary_analyst_tools(
            store=store,
            sandbox_client=_DummySandboxClient(),
        )
        tool_names = [t.name for t in tools]
        assert "document_extract" in tool_names

    def test_tools_share_store_instance(self) -> None:
        """FR-09 AC-8: all store-writing tools must see the same backing store."""
        store = EvidenceChainStore(analysis_id="aid-x")
        tools = build_binary_analyst_tools(
            store=store,
            sandbox_client=_DummySandboxClient(),
        )
        store_holders = {
            t.name: t for t in tools if getattr(t, "store", None) is not None
        }
        assert {
            "file_identify",
            "evidence_chain",
            "scoring",
            "decision_gate",
            "report_gen",
            "document_extract",
        } <= set(
            store_holders,
        )
        for tool in store_holders.values():
            assert tool.store is store


# ---------------------------------------------------------------------------
# Agent smoke — compiles with the FakeListChatModel end-to-end
# ---------------------------------------------------------------------------


class TestAgentCompilation:
    def test_build_binary_analyst_agent_compiles(self, tmp_path: Path) -> None:
        """ADR-01 + ADR-14: agent builds without raising, returns a graph."""
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        # Minimal skill so SkillsMiddleware discovery has something to find.
        skill_dir = skills_root / "dummy-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: dummy\ndescription: A dummy skill.\n---\nBody.\n",
            encoding="utf-8",
        )

        store = EvidenceChainStore(analysis_id="aid-compile")
        graph = build_binary_analyst_agent(
            model=_fake_model(),
            store=store,
            sandbox_client=_DummySandboxClient(),
            skills_root=skills_root,
        )
        # CompiledStateGraph from langgraph exposes `.get_graph()` and `.nodes`.
        assert graph is not None
        assert hasattr(graph, "invoke")


# ---------------------------------------------------------------------------
# TokenBudgetGuard / RoundBudgetGuard (FR-08 AC-9 + NFR-05/07)
# ---------------------------------------------------------------------------


class TestTokenBudgetGuard:
    def test_converges_at_threshold(self) -> None:
        """FR-08 AC-9: should_converge flips once threshold is crossed."""
        guard = TokenBudgetGuard(budget=10_000, threshold_ratio=0.8)
        guard.record(7_999)
        assert guard.should_converge is False
        guard.record(1)  # hits 8_000 = 80%
        assert guard.should_converge is True

    def test_exceeds_and_raises(self) -> None:
        """NFR-05: enforce() raises BudgetExceeded once consumed ≥ budget."""
        guard = TokenBudgetGuard(budget=10_000, threshold_ratio=0.8)
        guard.record(10_000)
        assert guard.exceeded is True
        with pytest.raises(BudgetExceeded):
            guard.enforce()

    def test_defaults_match_prompt_constants(self) -> None:
        """Default budget wiring matches the value declared in the prompt."""
        guard = TokenBudgetGuard()
        assert guard.budget == DEFAULT_TOKEN_BUDGET
        assert guard.should_converge is False

    @pytest.mark.parametrize("bad_budget", [0, -1])
    def test_rejects_non_positive_budget(self, bad_budget: int) -> None:
        with pytest.raises(ValueError, match="budget must be positive"):
            TokenBudgetGuard(budget=bad_budget)

    @pytest.mark.parametrize("bad_ratio", [0.0, -0.1, 1.5])
    def test_rejects_out_of_range_ratio(self, bad_ratio: float) -> None:
        with pytest.raises(ValueError, match="threshold_ratio must be in"):
            TokenBudgetGuard(budget=10_000, threshold_ratio=bad_ratio)

    def test_rejects_negative_record(self) -> None:
        guard = TokenBudgetGuard(budget=10_000)
        with pytest.raises(ValueError, match="tokens must be non-negative"):
            guard.record(-1)


class TestRoundBudgetGuard:
    def test_tick_counts_and_overflows(self) -> None:
        """NFR-07: round counter raises BudgetExceeded after max_rounds."""
        guard = RoundBudgetGuard(max_rounds=3)
        for _ in range(3):
            guard.tick()
        assert guard.rounds == 3
        assert guard.remaining == 0
        with pytest.raises(BudgetExceeded):
            guard.tick()

    def test_default_matches_prompt_constant(self) -> None:
        assert RoundBudgetGuard().max_rounds == DEFAULT_MAX_ROUNDS

    @pytest.mark.parametrize("bad_max", [0, -5])
    def test_rejects_non_positive_max_rounds(self, bad_max: int) -> None:
        with pytest.raises(ValueError, match="max_rounds must be positive"):
            RoundBudgetGuard(max_rounds=bad_max)

    def test_convergence_ratio_is_sane(self) -> None:
        """Documentation constant must land strictly between 0 and 1."""
        assert 0 < CONVERGENCE_THRESHOLD_RATIO < 1


# ---------------------------------------------------------------------------
# Facts-only degradation path (FR-08 AC-11 / E2E-01 E4)
# ---------------------------------------------------------------------------


class TestFactsOnlyReport:
    def test_writes_unknown_verdict(self, tmp_path: Path) -> None:
        """FR-08 AC-11: degraded report carries Verdict=UNKNOWN + MANUAL_REVERSE."""
        store = _make_file_meta_store(analysis_id="aid-unknown")
        output_dir = tmp_path / "out"

        result = build_facts_only_report(
            store=store,
            analysis_id="aid-unknown",
            output_dir=output_dir,
            reason="three consecutive LlmSchemaError",
            model_label="fake-llm",
        )

        assert Path(result.json_path).exists()
        assert Path(result.md_path).exists()

        payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))
        assert payload["verdict"]["label"] == "UNKNOWN"
        assert payload["escalation_recommendation"]["level"] == "MANUAL_REVERSE"
        assert payload["schema_version"] == "1.1.0"
        # Gap note surfaces the concrete reason.
        assert any(
            "LLM layer degraded" in gap for gap in payload["analysis_coverage"]["gaps"]
        )

    def test_logs_audit_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-08 AC-10 / NFR-06: fallback records an audit entry."""
        log_dir = tmp_path / "logs"
        monkeypatch.setenv("BINARY_ANALYSIS_LOG_DIR", str(log_dir))
        # Force the audit module to pick up the new default.
        import audit as audit_mod

        monkeypatch.setattr(audit_mod, "_DEFAULT_LOG_DIR", log_dir)

        store = _make_file_meta_store(analysis_id="aid-audit")
        output_dir = tmp_path / "out"

        with analysis_context("aid-audit", log_dir=log_dir):
            build_facts_only_report(
                store=store,
                analysis_id="aid-audit",
                output_dir=output_dir,
                reason="unrecoverable",
                model_label="fake-llm",
            )

        audit_file = log_dir / "aid-audit.audit.jsonl"
        assert audit_file.exists()
        entries = [
            json.loads(line)
            for line in audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        fallback_entries = [
            e
            for e in entries
            if e.get("event_type") == "llm_request"
            and e.get("stage") == "facts_only_fallback"
        ]
        assert fallback_entries, f"no fallback audit entry in {entries}"
        assert fallback_entries[0]["error_code"] == "LLM_UNRECOVERABLE"
        assert fallback_entries[0]["success"] is False

    def test_cleans_tmp_root(self, tmp_path: Path) -> None:
        """FR-15 AC-10 / IR-03: fallback still cleans the analysis tmpdir."""
        store = _make_file_meta_store(analysis_id="aid-cleanup")

        tmp_root = tmp_path / "tmp"
        analysis_dir = tmp_root / "deepagent-analyze-aid-cleanup"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "leak.bin").write_bytes(b"artefact")

        output_dir = tmp_path / "out"
        result = build_facts_only_report(
            store=store,
            analysis_id="aid-cleanup",
            output_dir=output_dir,
            reason="unrecoverable",
            tmp_root=tmp_root,
        )

        assert result.cleanup_performed is True
        assert not analysis_dir.exists()

    def test_requires_file_meta_in_store(self, tmp_path: Path) -> None:
        """E2E-01 E4: an empty store surfaces the missing-prerequisite error."""
        empty_store = EvidenceChainStore(analysis_id="aid-empty")
        with pytest.raises(ValueError, match="file_meta"):
            build_facts_only_report(
                store=empty_store,
                analysis_id="aid-empty",
                output_dir=tmp_path / "out",
                reason="unrecoverable",
            )


# ---------------------------------------------------------------------------
# Guard interop with create_deep_agent smoke (ADR-14 SkillsMiddleware injection)
# ---------------------------------------------------------------------------


class TestSkillsMiddlewareInjection:
    def test_skills_middleware_is_added_when_skills_configured(
        self,
        tmp_path: Path,
    ) -> None:
        """ADR-14: analyst_graph must wire SkillsMiddleware via create_deep_agent."""
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        (skills_root / "probe").mkdir()
        (skills_root / "probe" / "SKILL.md").write_text(
            "---\nname: probe\ndescription: probe skill.\n---\nprobe body.\n",
            encoding="utf-8",
        )

        with patch("analyst_graph.create_deep_agent") as mock_create:
            mock_create.return_value = object()
            store = EvidenceChainStore(analysis_id="aid-skills")
            build_binary_analyst_agent(
                model=_fake_model(),
                store=store,
                sandbox_client=_DummySandboxClient(),
                skills_root=skills_root,
            )
            kwargs: dict[str, Any] = mock_create.call_args.kwargs
            assert kwargs["skills"], "skills source list must be non-empty"
            # ADR-DOC-10 (post-split-removal): system_prompt is the single
            # rendered BINARY_ANALYST_SYSTEM_PROMPT — document routing rules
            # are inlined in agent.md, not appended as a separate patch.
            assert kwargs["system_prompt"] == BINARY_ANALYST_SYSTEM_PROMPT
            tools = kwargs["tools"]
            assert [t.name for t in tools] == list(_EXPECTED_TOOL_NAMES)


# ---------------------------------------------------------------------------
# Document-mode section in the rendered system prompt (ADR-DOC-10 + FR-08 AC-1/8/9)
# ---------------------------------------------------------------------------


class TestDocumentRoutingGuards:
    """ADR-DOC-10: document routing guards live in agent.md §1.

    The previous base/patch split (``<!-- system_prompt:document_mode_patch -->``
    marker plus exported ``DOCUMENT_MODE_PROMPT_PATCH`` constant) has been
    removed — these tests now assert that the same hard constraints survive
    in the single rendered :data:`BINARY_ANALYST_SYSTEM_PROMPT`.
    """

    def test_no_separate_document_mode_section(self) -> None:
        """Document routing is folded into §1 instead of a trailing §5."""
        assert "## 5. 文档模式" not in BINARY_ANALYST_SYSTEM_PROMPT

    def test_prompt_contains_document_bootstrap_guard(self) -> None:
        """ADR-DOC-10: §1 points to the document orchestrator."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT
        assert (
            "examples/binary_analysis/skills/document-analysis-e2e-orchestrator/"
            "SKILL.md"
        ) in prompt
        assert "document Stage Map" in prompt

    def test_prompt_mentions_audit_analysis_id(self) -> None:
        """NFR-06: audit output remains keyed by analysis_id."""
        assert "analysis_id" in BINARY_ANALYST_SYSTEM_PROMPT

    def test_prompt_mentions_document_tier(self) -> None:
        """ADR-DOC-10: routing references document_tier."""
        assert "document_tier" in BINARY_ANALYST_SYSTEM_PROMPT

    def test_prompt_forbids_pe_elf_document_extract(self) -> None:
        """FR-08 AC-8: document_extract must be forbidden on PE/ELF/Mach-O."""
        prompt = BINARY_ANALYST_SYSTEM_PROMPT.lower()
        assert "document_extract" in prompt
        assert "pe" in prompt or "elf" in prompt or "mach-o" in prompt

    def test_enhanced_system_prompt_equals_frozen_prompt(self, tmp_path: Path) -> None:
        """build_binary_analyst_agent passes the single frozen prompt verbatim."""
        skills_root = tmp_path / "skills"
        skills_root.mkdir()

        with patch("analyst_graph.create_deep_agent") as mock_create:
            mock_create.return_value = object()
            store = EvidenceChainStore(analysis_id="aid-doc-section")
            build_binary_analyst_agent(
                model=_fake_model(),
                store=store,
                sandbox_client=_DummySandboxClient(),
                skills_root=skills_root,
            )
            kwargs: dict[str, Any] = mock_create.call_args.kwargs
            assert kwargs["system_prompt"] == BINARY_ANALYST_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# FR-07 / FR-17 reactive-downgrade contract (E2E-01 E2 / E3)
# ---------------------------------------------------------------------------


def _get_tool(tools: list, name: str) -> Any:
    """Return the tool with ``name`` from the canonical 9-tool list."""
    return next(t for t in tools if t.name == name)


class TestReactiveDowngradeContract:
    """Orchestrator skill contract: a simulated tool-layer failure must be
    expressible through :class:`EvidenceChainTool` using the canonical
    ``analysis_coverage`` indicator_type, and downstream consumers
    (:class:`ScoringTool`) must still converge to a non-UNKNOWN Verdict
    from the remaining facts (FR-02 AC-8 / FR-08 AC-11 / E2E-01 E2).

    These tests stand in for the prompt-level behaviour declared in
    ``binary-analysis-e2e-orchestrator/SKILL.md`` Stage FR-07 downgrade
    table — they do NOT invoke the real LLM, only the canonical tool
    path that the Agent System Prompt instructs the LLM to follow when
    it sees the indicated ``ToolMessage`` content.
    """

    def test_analyzeheadless_timeout_skip_still_yields_verdict(self) -> None:
        """E2E-01 E2 · Stage FR-07 reactive downgrade.

        Given a malicious fixture (entropy + imports + anti-debug +
        packer + behavior-chain facts all present) and a simulated
        ``analyzeHeadless`` timeout ``ToolMessage``, the orchestrator
        skill expects the LLM to append a single ``analysis_coverage``
        Indicator to the ``disassembly`` bucket with
        ``data.status="SKIPPED"`` / ``data.reason="decompiler_unavailable"``.

        With that marker in place :class:`ScoringTool` must still emit a
        non-UNKNOWN Verdict from the remaining, non-disassembly evidence.
        """
        store = malicious.build(analysis_id="aid-fr07-e2")
        assert not store.snapshot().disassembly, (
            "malicious fixture precondition: disassembly empty"
        )

        tools = build_binary_analyst_tools(
            store=store,
            sandbox_client=_DummySandboxClient(),
        )
        evidence_tool = _get_tool(tools, "evidence_chain")
        scoring_tool = _get_tool(tools, "scoring")

        timeout_message = ToolMessage(
            content=(
                "analyzeHeadless timeout after 300s; "
                "Ghidra postScript did not produce manifest.json"
            ),
            tool_call_id="call_bash_analyzeheadless",
            name="bash",
        )
        assert "analyzeHeadless timeout" in timeout_message.content

        append_result = evidence_tool.invoke(
            {
                "action": "append",
                "bucket": Bucket.disassembly.value,
                "indicator": {
                    "source_fr": "FR-07",
                    "indicator_type": "analysis_coverage",
                    "severity": Severity.INFO.value,
                    "kind": "fact",
                    "data": {
                        "dimension": "decompilation",
                        "status": "SKIPPED",
                        "reason": "decompiler_unavailable",
                        "trigger": timeout_message.content,
                    },
                },
            },
        )
        assert append_result["ok"] is True

        snap = store.snapshot()
        markers = [
            ind
            for ind in snap.disassembly
            if ind.indicator_type == "analysis_coverage"
            and ind.data.get("status") == "SKIPPED"
            and ind.data.get("reason") == "decompiler_unavailable"
        ]
        assert len(markers) == 1, (
            "Stage FR-07 reactive downgrade must write exactly one "
            "analysis_coverage(SKIPPED, decompiler_unavailable) marker"
        )

        scoring_payload = scoring_tool.invoke({"analysis_id": "aid-fr07-e2"})
        assert scoring_payload["verdict"] != VerdictLabel.UNKNOWN.value, (
            "ScoringTool must still produce a non-UNKNOWN Verdict from "
            "the remaining facts (E2E-01 E2 acceptance)"
        )

    def test_empty_disassembly_triggers_fr17_behavior_chain_skip_marker(
        self,
    ) -> None:
        """E2E-01 E3 · Stage FR-17 reactive downgrade.

        With ``disassembly`` empty at FR-17 entry, the orchestrator
        skill mandates a single ``analysis_coverage`` Indicator in the
        ``behavior_chain`` bucket (``data.status="SKIPPED"`` /
        ``data.reason="no_decompilation_input"``); subsequent
        ``behavior_chain`` consumers treat the stage as degraded rather
        than missing.
        """
        store = _make_file_meta_store(analysis_id="aid-fr17")
        snap = store.snapshot()
        assert not snap.disassembly, (
            "FR-17 precondition: disassembly empty before this stage runs"
        )
        assert not snap.behavior_chain, (
            "FR-17 precondition: behavior_chain empty before this stage runs"
        )

        tools = build_binary_analyst_tools(
            store=store,
            sandbox_client=_DummySandboxClient(),
        )
        evidence_tool = _get_tool(tools, "evidence_chain")

        append_result = evidence_tool.invoke(
            {
                "action": "append",
                "bucket": Bucket.behavior_chain.value,
                "indicator": {
                    "source_fr": "FR-17",
                    "indicator_type": "analysis_coverage",
                    "severity": Severity.INFO.value,
                    "kind": "fact",
                    "data": {
                        "dimension": "behavior_chain",
                        "status": "SKIPPED",
                        "reason": "no_decompilation_input",
                    },
                },
            },
        )
        assert append_result["ok"] is True

        snap = store.snapshot()
        markers = [
            ind
            for ind in snap.behavior_chain
            if ind.indicator_type == "analysis_coverage"
            and ind.data.get("dimension") == "behavior_chain"
            and ind.data.get("status") == "SKIPPED"
            and ind.data.get("reason") == "no_decompilation_input"
        ]
        assert len(markers) == 1, (
            "Stage FR-17 must write exactly one "
            "analysis_coverage(SKIPPED, no_decompilation_input) marker"
        )


# ---------------------------------------------------------------------------
# FR-08 AC-2/3/4/5/6/7 recursion budget guards (C7)
# ---------------------------------------------------------------------------


class TestDocModeConstants:
    """FR-08 AC-2/3: document-mode budget constants must meet spec values."""

    def test_doc_default_token_budget_is_80k(self) -> None:
        """FR-08 AC-2: document mode token ceiling defaults to 80 000."""
        assert DOC_DEFAULT_TOKEN_BUDGET == 80_000

    def test_doc_default_max_rounds_is_15(self) -> None:
        """FR-08 AC-3: document mode LLM round ceiling defaults to 15."""
        assert DOC_DEFAULT_MAX_ROUNDS == 15

    def test_token_budget_hard_cap_is_120k(self) -> None:
        """FR-08 AC-6: hard cap for recursive scenarios is 120 000."""
        assert TOKEN_BUDGET_HARD_CAP == 120_000

    def test_binary_mode_defaults_unchanged(self) -> None:
        """e2e01 binary-mode defaults must not be altered by e2e02 additions."""
        assert DEFAULT_TOKEN_BUDGET == 50_000
        assert DEFAULT_MAX_ROUNDS == 10


class TestTokenBudgetGuardDocMode:
    """FR-08 AC-2/6: 80k soft limit + 120k hard cap behaviour."""

    def test_80k_converges_at_64k(self) -> None:
        """FR-08 AC-2: at 80k budget, 80% threshold triggers at 64k tokens."""
        guard = TokenBudgetGuard(
            budget=DOC_DEFAULT_TOKEN_BUDGET,  # 80_000
            threshold_ratio=CONVERGENCE_THRESHOLD_RATIO,  # 0.8
        )
        guard.record(63_999)
        assert guard.should_converge is False
        guard.record(1)  # hits 64_000 = 80% of 80_000
        assert guard.should_converge is True

    def test_80k_exceeded_raises(self) -> None:
        """FR-08 AC-2: consuming 80k tokens trips exceeded flag and enforce raise."""
        guard = TokenBudgetGuard(budget=DOC_DEFAULT_TOKEN_BUDGET)
        guard.record(DOC_DEFAULT_TOKEN_BUDGET)
        assert guard.exceeded is True
        with pytest.raises(BudgetExceeded) as exc_info:
            guard.enforce()
        assert exc_info.value.reason == "token"

    def test_try_extend_to_hard_cap_succeeds(self) -> None:
        """FR-08 AC-6: extension from 80k to 120k hard cap returns True."""
        guard = TokenBudgetGuard(
            budget=DOC_DEFAULT_TOKEN_BUDGET,  # 80_000
            hard_cap=TOKEN_BUDGET_HARD_CAP,  # 120_000
        )
        guard.record(81_000)
        assert guard.exceeded is True

        result = guard.try_extend_to_hard_cap()

        assert result is True
        assert guard.budget == TOKEN_BUDGET_HARD_CAP
        assert not guard.exceeded  # 81k consumed; new budget = 120k

    def test_try_extend_already_at_hard_cap_returns_false(self) -> None:
        """FR-08 AC-6: second extension attempt returns False (no-op)."""
        guard = TokenBudgetGuard(
            budget=DOC_DEFAULT_TOKEN_BUDGET,
            hard_cap=TOKEN_BUDGET_HARD_CAP,
        )
        guard.try_extend_to_hard_cap()  # first extension: 80k → 120k
        result = guard.try_extend_to_hard_cap()  # already at hard cap
        assert result is False
        assert guard.budget == TOKEN_BUDGET_HARD_CAP

    def test_budget_equals_hard_cap_returns_false(self) -> None:
        """Guard initialised at hard cap cannot extend further."""
        guard = TokenBudgetGuard(
            budget=TOKEN_BUDGET_HARD_CAP,
            hard_cap=TOKEN_BUDGET_HARD_CAP,
        )
        assert guard.try_extend_to_hard_cap() is False

    def test_hard_cap_below_budget_raises(self) -> None:
        """hard_cap must be >= budget; otherwise ValueError."""
        with pytest.raises(ValueError, match="hard_cap must be"):
            TokenBudgetGuard(budget=100_000, hard_cap=50_000)

    def test_enforce_reason_is_token(self) -> None:
        """BudgetExceeded from enforce() carries reason='token'."""
        guard = TokenBudgetGuard(budget=1_000)
        guard.record(1_000)
        with pytest.raises(BudgetExceeded) as exc_info:
            guard.enforce()
        assert exc_info.value.reason == "token"


class TestRoundBudgetGuardReason:
    """FR-08 AC-3: round guard BudgetExceeded carries reason='round'."""

    def test_tick_reason_is_round(self) -> None:
        guard = RoundBudgetGuard(max_rounds=1)
        guard.tick()
        with pytest.raises(BudgetExceeded) as exc_info:
            guard.tick()
        assert exc_info.value.reason == "round"


class TestRecursionDepthGuard:
    """FR-30 AC-4 / ADR-DOC-03: recursion depth guard prevents >max_depth nesting."""

    def test_enter_increments_depth(self) -> None:
        guard = RecursionDepthGuard(max_depth=2)
        assert guard.current_depth == 0
        guard.enter()
        assert guard.current_depth == 1
        guard.enter()
        assert guard.current_depth == 2

    def test_exit_decrements_depth(self) -> None:
        guard = RecursionDepthGuard(max_depth=2)
        guard.enter()
        guard.exit()
        assert guard.current_depth == 0

    def test_exit_never_goes_below_zero(self) -> None:
        guard = RecursionDepthGuard(max_depth=2)
        guard.exit()
        assert guard.current_depth == 0

    def test_depth_3_raises_budget_exceeded(self) -> None:
        """Depth limit 2: entering a third recursive level must raise."""
        guard = RecursionDepthGuard(max_depth=2)
        guard.enter()  # depth = 1 — ok
        guard.enter()  # depth = 2 — ok
        with pytest.raises(BudgetExceeded) as exc_info:
            guard.enter()  # depth = 3 — exceeds max
        assert exc_info.value.reason == "recursion_budget"
        assert exc_info.value.details["depth"] == 3

    def test_context_manager_protocol(self) -> None:
        """RecursionDepthGuard supports the 'with' statement."""
        guard = RecursionDepthGuard(max_depth=2)
        with guard:
            assert guard.current_depth == 1
        assert guard.current_depth == 0

    def test_rejects_non_positive_max_depth(self) -> None:
        with pytest.raises(ValueError, match="max_depth must be positive"):
            RecursionDepthGuard(max_depth=0)

    def test_default_max_depth_is_two(self) -> None:
        """ADR-DOC-03: default depth is 2 (document → embedded PE)."""
        assert RecursionDepthGuard().max_depth == 2


class TestBudgetCoordinator:
    """FR-08 AC-4/5: BudgetCoordinator wires guards + prioritize_children policy."""

    def _make_coordinator(
        self,
        *,
        token_budget: int = DOC_DEFAULT_TOKEN_BUDGET,
        max_rounds: int = DOC_DEFAULT_MAX_ROUNDS,
        max_depth: int = 2,
        child_floor: int = DEFAULT_TOKEN_BUDGET,  # 50_000
    ) -> BudgetCoordinator:
        return BudgetCoordinator(
            token_guard=TokenBudgetGuard(budget=token_budget),
            round_guard=RoundBudgetGuard(max_rounds=max_rounds),
            depth_guard=RecursionDepthGuard(max_depth=max_depth),
            child_floor=child_floor,
        )

    def test_prioritize_children_depth_zero_returns_full_remaining(self) -> None:
        """At depth 0 (no recursion) parent may use all remaining tokens."""
        coord = self._make_coordinator(token_budget=80_000)
        coord.token_guard.record(30_000)  # 50k remaining
        assert coord.prioritize_children("aid-x") == 50_000

    def test_prioritize_children_parent_starved_when_below_floor(self) -> None:
        """FR-08 AC-5: parent gets 0 tokens when remaining < child_floor."""
        coord = self._make_coordinator(token_budget=80_000, child_floor=50_000)
        coord.token_guard.record(70_000)  # 10k remaining < 50k floor
        coord.depth_guard.enter()  # depth = 1

        parent_budget = coord.prioritize_children("aid-parent")

        assert parent_budget == 0  # all 10k reserved for child

    def test_prioritize_children_parent_gets_surplus_over_floor(self) -> None:
        """FR-08 AC-5: parent gets remaining - child_floor when surplus exists."""
        coord = self._make_coordinator(token_budget=80_000, child_floor=20_000)
        coord.token_guard.record(20_000)  # 60k remaining > 20k floor
        coord.depth_guard.enter()  # depth = 1

        parent_budget = coord.prioritize_children("aid-parent")

        assert parent_budget == 40_000  # 60k - 20k floor

    def test_request_hard_cap_extension_delegates_to_token_guard(self) -> None:
        """FR-08 AC-6: coordinator extension request delegates to TokenBudgetGuard."""
        coord = self._make_coordinator(token_budget=DOC_DEFAULT_TOKEN_BUDGET)
        coord.token_guard.record(80_001)
        assert coord.token_guard.exceeded is True

        result = coord.request_hard_cap_extension()

        assert result is True
        assert coord.token_guard.budget == TOKEN_BUDGET_HARD_CAP

    def test_coordinator_exposes_all_three_guards(self) -> None:
        """BudgetCoordinator must expose token/round/depth guards as properties."""
        coord = self._make_coordinator()
        assert isinstance(coord.token_guard, TokenBudgetGuard)
        assert isinstance(coord.round_guard, RoundBudgetGuard)
        assert isinstance(coord.depth_guard, RecursionDepthGuard)


# ---------------------------------------------------------------------------
# FR-30 AC-3/4/6/7/8 — recurse_child_sample
# ---------------------------------------------------------------------------


class TestRecurseEmbeddedPe:
    """FR-30 AC-3/6/7/8: recurse_child_sample drives 1-level PE recursion."""

    pytestmark = pytest.mark.asyncio

    def _make_coordinator(
        self,
        *,
        token_budget: int = DOC_DEFAULT_TOKEN_BUDGET,
        max_depth: int = 2,
    ) -> BudgetCoordinator:
        return BudgetCoordinator(
            token_guard=TokenBudgetGuard(budget=token_budget),
            round_guard=RoundBudgetGuard(max_rounds=DOC_DEFAULT_MAX_ROUNDS),
            depth_guard=RecursionDepthGuard(max_depth=max_depth),
            child_floor=DEFAULT_TOKEN_BUDGET,
        )

    async def test_recurse_embedded_pe_writes_parent_child_link(
        self,
        tmp_path: Path,
    ) -> None:
        """FR-30 AC-7: after child completes, parent delivery_chain_doc has 1 parent_child_link."""
        from unittest.mock import MagicMock

        from embedded_recursion import recurse_child_sample

        parent_store = _make_file_meta_store("parent-aid-001")
        child_sample_id = "child-aid-001"
        coordinator = self._make_coordinator()
        depth_guard = coordinator.depth_guard

        # Mock child graph: invoke does nothing (child store stays empty)
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": []}

        with patch(
            "embedded_recursion.build_binary_analyst_agent",
            return_value=mock_graph,
        ):
            result = await recurse_child_sample(
                parent_store,
                child_sample_id,
                "/workspace/parent-aid-001/children/child-aid-001.bin",
                coordinator,
                depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="parent-aid-001",
                child_sha256="abc123",
                child_suggested_format="PE32",
            )

        assert result["status"] == "completed"
        assert result["child_sample_id"] == child_sample_id

        # AC-7: delivery_chain_doc bucket in parent store has exactly 1 parent_child_link
        snapshot = parent_store.snapshot()
        links = [
            ind
            for ind in snapshot.delivery_chain_doc
            if ind.indicator_type == "parent_child_link"
        ]
        assert len(links) == 1
        link = links[0]
        assert link.data["parent_analysis_id"] == "parent-aid-001"
        assert link.data["child_sample_id"] == child_sample_id
        assert link.data["child_sha256"] == "abc123"
        assert link.data["child_suggested_format"] == "PE32"
        assert "delivery_chain_doc_indicator_id" in result

    async def test_recurse_embedded_pe_returns_child_report(
        self,
        tmp_path: Path,
    ) -> None:
        """FR-15 handoff: completed child recursion returns report metadata."""
        from embedded_recursion import recurse_child_sample

        parent_store = _make_file_meta_store("parent-report")
        coordinator = self._make_coordinator()
        captured_child_stores: list[EvidenceChainStore] = []

        class _ChildGraph:
            async def ainvoke(self, _input: dict[str, object]) -> dict[str, object]:
                child_store = captured_child_stores[0]
                child_store.append(
                    Bucket.file_meta,
                    Indicator(
                        source_fr="FR-01",
                        indicator_type="file_meta",
                        severity=Severity.INFO,
                        kind="fact",
                        data={
                            "absolute_path": "/workspace/child-report/sample.bin",
                            "size_bytes": 256,
                            "format": "PE32",
                            "arch": "x86",
                            "fingerprints": {
                                "sha256": "d" * 64,
                                "md5": "e" * 32,
                                "sha1": "f" * 40,
                            },
                        },
                    ),
                )
                return {"messages": []}

        def _build(**kwargs: Any) -> _ChildGraph:
            captured_child_stores.append(kwargs["store"])
            return _ChildGraph()

        with patch(
            "embedded_recursion.build_binary_analyst_agent",
            side_effect=_build,
        ):
            result = await recurse_child_sample(
                parent_store,
                "child-report",
                "/workspace/parent-report/children/child-report.bin",
                coordinator,
                coordinator.depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="parent-report",
                child_sha256="d" * 64,
                child_suggested_format="PE32",
                output_dir=tmp_path,
            )

        assert result["status"] == "completed"
        child_report = result["child_report"]
        assert child_report["sha256"] == "d" * 64
        assert Path(child_report["json_path"]).exists()
        assert Path(child_report["md_path"]).exists()

    async def test_recurse_child_ac8_writes_derived_from_in_child_file_meta(
        self,
        tmp_path: Path,
    ) -> None:
        """FR-30 AC-8: child store's file_meta bucket gets derived_from=parent_analysis_id."""
        from unittest.mock import MagicMock

        from embedded_recursion import recurse_child_sample

        parent_store = _make_file_meta_store("parent-ac8")
        coordinator = self._make_coordinator()

        captured_child_stores: list[Any] = []

        def _capturing_build(**kwargs: Any) -> Any:
            # Record the child store before returning mock graph
            captured_child_stores.append(kwargs["store"])
            mock = MagicMock()
            mock.invoke.return_value = {"messages": []}
            return mock

        with patch(
            "embedded_recursion.build_binary_analyst_agent",
            side_effect=_capturing_build,
        ):
            await recurse_child_sample(
                parent_store,
                "child-ac8",
                "/workspace/parent-ac8/children/child-ac8.bin",
                coordinator,
                coordinator.depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="parent-ac8",
            )

        assert len(captured_child_stores) == 1
        child_store = captured_child_stores[0]
        child_snapshot = child_store.snapshot()

        # AC-8: at least one file_meta Indicator with derived_from containing parent_analysis_id
        derived = [
            ind
            for ind in child_snapshot.file_meta
            if "parent-ac8" in ind.derived_from
            or ind.data.get("derived_from_parent_analysis_id") == "parent-ac8"
        ]
        assert len(derived) >= 1

    async def test_recurse_child_depth_guard_entered_and_exited(
        self,
        tmp_path: Path,
    ) -> None:
        """RecursionDepthGuard.enter() is called; depth returns to 0 after completion."""
        from unittest.mock import MagicMock

        from embedded_recursion import recurse_child_sample

        parent_store = _make_file_meta_store("parent-depth")
        coordinator = self._make_coordinator()
        depth_guard = coordinator.depth_guard

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": []}

        assert depth_guard.current_depth == 0

        with patch("embedded_recursion.build_binary_analyst_agent", return_value=mock_graph):
            await recurse_child_sample(
                parent_store,
                "child-depth",
                "/workspace/parent-depth/children/child-depth.bin",
                coordinator,
                depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="parent-depth",
            )

        assert depth_guard.current_depth == 0


class TestDeliveryChainDocLinks:
    """FR-30 AC-4/7: depth limit and delivery_chain_doc Indicator structure."""

    pytestmark = pytest.mark.asyncio

    async def test_depth_limit_exceeded_writes_recursion_depth_exceeded(
        self,
        tmp_path: Path,
    ) -> None:
        """FR-30 AC-4: at max_depth=1, second recurse writes recursion_depth_exceeded."""
        from embedded_recursion import recurse_child_sample

        parent_store = _make_file_meta_store("parent-depth-limit")
        coord = BudgetCoordinator(
            token_guard=TokenBudgetGuard(budget=DOC_DEFAULT_TOKEN_BUDGET),
            round_guard=RoundBudgetGuard(max_rounds=DOC_DEFAULT_MAX_ROUNDS),
            depth_guard=RecursionDepthGuard(max_depth=1),
            child_floor=DEFAULT_TOKEN_BUDGET,
        )
        depth_guard = coord.depth_guard

        # Pre-enter once so next enter() exceeds max_depth=1
        depth_guard.enter()  # depth = 1 — ok
        # depth_guard is now at 1; next enter() will push to 2 > max_depth=1

        result = await recurse_child_sample(
            parent_store,
            "child-over-depth",
            "/workspace/parent-depth-limit/children/child-over-depth.bin",
            coord,
            depth_guard,
            model=_fake_model(),
            sandbox_client=_DummySandboxClient(),
            skills_root=tmp_path,
            parent_analysis_id="parent-depth-limit",
        )

        assert result["status"] == "recursion_depth_exceeded"
        assert "error" in result

        # embedded_payloads bucket should contain the recursion_depth_exceeded Indicator
        snapshot = parent_store.snapshot()
        exceeded = [
            ind
            for ind in snapshot.embedded_payloads
            if ind.indicator_type == "recursion_depth_exceeded"
        ]
        assert len(exceeded) == 1
        assert exceeded[0].data["child_sample_id"] == "child-over-depth"

    async def test_parent_child_link_data_structure(
        self,
        tmp_path: Path,
    ) -> None:
        """FR-30 AC-7: parent_child_link Indicator carries required fields."""
        from unittest.mock import MagicMock

        from embedded_recursion import recurse_child_sample

        parent_store = _make_file_meta_store("parent-link-structure")
        coord = BudgetCoordinator(
            token_guard=TokenBudgetGuard(budget=DOC_DEFAULT_TOKEN_BUDGET),
            round_guard=RoundBudgetGuard(max_rounds=DOC_DEFAULT_MAX_ROUNDS),
            depth_guard=RecursionDepthGuard(max_depth=2),
            child_floor=DEFAULT_TOKEN_BUDGET,
        )

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": []}

        with patch("embedded_recursion.build_binary_analyst_agent", return_value=mock_graph):
            await recurse_child_sample(
                parent_store,
                "child-link-test",
                "/workspace/parent-link-structure/children/child-link-test.bin",
                coord,
                coord.depth_guard,
                model=_fake_model(),
                sandbox_client=_DummySandboxClient(),
                skills_root=tmp_path,
                parent_analysis_id="parent-link-structure",
                child_sha256="deadbeef" * 8,
                child_suggested_format="PE32+",
            )

        snapshot = parent_store.snapshot()
        links = [
            ind
            for ind in snapshot.delivery_chain_doc
            if ind.indicator_type == "parent_child_link"
        ]
        assert len(links) == 1
        data = links[0].data
        required_keys = {
            "parent_analysis_id",
            "child_sample_id",
            "child_sha256",
            "child_suggested_format",
            "child_verdict",
        }
        assert required_keys.issubset(data.keys())
        assert data["child_sha256"] == "deadbeef" * 8
        assert data["child_suggested_format"] == "PE32+"
