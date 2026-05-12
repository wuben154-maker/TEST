"""Tests for final_message_split (SM_TASK_DIGEST / SM_FULL_REPORT)."""

from app.parsers.final_message_split import (
    DIGEST_HEADING,
    REPORT_HEADING,
    SUBAGENT_FULL_HEADING,
    SUBAGENT_STATS_PAYLOAD_HEADING,
    SUBAGENT_WRAPUP_HEADING,
    heuristic_digest_and_report,
    heuristic_subagent_sse_visible,
    split_final_assistant_message,
    split_subagent_wrapup_and_full,
    strip_conclusion_machine_tails,
    strip_digest_tail,
    strip_leading_preface_before_cjk_report_body,
    subagent_output_metrics,
    subagent_sse_visible_text,
)


def test_split_ok_basic_legacy_order():
    """Legacy order: DIGEST first, REPORT second — still accepted."""
    text = f"""{DIGEST_HEADING}

Two-line digest here.

{REPORT_HEADING}

# Report

Full body.
"""
    d, r = split_final_assistant_message(text)
    assert d == "Two-line digest here."
    assert r == "# Report\n\nFull body."


def test_split_ok_new_order_report_first():
    """New preferred order: REPORT first, DIGEST second."""
    text = f"""{REPORT_HEADING}

# Full Report

Detailed findings here.

{DIGEST_HEADING}

Short digest after the report.
"""
    d, r = split_final_assistant_message(text)
    assert d == "Short digest after the report."
    assert r == "# Full Report\n\nDetailed findings here."


def test_split_ok_json_report():
    text = f"""{DIGEST_HEADING}

Brief.

{REPORT_HEADING}

{{"title": "x", "summary": "y"}}
"""
    d, r = split_final_assistant_message(text)
    assert d == "Brief."
    assert '"title"' in r


def test_split_ok_json_report_new_order():
    """New order with JSON body in report section."""
    text = f"""{REPORT_HEADING}

{{"title": "x", "summary": "y"}}

{DIGEST_HEADING}

Brief.
"""
    d, r = split_final_assistant_message(text)
    assert d == "Brief."
    assert '"title"' in r


def test_split_fail_missing_report():
    text = f"""{DIGEST_HEADING}

Only digest.
"""
    assert split_final_assistant_message(text) == (None, None)


def test_split_fail_empty_digest():
    text = f"""{DIGEST_HEADING}

{REPORT_HEADING}

Only report.
"""
    assert split_final_assistant_message(text) == (None, None)


def test_heuristic_two_paragraphs():
    d, r = heuristic_digest_and_report("Short intro.\n\nLong\n\nsecond part.")
    assert d == "Short intro."
    assert r == "Long\n\nsecond part."


def test_heuristic_single_block_truncates():
    long_one = "x" * 700
    d, r = heuristic_digest_and_report(long_one)
    assert d.endswith("...")
    assert len(d) < len(long_one)
    assert r == long_one


def test_heuristic_short_single_block():
    d, r = heuristic_digest_and_report("Only one paragraph.")
    assert d == "Only one paragraph."
    assert r == "Only one paragraph."


def test_split_subagent_wrapup_ok():
    text = f"""{SUBAGENT_WRAPUP_HEADING}

Did X and Y. Found Z.

{SUBAGENT_FULL_HEADING}

# Long report

Many details here.
"""
    w, f = split_subagent_wrapup_and_full(text)
    assert w == "Did X and Y. Found Z."
    assert f == "# Long report\n\nMany details here."


def test_split_subagent_wrapup_fail_wrong_order():
    text = f"""{SUBAGENT_FULL_HEADING}

Body.

{SUBAGENT_WRAPUP_HEADING}

Late.
"""
    assert split_subagent_wrapup_and_full(text) == (None, None)


