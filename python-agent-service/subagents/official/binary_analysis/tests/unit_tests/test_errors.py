"""Tests for binary_analysis.errors — C1-AC1."""

import pytest

from errors import (
    BinaryAnalysisError,
    BudgetExceeded,
    EntryFormatUnsupported,
    LlmNetworkError,
    LlmRateLimit,
    LlmSchemaError,
    LlmUnrecoverable,
    SandboxCreateTimeout,
    SandboxExecFailed,
    SandboxNetworkError,
    SandboxUnavailable,
    SandboxUnrecoverable,
    StateCorruption,
    ToolCrash,
    ToolSchemaInvalid,
    ToolTimeout,
    ToolUnavailable,
)

ALL_ERROR_CLASSES = [
    EntryFormatUnsupported,
    ToolUnavailable,
    ToolTimeout,
    ToolCrash,
    ToolSchemaInvalid,
    SandboxUnavailable,
    SandboxCreateTimeout,
    SandboxNetworkError,
    SandboxExecFailed,
    SandboxUnrecoverable,
    LlmNetworkError,
    LlmRateLimit,
    LlmSchemaError,
    LlmUnrecoverable,
    BudgetExceeded,
    StateCorruption,
]

EXPECTED_ERROR_CODES = {
    EntryFormatUnsupported: "ENTRY_FORMAT_UNSUPPORTED",
    ToolUnavailable: "TOOL_UNAVAILABLE",
    ToolTimeout: "TOOL_TIMEOUT",
    ToolCrash: "TOOL_CRASH",
    ToolSchemaInvalid: "TOOL_SCHEMA_INVALID",
    SandboxUnavailable: "SANDBOX_UNAVAILABLE",
    SandboxCreateTimeout: "SANDBOX_CREATE_TIMEOUT",
    SandboxNetworkError: "SANDBOX_NETWORK_ERROR",
    SandboxExecFailed: "SANDBOX_EXEC_FAILED",
    SandboxUnrecoverable: "SANDBOX_UNRECOVERABLE",
    LlmNetworkError: "LLM_NETWORK_ERROR",
    LlmRateLimit: "LLM_RATE_LIMIT",
    LlmSchemaError: "LLM_SCHEMA_ERROR",
    LlmUnrecoverable: "LLM_UNRECOVERABLE",
    BudgetExceeded: "BUDGET_EXCEEDED",
    StateCorruption: "STATE_CORRUPTION",
}


@pytest.mark.parametrize("cls", ALL_ERROR_CLASSES)
def test_is_binary_analysis_error(cls):
    err = cls("test message")
    assert isinstance(err, BinaryAnalysisError)


@pytest.mark.parametrize("cls", ALL_ERROR_CLASSES)
def test_is_exception(cls):
    err = cls("test message")
    assert isinstance(err, Exception)


@pytest.mark.parametrize("cls, expected_code", EXPECTED_ERROR_CODES.items())
def test_error_code(cls, expected_code):
    err = cls("test message")
    assert err.error_code == expected_code


@pytest.mark.parametrize("cls", ALL_ERROR_CLASSES)
def test_to_dict_keys(cls):
    err = cls("some msg")
    d = err.to_dict()
    assert "error_code" in d
    assert "message" in d
    assert "details" in d


@pytest.mark.parametrize("cls", ALL_ERROR_CLASSES)
def test_to_dict_values(cls):
    err = cls("some msg", details={"foo": "bar"})
    d = err.to_dict()
    assert d["message"] == "some msg"
    assert d["details"] == {"foo": "bar"}
    assert d["error_code"] == cls.error_code


@pytest.mark.parametrize("cls", ALL_ERROR_CLASSES)
def test_to_dict_is_serialisable(cls):
    import json

    err = cls("serialise me", details={"x": 1})
    json.dumps(err.to_dict())  # must not raise


def test_base_class_default_error_code():
    err = BinaryAnalysisError("base")
    assert err.error_code == "BINARY_ANALYSIS_ERROR"


def test_details_default_empty():
    err = EntryFormatUnsupported("no details")
    assert err.details == {}


def test_count_of_error_classes():
    assert len(ALL_ERROR_CLASSES) == 16


def test_can_catch_as_exception():
    with pytest.raises(Exception):
        raise ToolTimeout("timed out")


def test_can_catch_as_base_class():
    with pytest.raises(BinaryAnalysisError):
        raise SandboxUnrecoverable("unrecoverable")
