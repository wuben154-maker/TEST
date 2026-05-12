from __future__ import annotations

import importlib
import json
from unittest.mock import MagicMock

import pytest

from app.agents.subagent_registry import (
    SubagentRegistryEntry,
    build_subagent_specs_from_registry,
    validate_compiled_builders_for_entries,
)


class _AttachmentResp:
    """Minimal download_files response stub for analyze_attachment tests."""

    def __init__(self, content: bytes) -> None:
        self.error = None
        self.content = content


def _fake_attachment_backend(content: bytes):
    class _Backend:
        def download_files(self, _paths):
            return [_AttachmentResp(content)]

    return _Backend()


def test_bundle_importable_via_package_path():
    pkg = importlib.import_module("subagents.official.email_security")
    assert hasattr(pkg, "__path__")
    assert any("email_security" in str(p) for p in pkg.__path__)


def test_email_security_tools_exports_backward_compatible_factories():
    tools_pkg = importlib.import_module("subagents.official.email_security.tools")

    expected = [
        "analyze_attachment",
        "analyze_binary",
        "analyze_html_attachment",
        "audit_office_macro",
        "audit_pdf",
        "detect_executable_format",
        "inspect_archive",
        "scan_attachment_second_pass",
    ]
    for name in expected:
        assert hasattr(tools_pkg, name), f"Missing tools export: {name}"

    assert getattr(tools_pkg.analyze_html_attachment, "name", None) == "analyze_html_attachment"


def test_validate_compiled_builders_rejects_unknown_compiled_id():
    entry = SubagentRegistryEntry(
        id="unknown-compiled",
        runtime="compiled",
        source="official",
        bundle_path="x",
        enabled=True,
    )
    with pytest.raises(RuntimeError, match="COMPILED_SUBAGENT_BUILDERS"):
        validate_compiled_builders_for_entries([entry])


def test_registry_email_security_without_backend_fails_for_required_bindings():
    with pytest.raises(RuntimeError, match="requires backend binding"):
        build_subagent_specs_from_registry()


def test_registry_email_security_tools_with_backend_factory():
    specs = build_subagent_specs_from_registry(backend_factory=lambda _rt: MagicMock())
    email = next(x for x in specs if x.get("name") == "email-security")
    assert "runnable" not in email
    assert email["skills"] == ["/subagent-skills/email-security/"]
    names = {getattr(t, "name", str(t)) for t in email["tools"]}
    assert "parse_eml" in names
    assert "scan_attachment_second_pass" in names
    assert "compute_risk_score" in names


def test_email_security_prompt_prefers_binary_analysis_for_attachments():
    specs = build_subagent_specs_from_registry(backend_factory=lambda _rt: MagicMock())
    email = next(x for x in specs if x.get("name") == "email-security")
    prompt = email["system_prompt"]

    assert 'task()` with `subagent_type="binary-analysis"`' in prompt
    assert "SHOULD delegate" in prompt
    assert "MUST delegate" in prompt
    assert "needs_binary_analysis=true" in prompt
    assert "PE/ELF/Mach-O" in prompt
    assert "Office, PDF, archive, disk image, script, or direct-execution" in prompt
    assert "attachments[i].file_path" in prompt
    assert "filename, content_type, sha256" in prompt
    assert "MUST NOT lower" in prompt
    assert "nested delegation fails" in prompt
    assert "unanalyzed_high_tier_count" in prompt


def test_bound_email_tools_hide_injected_backend_fields():
    specs = build_subagent_specs_from_registry(backend_factory=lambda _rt: MagicMock())
    email = next(x for x in specs if x.get("name") == "email-security")
    parse_eml_tool = next(t for t in email["tools"] if getattr(t, "name", "") == "parse_eml")
    fields = set(getattr(parse_eml_tool.args_schema, "model_fields", {}).keys())
    assert "file_path" in fields
    assert "backend_factory" not in fields
    assert "runtime" not in fields


def test_bound_parse_eml_executes_without_runtime():
    tools_pkg = importlib.import_module("subagents.official.email_security.tools")

    class _Resp:
        error = "file_not_found"
        content = None

    class _Backend:
        def download_files(self, _paths):
            return [_Resp()]

    bound_tool = tools_pkg.bind_backend(tools_pkg.parse_eml, lambda _rt: _Backend())
    out = bound_tool.func(file_path="/uploads/missing.eml")
    assert out["ok"] is False
    assert "file_not_found" in out["error"]


