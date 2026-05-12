"""Unit tests for `app.parsers.stats_meta`.

Covers acceptance criteria A-04 .. A-07, N-02 from
`docs/Process/stats-bar-value-redesign/acceptance.md`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.parsers import stats_meta as sm


# ---------------------------------------------------------------------------
# classify_task_kind  (A-07)
# ---------------------------------------------------------------------------


class TestClassifyTaskKind:
    def test_security_subagent_wins(self) -> None:
        assert sm.classify_task_kind(["web-security"]) == "security"

    def test_research_subagent(self) -> None:
        assert sm.classify_task_kind(["deep-research"]) == "research"

    def test_empty(self) -> None:
        assert sm.classify_task_kind([]) is None

    def test_generic_subagent(self) -> None:
        assert sm.classify_task_kind(["general-purpose"]) is None

    def test_mixed_security_wins(self) -> None:
        # A-07: security wins over research on mixed runs.
        assert (
            sm.classify_task_kind(["deep-research", "web-security"]) == "security"
        )

    def test_underscore_normalises_to_kebab(self) -> None:
        assert sm.classify_task_kind(["web_security"]) == "security"
        assert sm.classify_task_kind(["deep_research"]) == "research"

    def test_all_four_security_variants(self) -> None:
        for st in (
            "web-security",
            "email-security",
            "binary-analysis",
            "soc-alert",
        ):
            assert sm.classify_task_kind([st]) == "security", st


# ---------------------------------------------------------------------------
# derive_security_meta  (A-04, N-03)
# ---------------------------------------------------------------------------


class TestDeriveSecurityMeta:
    def test_derive_security_meta_webshell(self) -> None:
        """A-04: schema-v2 findings + tool trail → populated security meta."""
        findings = [
            {
                "type": "web_shell",
                "severity": "high",
                "risk": 82,
            },
            {
                "type": "sqli",
                "severity": "medium",
                "risk": 55,
            },
        ]
        sec = sm.derive_security_meta(
            tools_used=["detect_web_attack", "yara_scan", "run_in_sandbox"],
            task_outputs=[],
            security_findings_raw=findings,
        )
        assert sec is not None
        assert sec.severity == "high"
        assert sec.risk_score == 82
        # Top-risk ordering (high-risk first); de-duplicated; frontend truncates.
        assert sec.threat_classes == ("web-shell", "sqli")
        # Canonical display order: static → yara → sandbox → ti.
        assert sec.validation == ("static", "yara", "sandbox")
        # Actionable counts critical/high/medium; low/info excluded.
        assert sec.actionable == {"total": 2, "critical": 0, "high": 1, "medium": 1}

    def test_actionable_breakdown_groups_by_severity(self) -> None:
        findings = [
            {"type": "rce", "severity": "critical", "risk": 95},
            {"type": "xss", "severity": "high", "risk": 80},
            {"type": "xss-2", "severity": "high", "risk": 75},
            {"type": "info_disclosure", "severity": "medium", "risk": 50},
            {"type": "best_practice", "severity": "low"},
            {"type": "noise", "severity": "info"},
        ]
        sec = sm.derive_security_meta(
            tools_used=[],
            task_outputs=[],
            security_findings_raw=findings,
        )
        assert sec is not None
        assert sec.actionable == {
            "total": 4,
            "critical": 1,
            "high": 2,
            "medium": 1,
        }

    def test_actionable_omitted_when_no_qualifying_findings(self) -> None:
        findings = [
            {"type": "noise", "severity": "low"},
            {"type": "info-only", "severity": "info"},
        ]
        sec = sm.derive_security_meta(
            tools_used=[],
            task_outputs=[],
            security_findings_raw=findings,
        )
        assert sec is not None
        assert sec.actionable is None

    def test_actionable_omitted_when_no_findings(self) -> None:
        sec = sm.derive_security_meta(
            tools_used=["detect_web_attack"],
            task_outputs=[],
            security_findings_raw=[],
        )
        assert sec is not None
        assert sec.actionable is None

    def test_empty_findings_default_info(self) -> None:
        sec = sm.derive_security_meta(
            tools_used=["detect_web_attack"],
            task_outputs=[],
            security_findings_raw=[],
        )
        assert sec is not None
        assert sec.severity == "info"
        assert sec.risk_score is None
        assert sec.threat_classes is None
        assert sec.validation == ("static",)

    def test_extracts_findings_from_task_output_json_fence(self) -> None:
        """Best-effort parse when the caller did not pre-extract findings."""
        task_output = (
            "## WRAPUP\n"
            "Detected a web shell.\n\n"
            "```json\n"
            '{"findings": [{"type": "web_shell", "severity": "critical", "risk": 95}]}\n'
            "```\n"
        )
        sec = sm.derive_security_meta(
            tools_used=["detect_web_attack"],
            task_outputs=[task_output],
            security_findings_raw=None,
        )
        assert sec is not None
        assert sec.severity == "critical"
        assert sec.risk_score == 95
        assert sec.threat_classes == ("web-shell",)

    def test_unknown_severity_is_ignored(self) -> None:
        sec = sm.derive_security_meta(
            tools_used=[],
            task_outputs=[],
            security_findings_raw=[{"type": "foo", "severity": "weird", "risk": 10}],
        )
        assert sec is not None
        assert sec.severity == "info"  # no valid severity ⇒ default
        assert sec.risk_score == 10  # risk still honoured
        assert sec.threat_classes == ("foo",)

    def test_risk_clamped_to_0_100(self) -> None:
        sec = sm.derive_security_meta(
            tools_used=[],
            task_outputs=[],
            security_findings_raw=[{"type": "a", "severity": "high", "risk": 250}],
        )
        assert sec is not None
        assert sec.risk_score == 100

    def test_web_security_schema_v2_category_and_risk_score(self) -> None:
        sec = sm.derive_security_meta(
            tools_used=["detect_web_attack"],
            task_outputs=[],
            security_findings_raw=[
                {
                    "category": "xss",
                    "severity": "high",
                    "risk_score": 83,
                }
            ],
        )

        assert sec is not None
        assert sec.risk_score == 83
        assert sec.threat_classes == ("xss",)


class TestValidationTrail:
    def test_all_four_dimensions(self) -> None:
        sec = sm.derive_security_meta(
            tools_used=[
                "detect_web_attack",
                "yara_scan",
                "run_in_sandbox",
                "threat_intel_lookup",
            ],
            task_outputs=[],
            security_findings_raw=[],
        )
        assert sec is not None
        assert sec.validation == ("static", "yara", "sandbox", "ti")

    def test_unknown_tool_does_not_contribute(self) -> None:
        sec = sm.derive_security_meta(
            tools_used=["some_random_tool"],
            task_outputs=[],
            security_findings_raw=[],
        )
        assert sec is not None
        assert sec.validation is None


# ---------------------------------------------------------------------------
# derive_research_meta  (A-05, A-06)
# ---------------------------------------------------------------------------


def _iso_days_ago(n: int) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(days=n)
    return dt.strftime("%Y-%m-%d")


class TestDeriveResearchMeta:
    def test_derive_research_meta_fullshape(self) -> None:
        """A-05: every section populated → every field derived."""
        md = f"""
