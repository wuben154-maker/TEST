"""Unit tests for task() delegation envelope keys (nested subagent SSE)."""

from app._vendor.deepagents.middleware import subagents as sa


def test_merge_delegation_first_hop_sets_root_and_depth() -> None:
    out = sa._merge_task_delegation_into_invoke_cfg(  # noqa: SLF001
        {},
        current_task_tool_call_id="tc-main",
    )
    c = out["configurable"]
    assert c["delegation_depth"] == 1
    assert c["delegation_root_tool_call_id"] == "tc-main"
    assert "delegation_parent_tool_call_id" not in c


def test_merge_delegation_nested_increments_depth_and_parent() -> None:
    base = sa._merge_task_delegation_into_invoke_cfg(  # noqa: SLF001
        {},
        current_task_tool_call_id="tc-main",
    )
    nested = sa._merge_task_delegation_into_invoke_cfg(  # noqa: SLF001
        base,
        current_task_tool_call_id="tc-nested",
    )
    c = nested["configurable"]
    assert c["delegation_depth"] == 2
    assert c["delegation_root_tool_call_id"] == "tc-main"
    assert c["delegation_parent_tool_call_id"] == "tc-nested"


def test_delegation_tags_camel_case_for_sse() -> None:
    tags = sa._delegation_tags_from_configurable(  # noqa: SLF001
        {
            "delegation_depth": 2,
            "delegation_root_tool_call_id": "r1",
            "delegation_parent_tool_call_id": "p1",
        }
    )
    assert tags == {
        "delegationDepth": 2,
        "rootDelegationId": "r1",
        "parentToolCallId": "p1",
    }

    shallow = sa._delegation_tags_from_configurable(  # noqa: SLF001
        {
            "delegation_depth": 1,
            "delegation_root_tool_call_id": "r1",
        }
    )
    assert "parentToolCallId" not in shallow
    assert shallow["delegationDepth"] == 1
    assert shallow["rootDelegationId"] == "r1"
