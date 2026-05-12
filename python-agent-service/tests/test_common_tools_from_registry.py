"""Common / email / web / HITL factories read enabled/description from tool_presentation.yaml (legacy ``tools:`` in tests)."""

from pathlib import Path

import app.sse.tool_presentation as tp
from app.sse.tool_presentation import clear_tool_registry_cache, get_tool_rule
from app.tools.common.tools import create_common_tools
from subagents.official.email_security.tools.tools import create_email_tools
from subagents.official.web_security.tools.tools import create_web_tools
from app.tools.research_tools import create_research_tools


def test_get_tool_rule_enabled_description(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  extract_iocs:
    enabled: false
    description: "custom iocs desc"
    presentation: action
    emit_output: true
  decode_base64:
    enabled: true
    presentation: action
    emit_output: true
  decode_url:
    enabled: true
    presentation: action
    emit_output: true
  lookup_threat_intel:
    enabled: true
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    rule = get_tool_rule("extract_iocs")
    assert rule is not None
    assert rule.enabled is False
    assert rule.description == "custom iocs desc"


def test_create_common_tools_skips_disabled(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  extract_iocs:
    enabled: false
    presentation: action
    emit_output: true
  decode_base64:
    enabled: true
    presentation: action
    emit_output: true
  decode_url:
    enabled: true
    presentation: action
    emit_output: true
  lookup_threat_intel:
    enabled: true
    presentation: action
    emit_output: true
  request_user_input:
    enabled: true
    presentation: parameter
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    tools = create_common_tools(include_hitl=False)
    names = {t.name for t in tools}
    assert "extract_iocs" not in names
    assert "decode_base64" in names
    assert "decode_url" in names
    assert "lookup_threat_intel" in names


def test_create_common_tools_description_override(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  extract_iocs:
    enabled: true
    description: "YAML-driven IOC extractor"
    presentation: action
    emit_output: true
  decode_base64:
    enabled: true
    presentation: action
    emit_output: true
  decode_url:
    enabled: true
    presentation: action
    emit_output: true
  lookup_threat_intel:
    enabled: true
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    tools = create_common_tools(include_hitl=False)
    ext = next(t for t in tools if t.name == "extract_iocs")
    assert ext.description == "YAML-driven IOC extractor"


def test_create_common_tools_hitl_disabled_by_yaml(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  extract_iocs:
    enabled: true
    presentation: action
    emit_output: true
  decode_base64:
    enabled: true
    presentation: action
    emit_output: true
  decode_url:
    enabled: true
    presentation: action
    emit_output: true
  lookup_threat_intel:
    enabled: true
    presentation: action
    emit_output: true
  request_user_input:
    enabled: false
    presentation: parameter
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    tools = create_common_tools(include_hitl=True)
    names = {t.name for t in tools}
    assert "request_user_input" not in names


def test_create_email_tools_skips_disabled(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  analyze_email_headers:
    enabled: false
    presentation: action
    emit_output: true
  detect_phishing_indicators:
    enabled: true
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    tools = create_email_tools()
    names = {t.name for t in tools}
    assert "analyze_email_headers" not in names
    assert "detect_phishing_indicators" in names


def test_create_email_tools_description_override(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  analyze_email_headers:
    enabled: true
    description: "YAML email header analyzer"
    presentation: action
    emit_output: true
  detect_phishing_indicators:
    enabled: true
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    tools = create_email_tools()
    hdr = next(t for t in tools if t.name == "analyze_email_headers")
    assert hdr.description == "YAML email header analyzer"


def test_create_web_tools_skips_disabled(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  detect_web_attack:
    enabled: false
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    assert create_web_tools() == []


def test_create_research_tools_reads_description_from_yaml(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
common_tools:
  web_search:
    enabled: true
    description: "YAML web search blurb"
    presentation: action
    emit_output: true
  scrape_url:
    enabled: true
    presentation: action
    emit_output: true
  summarize_content:
    enabled: true
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    tools = create_research_tools()
    by_name = {t.name: t for t in tools}
    assert by_name["web_search"].description == "YAML web search blurb"


def test_create_research_tools_skips_disabled(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
common_tools:
  web_search:
    enabled: false
    presentation: action
    emit_output: true
  scrape_url:
    enabled: true
    presentation: action
    emit_output: true
  summarize_content:
    enabled: true
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    names = {t.name for t in create_research_tools()}
    assert "web_search" not in names
    assert "scrape_url" in names


def test_create_web_tools_description_override(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "tool_presentation.yaml"
    cfg.write_text(
        """
tools:
  write_todos:
    presentation: task
    emit_output: true
  detect_web_attack:
    enabled: true
    description: "YAML web attack scanner"
    presentation: action
    emit_output: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "_TOOL_REGISTRY_YAML_PATH", cfg)
    clear_tool_registry_cache()

    tools = create_web_tools()
    assert len(tools) == 1
    assert tools[0].description == "YAML web attack scanner"
