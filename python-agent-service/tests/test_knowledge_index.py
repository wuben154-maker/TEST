"""Tests for knowledge index metadata."""

from pathlib import Path

import pytest

from app.services.knowledge_index import (
    derive_display_name,
    entry_for_file,
    load_index,
    project_id_for_file,
    upsert_file_metadata,
)


def test_derive_display_name_prefers_report_title() -> None:
    assert (
        derive_display_name(
            "MyTitle-abc.docx",
            {"report_title": "Phishing triage", "project_id": None},
        )
        == "Phishing triage"
    )


def test_derive_display_name_fallback_filename() -> None:
    assert derive_display_name("report-xyz.docx", None) == "report-xyz"


@pytest.mark.parametrize(
    "report_title,project_id",
    [
        ("My report", "proj-uuid-1"),
        (None, None),
    ],
)
def test_upsert_roundtrip(
    tmp_path: Path, report_title: str | None, project_id: str | None
) -> None:
    fname = "report-m1.docx"
    upsert_file_metadata(
        tmp_path,
        filename=fname,
        message_id="m1",
        report_title=report_title,
        project_id=project_id,
        task_kind="security",
    )
    idx = load_index(tmp_path)
    e = entry_for_file(idx, fname)
    assert e is not None
    assert e.get("message_id") == "m1"
    assert e.get("task_kind") == "security"
    if report_title:
        assert e.get("report_title") == report_title
    else:
        assert e.get("report_title") in (None, "")
    assert project_id_for_file(e) == project_id