def test_split_body_first_main_report_then_wrapup_only():
    long_body = "# Title\n\n" + ("paragraph line\n" * 80)
    text = f"{long_body}\n\n{SUBAGENT_WRAPUP_HEADING}\n\nShort UI preview only.\n"
    w, f = split_subagent_wrapup_and_full(text)
    assert w == "Short UI preview only."
    assert f.strip().startswith("# Title")
    assert "paragraph line" in f


def test_split_body_first_ignores_legacy_short_full_section():
    """Long report before WRAPUP; legacy FULL_REPORT holds only a short blurb (model mistake)."""
    long_prefix = "# Real report\n\n" + ("section\n" * 100)
    short_full = "Tiny executive summary only."
    text = (
        f"{long_prefix}\n\n{SUBAGENT_WRAPUP_HEADING}\n\nWrap.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\n{short_full}"
    )
    w, f = split_subagent_wrapup_and_full(text)
    assert w == "Wrap."
    assert short_full not in f
    assert long_prefix.strip() in f or f.strip() == long_prefix.strip()


def test_subagent_sse_visible_text_prefers_wrapup():
    full = f"""{SUBAGENT_WRAPUP_HEADING}

Short wrap.

{SUBAGENT_FULL_HEADING}

{"x" * 2000}
"""
    assert subagent_sse_visible_text(full) == "Short wrap."


def test_subagent_sse_visible_text_heuristic_first_paragraph():
    long = "x" * 1200
    text = f"First para only.\n\n{long}"
    out = subagent_sse_visible_text(text)
    assert out == "First para only."


def test_heuristic_subagent_sse_visible_truncates_single_block():
    blob = "y" * 1200
    out = heuristic_subagent_sse_visible(blob)
    assert out.endswith("...")
    assert len(out) < len(blob)


def test_subagent_output_metrics_empty():
    m = subagent_output_metrics("")
    assert m["final_text_char_count"] == 0
    assert m["first_wrapup_heading_found"] is False
    assert m["content_before_first_wrapup_char_count"] is None
    assert m["subagent_anchors_parsed"] is False


def test_subagent_output_metrics_well_formed():
    long_body = "# Report\n\n" + ("paragraph\n" * 20)
    text = f"""{SUBAGENT_WRAPUP_HEADING}

Short wrap.

{SUBAGENT_FULL_HEADING}

{long_body}
"""
    m = subagent_output_metrics(text)
    assert m["first_wrapup_heading_found"] is True
    assert m["content_before_first_wrapup_char_count"] == 0
    assert m["subagent_anchors_parsed"] is True
    assert m["subagent_wrapup_char_count"] == len("Short wrap.")
    assert m["subagent_full_report_char_count"] == len(long_body.strip())


def test_subagent_output_metrics_misplaced_long_report_before_anchors():
    """Body-first: prefix is the parsed full report; legacy FULL blurb is ignored."""
    long_prefix = "# Real report\n\n" + ("section\n" * 100)
    short_full = "Tiny executive summary only."
    text = (
        f"{long_prefix}\n\n{SUBAGENT_WRAPUP_HEADING}\n\nWrap.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\n{short_full}"
    )
    m = subagent_output_metrics(text)
    expected_before = (long_prefix + "\n\n").strip()
    assert m["content_before_first_wrapup_char_count"] == len(expected_before)
    assert m["subagent_anchors_parsed"] is True
    assert m["subagent_full_report_char_count"] == len(expected_before)
    assert m["subagent_wrapup_char_count"] == len("Wrap.")


def test_strip_digest_tail_removes_trailing_digest():
    body = "### Summary\nFull analysis content here."
    text = f"{body}\n\n{DIGEST_HEADING}\nShort digest that should be stripped."
    assert strip_digest_tail(text) == body


def test_strip_digest_tail_noop_without_digest():
    text = "### Report\n\nJust a normal conclusion."
    assert strip_digest_tail(text) == text


def test_strip_digest_tail_empty():
    assert strip_digest_tail("") == ""
    assert strip_digest_tail(None) is None