# Report

## Executive Summary
- Finding one.
- Finding two.
- Finding three.
- Finding four.
- Finding five.

## Recommendations
- Do X.
- Do Y.
- Do Z.

## Gaps & Limitations
- Gap one.
- Gap two.

## Sources
- https://alpha.example.com/a — published {_iso_days_ago(3)}
- https://beta.example.org/b — published {_iso_days_ago(1)}
- https://gamma.example.net/c — published {_iso_days_ago(2)}
- https://alpha.example.com/d — published {_iso_days_ago(4)}
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.key_findings == 5
        assert res.recommendations == 3
        assert res.gaps == 2
        # 3 unique hostnames (alpha / beta / gamma).
        assert res.sources == 3
        assert res.freshness == "<=7d"

    def test_derive_research_meta_partial_sections(self) -> None:
        """A-06: missing sections → fields omitted from the serialised dict."""
        md = """
# Report

## Executive Summary
- Only a single finding.
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.key_findings == 1
        assert res.recommendations is None
        assert res.gaps is None
        assert res.sources is None
        # Frontend hides the chip when freshness is None.
        assert res.freshness is None

    def test_sources_freshness_n_a_when_no_dates(self) -> None:
        md = """
## Sources
- https://alpha.example.com/a
- https://beta.example.org/b
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.sources == 2
        assert res.freshness == "n/a"

    def test_older_freshness_bucket(self) -> None:
        md = f"""
## Sources
- https://alpha.example.com/a — {_iso_days_ago(200)}
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.freshness == "older"

    def test_bullet_count_accepts_numbered_list(self) -> None:
        md = """