def test_safe_storage_basename_normalizes_copyright_and_replacement_char():
    h = importlib.import_module("subagents.official.email_security.tools._helpers")
    out = h._safe_storage_basename("\u00a92023MicrosoftCorporation.pdf")
    assert "\u00a9" not in out
    assert out.endswith(".pdf")
    assert "2023MicrosoftCorporation" in out
    out2 = h._safe_storage_basename("report\ufffdfinal.docx")
    assert "\ufffd" not in out2
    assert out2.endswith(".docx")


def test_normalize_path_accepts_workspace_ui_spelling():
    """UI-scrubbed ``workspace/...`` and ``/workspace/...`` must work for parse_eml."""
    h = importlib.import_module("subagents.official.email_security.tools._helpers")
    assert h._normalize_path("workspace/dfadfb14e921_sample-352.eml") == (
        "/workspace/dfadfb14e921_sample-352.eml"
    )
    assert h._normalize_path("/workspace/dfadfb14e921_sample-352.eml") == (
        "/workspace/dfadfb14e921_sample-352.eml"
    )
    assert h._normalize_path("/uploads/u_x/p_y/z.eml") == "/uploads/u_x/p_y/z.eml"


def test_list_uploaded_files_tool_lists_from_uploads_root():
    """Regression: legacy /uploaded listing omitted owner segment and broke parse_eml."""
    parse_eml_mod = importlib.import_module("subagents.official.email_security.tools.parse_eml")
    ls_paths: list[str] = []

    class _FakeBackend:
        def ls_info(self, path: str) -> list[dict[str, object]]:
            ls_paths.append(path)
            return []

    parse_eml_mod.list_uploaded_files.func(
        backend_factory=lambda _rt: _FakeBackend(),
        runtime=MagicMock(),
    )
    assert ls_paths == ["/uploads"]


# ---------------------------------------------------------------------------
# P0: analyze_attachment must surface needs_binary_analysis + attachment_tier
# for Tier1/Tier2 types so the email-security agent's MUST-delegate trigger
# fires regardless of the content-based risk verdict.
# ---------------------------------------------------------------------------


def _run_analyze_attachment(*, content: bytes, filename: str, content_type: str) -> dict:
    tools_pkg = importlib.import_module("subagents.official.email_security.tools")
    bound = tools_pkg.bind_backend(
        tools_pkg.analyze_attachment,
        lambda _rt: _fake_attachment_backend(content),
    )
    return bound.func(
        file_path=f"/uploads/u_test/{filename}",
        filename=filename,
        content_type=content_type,
    )


def test_analyze_attachment_marks_pdf_as_tier2_and_needs_binary_analysis():
    """A clean PDF body still produces needs_binary_analysis so the email
    agent's MUST-delegate-to-binary-analysis trigger fires (P0)."""
    out = _run_analyze_attachment(
        content=b"%PDF-1.4\n%clean body\n%%EOF\n",
        filename="invoice.pdf",
        content_type="application/pdf",
    )
    assert out.get("needs_binary_analysis") is True
    assert out.get("attachment_tier") == "tier2"