def test_strip_cjk_preface_removes_english_cot():
    raw = """Analyzing SOC Architecture

I'm currently focused on dissecting the integration of EDR and SIEM.

大规模SOC环境下的自动化分诊实施方案研究报告
在每日告警量达到10万级别的超大规模安全运营中心（SOC）中，传统的依靠人工逐一审计告警的模式已无法维系。"""
    out = strip_leading_preface_before_cjk_report_body(raw)
    assert out.startswith("大规模SOC")
    assert "Analyzing SOC" not in out


def test_strip_cjk_preface_noop_for_english_only():
    en = "Hello world.\n\nSecond paragraph here."
    assert strip_leading_preface_before_cjk_report_body(en) == en.strip()


# --- SM_STATS_PAYLOAD sentinel: keep machine-only stats JSON out of chat UI ---


def test_subagent_stats_payload_heading_constant_value():
    """Locks the public constant the prompts must emit verbatim."""
    assert SUBAGENT_STATS_PAYLOAD_HEADING == "### SM_STATS_PAYLOAD"


def test_subagent_sse_visible_text_strips_stats_payload_block_S01():
    """Wrapup containing the sentinel + fenced JSON: chat sees prose only."""
    long_body = "# Title\n\n" + ("paragraph line\n" * 80)
    wrapup_prose = "Did X and Y. Found Z."
    text = (
        f"{long_body}\n\n"
        f"{SUBAGENT_WRAPUP_HEADING}\n\n"
        f"{wrapup_prose}\n\n"
        f"{SUBAGENT_STATS_PAYLOAD_HEADING}\n\n"
        '```json\n'
        '{"research_stats": {"keyFindings": 5, "recommendations": 2, "gaps": 1}}\n'
        '```\n'
    )
    out = subagent_sse_visible_text(text)
    assert out == wrapup_prose
    assert "SM_STATS_PAYLOAD" not in out
    assert "research_stats" not in out
    assert "```json" not in out


def test_subagent_sse_visible_text_no_sentinel_unchanged_S02():
    """No sentinel: behaviour identical to before — wrapup returned as-is."""
    long_body = "# Title\n\n" + ("paragraph line\n" * 80)
    wrapup_prose = "Wrap-up summary text."
    text = f"{long_body}\n\n{SUBAGENT_WRAPUP_HEADING}\n\n{wrapup_prose}\n"
    assert subagent_sse_visible_text(text) == wrapup_prose


def test_split_subagent_wrapup_full_body_unaffected_by_sentinel_S03():
    """Sentinel inside the *full body prefix* must not be stripped from the
    full report — only the WRAPUP-tail consumer (SSE/chat) trims it."""
    # Use a body that is itself substantial so body-first layout kicks in.
    full = (
        "# Final report\n\n"
        f"Some prose with an accidental {SUBAGENT_STATS_PAYLOAD_HEADING} marker inside.\n"
        + ("more body\n" * 80)
    )
    text = f"{full}\n\n{SUBAGENT_WRAPUP_HEADING}\n\nShort preview.\n"
    wrapup, full_report = split_subagent_wrapup_and_full(text)
    assert wrapup == "Short preview."
    assert full_report is not None
    assert SUBAGENT_STATS_PAYLOAD_HEADING in full_report  # body retained as-is


def test_subagent_sse_visible_text_strips_sentinel_in_classic_layout_S04():
    """Classic WRAPUP→FULL_REPORT layout: sentinel may sit between prose and FULL."""
    text = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\n"
        "Two-line preview.\n\n"
        f"{SUBAGENT_STATS_PAYLOAD_HEADING}\n\n"
        '```json\n{"findings": []}\n```\n\n'
        f"{SUBAGENT_FULL_HEADING}\n\nFull body for parent agent.\n"
    )
    out = subagent_sse_visible_text(text)
    assert out == "Two-line preview."
    assert "findings" not in out
    assert "SM_STATS_PAYLOAD" not in out


