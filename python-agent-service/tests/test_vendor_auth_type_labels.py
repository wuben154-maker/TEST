"""Tests for vendor auth type display labels (LABELS.md + labels.py)."""

from app.parsers import labels


def test_vendor_auth_basic_zh_is_human_readable():
    assert labels.get_vendor_auth_type_label("basic", "zh") == "用户名和密码"


def test_vendor_auth_api_key_en():
    assert labels.get_vendor_auth_type_label("api_key", "en") == "API key"


def test_vendor_auth_unknown_code_returns_code():
    assert labels.get_vendor_auth_type_label("unknown_future_type", "zh") == "unknown_future_type"


def test_vendor_auth_types_dict_contains_basic():
    d = labels.get_vendor_auth_types_dict("zh")
    assert d["basic"] == "用户名和密码"
    assert "oauth2" in d


def test_reload_labels_clears_vendor_auth_cache():
    labels.get_vendor_auth_type_labels()
    labels.reload_labels()
    labels.get_vendor_auth_type_labels()
    assert labels.get_vendor_auth_type_label("basic", "zh") == "用户名和密码"
