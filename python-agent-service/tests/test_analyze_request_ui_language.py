"""AnalyzeRequest: ui_language vs legacy ``language`` merge (SSE labels locale)."""

from app.main import AnalyzeRequest


def test_language_only_sets_resolved_ui_locale():
    """Frontend sends ``language: en`` without ``ui_language`` — must not fall back to zh."""
    r = AnalyzeRequest.model_validate({"message": "hello", "language": "en"})
    resolved = (r.ui_language or r.language or "zh").strip()
    assert resolved == "en"


def test_ui_language_explicit_wins_over_language():
    r = AnalyzeRequest.model_validate(
        {"message": "hello", "ui_language": "ja", "language": "en"}
    )
    resolved = (r.ui_language or r.language or "zh").strip()
    assert resolved == "ja"


def test_neither_field_defaults_zh():
    r = AnalyzeRequest.model_validate({"message": "hello"})
    resolved = (r.ui_language or r.language or "zh").strip()
    assert resolved == "zh"