def test_subagent_sse_visible_text_strips_sentinel_in_wrapup_only_layout_S05():
    """Wrapup-only layout (no FULL_REPORT, no substantial body)."""
    text = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\n"
        "Short preview only.\n\n"
        f"{SUBAGENT_STATS_PAYLOAD_HEADING}\n\n"
        '```json\n{"research_stats": {"keyFindings": 3}}\n```\n'
    )
    out = subagent_sse_visible_text(text)
    assert "SM_STATS_PAYLOAD" not in out
    assert "research_stats" not in out
    assert "Short preview only." in out


# --- strip_conclusion_machine_tails: cleanse text destined for `conclusion.content` ---
#
# Background: when a subagent emits a body+sentinel+JSON tail without the
# canonical ``## SM_SUBAGENT_WRAPUP`` heading, ``split_subagent_wrapup_and_full``
# returns ``(None, None)`` and the adapter falls back to
# ``heuristic_digest_and_report``. That heuristic happily keeps the sentinel and
# the fenced JSON tail in the conclusion body, which then leaks into the chat
# UI as part of the streamed conclusion summary (user-reported regression on
# 2026-04-25). The new helper guarantees both machine tails (SM_TASK_DIGEST and
# SM_STATS_PAYLOAD) are cleaned in a single call before the value is forwarded
# to ``conclusion.content``.


def test_strip_conclusion_machine_tails_removes_stats_payload_tail_C01():
    body = (
        "围绕 Kimi K2.6 开展了 4 轮深度网络搜索...建议以辅助决策模式分阶段引入。\n\n"
        f"{SUBAGENT_STATS_PAYLOAD_HEADING}\n\n"
        '```json\n{"research_stats": {"keyFindings": 12}}\n```\n'
    )
    out = strip_conclusion_machine_tails(body)
    assert SUBAGENT_STATS_PAYLOAD_HEADING not in out
    assert "research_stats" not in out
    assert "```json" not in out
    assert "围绕 Kimi K2.6" in out
    assert out.endswith("分阶段引入。")


def test_strip_conclusion_machine_tails_removes_digest_tail_C02():
    body = (
        "Final report body paragraph one.\n\n"
        "Paragraph two.\n\n"
        f"{DIGEST_HEADING}\n\n"
        "- bullet 1\n- bullet 2\n"
    )
    out = strip_conclusion_machine_tails(body)
    assert DIGEST_HEADING not in out
    assert "bullet" not in out
    assert "Paragraph two." in out


def test_strip_conclusion_machine_tails_handles_both_tails_in_either_order_C03():
    body = (
        "Body line.\n\n"
        f"{SUBAGENT_STATS_PAYLOAD_HEADING}\n\n"
        '```json\n{"findings": []}\n```\n\n'
        f"{DIGEST_HEADING}\n\n- digest\n"
    )
    out = strip_conclusion_machine_tails(body)
    assert SUBAGENT_STATS_PAYLOAD_HEADING not in out
    assert DIGEST_HEADING not in out
    assert "findings" not in out
    assert "digest" not in out
    assert out.strip() == "Body line."

    flipped = (
        "Body line.\n\n"
        f"{DIGEST_HEADING}\n\n- digest\n\n"
        f"{SUBAGENT_STATS_PAYLOAD_HEADING}\n\n"
        '```json\n{"findings": []}\n```\n'
    )
    out2 = strip_conclusion_machine_tails(flipped)
    assert SUBAGENT_STATS_PAYLOAD_HEADING not in out2
    assert DIGEST_HEADING not in out2
    assert out2.strip() == "Body line."


def test_strip_conclusion_machine_tails_noop_when_no_tails_C04():
    plain = "# Report\n\nFull body, nothing to strip.\n"
    assert strip_conclusion_machine_tails(plain).rstrip() == plain.rstrip()


def test_strip_conclusion_machine_tails_handles_none_and_empty_C05():
    assert strip_conclusion_machine_tails("") == ""
    assert strip_conclusion_machine_tails(None) == None  # type: ignore[arg-type]