def test_analyze_attachment_marks_office_as_tier2_via_mime():
    """Office docs (.docx + officedocument MIME) must carry the tier2 signal
    even when audit_office_macro returns LOW."""
    out = _run_analyze_attachment(
        content=b"PK\x03\x04",
        filename="report.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    assert out.get("needs_binary_analysis") is True
    assert out.get("attachment_tier") == "tier2"


def test_analyze_attachment_marks_archive_as_tier2():
    """Archives must reach binary-analysis (Tier2 in the AGENT.md contract)."""
    out = _run_analyze_attachment(
        content=b"PK\x03\x04not-a-real-zip",
        filename="payload.zip",
        content_type="application/zip",
    )
    assert out.get("needs_binary_analysis") is True
    assert out.get("attachment_tier") == "tier2"


def test_analyze_attachment_marks_script_as_tier1():
    """Direct-execution scripts (.ps1) are Tier1 and must trigger delegation."""
    out = _run_analyze_attachment(
        content=b"Write-Host 'hi'\n",
        filename="setup.ps1",
        content_type="application/x-powershell",
    )
    assert out.get("needs_binary_analysis") is True
    assert out.get("attachment_tier") == "tier1"


def test_analyze_attachment_does_not_force_binary_analysis_for_tier3_html():
    """HTML is Tier3 (stealth) — SHOULD-delegate, not MUST. We must NOT
    set needs_binary_analysis=True purely from extension; the tag is
    reserved for Tier1/Tier2 to keep the prompt's MUST-delegate trigger
    semantically meaningful."""
    out = _run_analyze_attachment(
        content=b"<html><body>hi</body></html>",
        filename="page.html",
        content_type="text/html",
    )
    assert out.get("needs_binary_analysis") is not True
    assert out.get("attachment_tier") == "tier3"


# ---------------------------------------------------------------------------
# P1: compute_risk_score honors `unanalyzed_high_tier_count` — applies an
# uncertainty penalty AND floors the suggested verdict to SUSPICIOUS so a
# silently-deferred Tier1/Tier2 attachment cannot be reported as BENIGN.
# ---------------------------------------------------------------------------


def _baseline_findings(**overrides) -> str:
    base = {
        "auth": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
        "url_high_risk_count": 0,
        "url_medium_risk_count": 0,
        "attachment_risks": [],
        "social_engineering_score": 0,
        "prompt_injection_detected": False,
        "display_name_spoofing": False,
        "reply_to_mismatch": False,
        "mass_mailing_penalty": 0,
        "unanalyzed_high_tier_count": 0,
    }
    base.update(overrides)
    return json.dumps(base)


def test_compute_risk_score_zero_unanalyzed_does_not_floor():
    scoring = importlib.import_module("subagents.official.email_security.tools.scoring")
    out = scoring.compute_risk_score.func(findings=_baseline_findings())
    assert out["suggested_verdict"] == "BENIGN"
    assert out["risk_score"] < 30
    assert out["score_breakdown"]["unanalyzed_attachments"] == 0
    assert out["score_breakdown"]["unanalyzed_floor_applied"] is False
    assert out["score_breakdown"]["unanalyzed_high_tier_count"] == 0


def test_compute_risk_score_unanalyzed_high_tier_floors_to_suspicious():
    """Even a fully-clean email with one deferred Tier1/Tier2 attachment
    must surface as SUSPICIOUS so the deferred deep analysis is visible."""
    scoring = importlib.import_module("subagents.official.email_security.tools.scoring")
    out = scoring.compute_risk_score.func(
        findings=_baseline_findings(unanalyzed_high_tier_count=1)
    )
    assert out["risk_score"] >= 30
    assert out["suggested_verdict"] == "SUSPICIOUS"
    assert out["score_breakdown"]["unanalyzed_attachments"] == 8
    assert out["score_breakdown"]["unanalyzed_floor_applied"] is True
    assert out["score_breakdown"]["unanalyzed_high_tier_count"] == 1


def test_compute_risk_score_unanalyzed_penalty_caps_at_30():
    """Uncertainty alone must not be able to push verdict to MALICIOUS."""
    scoring = importlib.import_module("subagents.official.email_security.tools.scoring")
    out = scoring.compute_risk_score.func(
        findings=_baseline_findings(unanalyzed_high_tier_count=10)
    )
    assert out["score_breakdown"]["unanalyzed_attachments"] == 30
    # Cap of 30 with otherwise-clean signals stays below the MALICIOUS threshold (65).
    assert out["suggested_verdict"] in {"SUSPICIOUS", "BENIGN"}
    assert out["risk_score"] < 65


def test_compute_risk_score_negative_unanalyzed_clamped_to_zero():
    scoring = importlib.import_module("subagents.official.email_security.tools.scoring")
    out = scoring.compute_risk_score.func(
        findings=_baseline_findings(unanalyzed_high_tier_count=-5)
    )
    assert out["score_breakdown"]["unanalyzed_high_tier_count"] == 0
    assert out["score_breakdown"]["unanalyzed_attachments"] == 0
    assert out["score_breakdown"]["unanalyzed_floor_applied"] is False