## Recommendations
1. Do X.
2. Do Y.
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.recommendations == 2

    def test_bullet_count_ignores_nested(self) -> None:
        md = """
## Executive Summary
- Top one.
  - Nested one (should not count).
  - Nested two.
- Top two.
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.key_findings == 2

    def test_empty_markdown_returns_none(self) -> None:
        assert sm.derive_research_meta(report_markdown="") is None
        assert sm.derive_research_meta(report_markdown="   \n\n") is None

    def test_fenced_research_stats_block_takes_priority(self) -> None:
        """When the subagent appends a ``{"research_stats": {...}}`` fenced
        JSON block, those values must be used directly (no markdown counting)
        because deep-research reports have free-form section names that the
        alias list cannot reliably catch.
        """
        md = """
# 关于 X 主题的深度调研

## 概述
内容很长，没有英文章节标题。

```json
{"research_stats": {"keyFindings": 7, "recommendations": 4, "gaps": 2}}
```

### Sources
- [1] Alpha: https://alpha.example.com/a
- [2] Beta: https://beta.example.org/b
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.key_findings == 7
        assert res.recommendations == 4
        assert res.gaps == 2
        # Sources still derived from URL hostnames (model does not self-report).
        assert res.sources == 2

    def test_fenced_research_stats_partial_falls_back_per_field(self) -> None:
        """If the subagent only reports some fields in the JSON block, missing
        fields fall back to markdown derivation per-field — not all-or-nothing.
        """
        md = f"""
# Report

## Executive Summary
- Finding A.
- Finding B.

## Sources
- https://alpha.example.com/a — {_iso_days_ago(5)}

```json
{{"research_stats": {{"recommendations": 3}}}}
```
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.key_findings == 2  # from markdown
        assert res.recommendations == 3  # from JSON
        assert res.sources == 1  # from URLs
        assert res.freshness == "<=7d"  # from URL date

    def test_fenced_research_stats_invalid_json_does_not_break_fallback(
        self,
    ) -> None:
        md = """
## Executive Summary
- One.
- Two.

```json
{this is not: valid json
```
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.key_findings == 2  # markdown fallback still works

    def test_research_stats_from_task_outputs_when_split_strips_fenced(
        self,
    ) -> None:
        """Real adapter flow: deep-research compiled subagent emits the full
        report including WRAPUP + fenced JSON, but the conclusion split
        (`split_subagent_wrapup_and_full`) keeps only the body before WRAPUP.
        We therefore pass `task_outputs` (raw) **and** `report_markdown` (split
        prefix) to `derive_research_meta`; stats must come from task_outputs.
        """
        full_subagent_output = """
# 深度调研报告

## 引言
内容很多。

## 主要发现
- 发现 A。
- 发现 B。

## SM_SUBAGENT_WRAPUP
本次研究覆盖了 ...

```json
{"research_stats": {"keyFindings": 5, "recommendations": 2, "gaps": 1}}
```
"""
        # Conclusion body: WRAPUP and everything after stripped (matches
        # actual adapter behaviour for compiled subagent finishes).
        conclusion_body = full_subagent_output.split("## SM_SUBAGENT_WRAPUP")[0]

        res = sm.derive_research_meta(
            report_markdown=conclusion_body,
            task_outputs=[full_subagent_output],
        )
        assert res is not None
        assert res.key_findings == 5
        assert res.recommendations == 2
        assert res.gaps == 1

    def test_research_stats_task_outputs_empty_falls_back_to_markdown(
        self,
    ) -> None:
        md = """
## Executive Summary
- A.
- B.
- C.
"""
        res = sm.derive_research_meta(
            report_markdown=md,
            task_outputs=[],
        )
        assert res is not None
        assert res.key_findings == 3

    def test_chinese_freeform_report_with_fenced_stats(self) -> None:
        """Real-world deep-research case: report fully in Chinese with no
        English alias-matching headings. Stats must still populate via JSON."""
        md = """
# 量子计算近期进展深度报告

## 引言
量子计算近年来取得了显著突破。

## 主要技术路线
内容很多。

## 总结与展望
未来值得关注的方向。

## SM_SUBAGENT_WRAPUP
本调研覆盖了 ...

```json
{"research_stats": {"keyFindings": 6, "recommendations": 3, "gaps": 1}}
```
"""
        res = sm.derive_research_meta(report_markdown=md)
        assert res is not None
        assert res.key_findings == 6
        assert res.recommendations == 3
        assert res.gaps == 1


