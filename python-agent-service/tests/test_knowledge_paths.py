"""Tests for ``knowledge_paths`` layout and safe resolution."""

from pathlib import Path

import pytest
from app.config import Settings
from app.services.knowledge_paths import (
    knowledge_stored_filename,
    resolve_knowledge_file,
    user_knowledge_dir,
)


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    s = Settings(upload_dir=str(tmp_path / "uploads"), _env_file=None)  # type: ignore[call-arg]
    return s


def test_user_knowledge_dir_layout(tmp_settings: Settings, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_STORAGE_ROOT", raising=False)
    uid = "user-uuid-001"
    d = user_knowledge_dir(tmp_settings, uid)
    assert "knowledge" in d.parts
    assert "user-uuid-001" in str(d)


def test_stored_filename_with_title_segment(tmp_settings: Settings, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_STORAGE_ROOT", raising=False)
    name = knowledge_stored_filename("req-abc-123", "我的渗透测试报告")
    assert name.endswith(".docx")
    assert "req-abc-123" in name
    assert name.startswith("我的渗透测试报告")


def test_stored_filename_title_only_ascii():
    name = knowledge_stored_filename("mid-xyz", "Weekly Scan Report")
    assert "Weekly_Scan_Report-mid-xyz.docx" == name or "Weekly" in name


def test_title_segment_empty_fallback():
    assert knowledge_stored_filename("only-mid", "") == "report-only-mid.docx"
    assert knowledge_stored_filename("only-mid", None) == "report-only-mid.docx"


def test_resolve_rejects_traversal(tmp_settings: Settings):
    uid = "u1"
    p = resolve_knowledge_file(tmp_settings, uid, "../../../etc/passwd")
    assert p is None


def test_resolve_accepts_basenames(tmp_settings: Settings):
    uid = "u1"
    user_knowledge_dir(tmp_settings, uid)
    fn = "report-x.docx"
    path = Path(user_knowledge_dir(tmp_settings, uid)) / fn
    path.write_bytes(b"PK\x03\x04fake")
    got = resolve_knowledge_file(tmp_settings, uid, fn)
    assert got is not None
    assert got.is_file()
