"""Tool presentation registry tests."""

from pathlib import Path

import app.sse.tool_presentation as tp
from app.sse.tool_presentation import (
    DEFAULT_TOOL_PRESENTATION,
    attach_tool_presentation,
    clear_tool_registry_cache,
    get_tool_rule,
    resolve_tool_presentation,
    should_emit_tool_output,
)


def test_known_write_todos_task():
    p, c, known = resolve_tool_presentation("write_todos")
    assert known and p == "task" and c is None
    rule = get_tool_rule("write_todos")
    assert rule is not None and rule.category == "system"


def test_known_read_file_action():
    p, c, known = resolve_tool_presentation("read_file")
    assert known and p == "action"


def test_prefix_internal_defaults_state():
    p, c, known = resolve_tool_presentation("internal_foo")
    assert known and p == "state"


def test_prefix_hitl_defaults_state():
    p, c, known = resolve_tool_presentation("hitl_choice")
    assert known and p == "state"


def test_unknown_uses_default_and_not_known():
    p, c, known = resolve_tool_presentation("totally_new_tool_xyz")
    assert not known
    assert p == DEFAULT_TOOL_PRESENTATION
    assert c is None


def test_attach_tool_call_mutates():
    ev = {"type": "tool_call", "id": "1", "toolName": "read_file"}
    attach_tool_presentation(ev)
    assert ev["toolPresentation"] == "action"
    assert "parameterControl" not in ev

    ev2 = {"type": "tool_call", "id": "2", "toolName": "brand_new_unlisted"}
    attach_tool_presentation(ev2)
    assert ev2["toolPresentation"] == DEFAULT_TOOL_PRESENTATION


def test_attach_tool_sse_name_rewrites_outbound_tool_name():
    ev_call = {"type": "tool_call", "id": "x", "toolName": "web_search_deep_research"}
    attach_tool_presentation(ev_call)
    assert ev_call["toolName"] == "web_searchs"
    assert ev_call["toolPresentation"] == "action"
    ev_res = {"type": "tool_result", "id": "x", "toolName": "web_search_deep_research"}
    attach_tool_presentation(ev_res)
    assert ev_res["toolName"] == "web_searchs"


def test_attach_skips_non_tool_events():
    ev = {"type": "reasoning", "id": "r", "content": "x"}
    attach_tool_presentation(ev)
    assert "toolPresentation" not in ev


def test_deep_research_tools_presentation():
    for name in ("think_tool", "ResearchComplete", "ResearchQuestion"):
        p, c, known = resolve_tool_presentation(name)
        assert known and p == "state" and c is None, name
        ev = {"type": "tool_call", "id": "x", "toolName": name}
        attach_tool_presentation(ev)
        assert ev["toolPresentation"] == "state", name

    p_cr, c_cr, known_cr = resolve_tool_presentation("ConductResearch")
    assert known_cr and p_cr == "research_task" and c_cr is None
    ev_cr = {"type": "tool_call", "id": "x", "toolName": "ConductResearch"}
    attach_tool_presentation(ev_cr)
    assert ev_cr["toolPresentation"] == "research_task"

    assert should_emit_tool_output("ResearchQuestion") is False


def test_binary_analysis_subagent_tools_are_known():
    for name in ("file_identify", "evidence_chain", "document_extract"):
        p, c, known = resolve_tool_presentation(name)
        assert known and p == "action" and c is None, name
        ev = {"type": "tool_call", "id": "x", "toolName": name}
        attach_tool_presentation(ev)
        assert ev["toolPresentation"] == "action", name


def test_should_emit_tool_output_read_file_false():
    assert should_emit_tool_output("read_file") is False


def test_should_emit_tool_output_web_search_true():
    assert should_emit_tool_output("web_search") is True


def test_should_emit_tool_output_unknown_true():
    assert should_emit_tool_output("some_new_tool") is True


def test_tiered_yaml_sets_tool_categories(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
system_tools:
  read_file:
    presentation: action
    emit_output: false
common_tools:
  extract_iocs:
    enabled: true
    presentation: action
    emit_output: true
subagent_tools:
  detect_web_attack:
    enabled: true
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    rf = get_tool_rule("read_file")
    ioc = get_tool_rule("extract_iocs")
    web = get_tool_rule("detect_web_attack")
    assert rf is not None and rf.category == "system"
    assert ioc is not None and ioc.category == "common"
    assert web is not None and web.category == "subagent"


def test_hot_reload_from_yaml(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  read_file:
    presentation: action
    emit_output: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    assert should_emit_tool_output("read_file") is False

    cfg.write_text(
        """
tools:
  read_file:
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    clear_tool_registry_cache()

    assert should_emit_tool_output("read_file") is True


def test_legacy_flat_tools_yaml_has_no_category(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  read_file:
    presentation: action
    emit_output: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()
    rf = get_tool_rule("read_file")
    assert rf is not None and rf.category is None