# ---------------------------------------------------------------------------
# build_task_stats_meta  (A-01..A-03)
# ---------------------------------------------------------------------------


class TestBuildTaskStatsMeta:
    def test_security_roundtrip_dict(self) -> None:
        meta = sm.build_task_stats_meta(
            subagent_types=["web-security"],
            tools_used=["detect_web_attack", "yara_scan"],
            task_outputs=[],
            report_markdown="",
            security_findings_raw=[
                {"type": "web_shell", "severity": "high", "risk": 82}
            ],
        )
        assert meta == {
            "taskKind": "security",
            "security": {
                "severity": "high",
                "riskScore": 82,
                "actionable": {"total": 1, "critical": 0, "high": 1, "medium": 0},
                "threatClasses": ["web-shell"],
                "validation": ["static", "yara"],
            },
        }

    def test_research_roundtrip_dict(self) -> None:
        md = f"""
## Executive Summary
- One.
- Two.

## Sources
- https://alpha.example.com/a — {_iso_days_ago(20)}
"""
        meta = sm.build_task_stats_meta(
            subagent_types=["deep-research"],
            tools_used=[],
            task_outputs=[],
            report_markdown=md,
        )
        assert meta is not None
        assert meta["taskKind"] == "research"
        assert meta["research"]["keyFindings"] == 2
        assert meta["research"]["sources"] == 1
        assert meta["research"]["freshness"] == "<=30d"
        # Absent fields must NOT appear as null — they must be omitted.
        assert "recommendations" not in meta["research"]
        assert "gaps" not in meta["research"]

    def test_generic_task_returns_none(self) -> None:
        # A-03: no known subagent → no meta.
        assert (
            sm.build_task_stats_meta(
                subagent_types=["general-purpose"],
                tools_used=[],
                task_outputs=[],
                report_markdown="## whatever\n- a",
            )
            is None
        )

    def test_multi_subagent_outputs_aggregate_into_single_meta(self) -> None:
        """Multi-subagent run (parent dispatches web + email + binary in parallel):
        each subagent writes its own ``task()`` ToolMessage with a fenced
        ``findings`` block. The adapter aggregates them and derive_* must merge
        them into one stats payload (severity = max, classes = dedup, actionable
        = sum, validation = union).
        """
        web_report = """
# Web analysis
## SM_SUBAGENT_WRAPUP
Detected RCE.
```json
{"findings": [
  {"type": "rce", "severity": "critical", "risk": 95},
  {"type": "xss", "severity": "high", "risk": 70}
]}
```
"""
        email_report = """
# Email analysis
## SM_SUBAGENT_WRAPUP
Phishing detected.
```json
{"findings": [
  {"type": "phishing", "severity": "high", "risk": 75}
]}
```
"""
        binary_report = """
# Binary analysis
## SM_SUBAGENT_WRAPUP
Suspicious packer.
```json
{"findings": [
  {"type": "malware", "severity": "medium", "risk": 55}
]}
```
"""
        # Parent agent's own conclusion text — note it ALSO contains a fenced
        # JSON block. This must NOT be double-counted because security path
        # ignores report_md.
        parent_conclusion = """
# Final report
Combined risk is critical (RCE).
```json
{"findings": [
  {"type": "rce", "severity": "critical", "risk": 99}
]}
```
"""
        meta = sm.build_task_stats_meta(
            subagent_types=["web-security", "email-security", "binary-analysis"],
            tools_used=["detect_web_attack", "parse_eml", "yara_scan", "run_in_sandbox"],
            task_outputs=[web_report, email_report, binary_report],
            report_markdown=parent_conclusion,
            security_findings_raw=None,
        )
        assert meta is not None
        sec = meta["security"]
        # Severity: critical (from web rce); riskScore: max across subagents
        # = 95 (parent's 99 must NOT bleed in).
        assert sec["severity"] == "critical"
        assert sec["riskScore"] == 95
        # Threat classes deduped + risk-desc: rce(95) > phishing(75) > xss(70) > malware(55)
        assert sec["threatClasses"] == ["rce", "phishing", "xss", "malware"]
        # Actionable: 1 critical + 2 high + 1 medium = 4 total. Parent's
        # critical/99 must NOT be counted.
        assert sec["actionable"] == {
            "total": 4,
            "critical": 1,
            "high": 2,
            "medium": 1,
        }
        # Validation: union across subagents, canonical order.
        assert sec["validation"] == ["static", "yara", "sandbox"]

    def test_parent_conclusion_fenced_json_does_not_leak_into_security_meta(
        self,
    ) -> None:
        """Defense-in-depth: even if parent agent decides to emit a fenced JSON
        in its conclusion (e.g. mimicking subagent format), security path must
        ignore it because `report_md` is research-only."""
        parent_only = '```json\n{"findings": [{"type": "rce", "severity": "critical"}]}\n```'
        meta = sm.build_task_stats_meta(
            subagent_types=["web-security"],
            tools_used=[],
            task_outputs=[],  # no subagent ran
            report_markdown=parent_only,  # parent's text only
            security_findings_raw=None,
        )
        # Severity collapses to info because no findings reachable from
        # task_outputs / tool results — parent text is intentionally ignored.
        assert meta == {
            "taskKind": "security",
            "security": {"severity": "info"},
        }

    def test_end_to_end_subagent_report_with_appendix_findings(self) -> None:
        """End-to-end: a security subagent report shaped per
        `subagent_output_appendix.py` should populate every applicable chip.
        """
        report_md = """
# Web Security Analysis

## Findings
The uploaded file contains an obfuscated PHP web shell (eval+base64).
A second-order SQL injection is reachable via /search?q=.

## SM_SUBAGENT_WRAPUP
- Parsed PHP, ran YARA, executed in sandbox.
- Found 1 web shell + 1 SQLi.
- Recommend immediate quarantine.

```json
{
  "findings": [
    {"type": "web_shell", "severity": "critical", "risk": 95, "evidence": "phpunit/util.php"},
    {"type": "sqli", "severity": "high", "risk": 80, "evidence": "/search?q="}
  ]
}
```
"""
        meta = sm.build_task_stats_meta(
            subagent_types=["web-security"],
            tools_used=["parse_php", "yara_scan", "run_in_sandbox"],
            task_outputs=[report_md],
            report_markdown=report_md,
            security_findings_raw=None,  # adapter did not pre-collect
        )
        assert meta == {
            "taskKind": "security",
            "security": {
                "severity": "critical",
                "riskScore": 95,
                "actionable": {"total": 2, "critical": 1, "high": 1, "medium": 0},
                "threatClasses": ["web-shell", "sqli"],
                "validation": ["static", "yara", "sandbox"],
            },
        }

    def test_security_with_no_signals_still_emits_severity(self) -> None:
        """Edge: bar should still render with at least severity (info) + empty validation."""
        meta = sm.build_task_stats_meta(
            subagent_types=["web-security"],
            tools_used=[],
            task_outputs=[],
            report_markdown="",
        )
        assert meta == {
            "taskKind": "security",
            "security": {"severity": "info"},
        }


# ---------------------------------------------------------------------------
# N-02: malformed input must never raise
# ---------------------------------------------------------------------------


class TestNoRaiseOnMalformed:
    def test_none_inputs_return_none(self) -> None:
        assert (
            sm.build_task_stats_meta(
                subagent_types=[],
                tools_used=[],
                task_outputs=[],
                report_markdown="",
            )
            is None
        )

    def test_non_iterable_subagent_types(self) -> None:
        # Must gracefully return None, not raise.
        assert sm.build_task_stats_meta(  # type: ignore[arg-type]
            subagent_types=123,  # wrong type
            tools_used=[],
            task_outputs=[],
            report_markdown="",
        ) is None

    @pytest.mark.parametrize(
        "findings",
        [
            [{"severity": None}],
            [{"severity": 42}],
            [{"risk": "not-a-number"}],
            [{"type": None}],
            [None, "string", 42],  # mixed garbage
        ],
    )
    def test_malformed_findings_no_raise(self, findings: list[object]) -> None:
        meta = sm.build_task_stats_meta(
            subagent_types=["web-security"],
            tools_used=[],
            task_outputs=[],
            report_markdown="",
            security_findings_raw=findings,  # type: ignore[arg-type]
        )
        assert meta is not None
        assert meta["taskKind"] == "security"

    def test_malformed_markdown_no_raise(self) -> None:
        meta = sm.build_task_stats_meta(
            subagent_types=["deep-research"],
            tools_used=[],
            task_outputs=[],
            report_markdown="##\n- \n- ```unterminated",
        )
        # Either None (no derivable fields) or a dict with research key missing.
        assert meta is None or meta.get("taskKind") == "research"
