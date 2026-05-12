"""Elastic Security read-only API tools for SOC alert profile."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..api_service_config import load_api_service_config


class SocEsDetSearchAlertsInput(BaseModel):
    """Input schema for searching detection alerts."""

    query: dict[str, Any] = Field(
        default_factory=dict,
        description="Elasticsearch query body for detection alert search.",
    )


class SocEsDetGetRuleInput(BaseModel):
    """Input schema for retrieving one detection rule."""

    id: str | None = Field(default=None, description="Rule saved object id.")
    rule_id: str | None = Field(default=None, description="Rule stable rule_id.")


class SocEsDetFindRulesInput(BaseModel):
    """Input schema for listing detection rules."""

    page: int = Field(default=1, description="Page number.")
    per_page: int = Field(default=20, description="Items per page.")
    filter: str | None = Field(default=None, description="Optional KQL filter string.")
    sort_field: str | None = Field(default=None, description="Optional sort field.")
    sort_order: str | None = Field(default=None, description="Optional sort order.")


class SocEsCaseFindCasesInput(BaseModel):
    """Input schema for searching cases."""

    page: int = Field(default=1, description="Page number.")
    per_page: int = Field(default=20, description="Items per page.")
    sort_field: str | None = Field(default=None, description="Optional sort field.")
    sort_order: str | None = Field(default=None, description="Optional sort order.")
    status: str | None = Field(default=None, description="Optional case status filter.")


class SocEsCaseGetByIdInput(BaseModel):
    """Input schema for retrieving one case."""

    case_id: str = Field(description="Case id.")


class SocEsCaseActivityInput(BaseModel):
    """Input schema for querying case activity."""

    case_id: str = Field(description="Case id.")
    page: int = Field(default=1, description="Page number.")
    per_page: int = Field(default=20, description="Items per page.")


class SocEsExceptionsFindInput(BaseModel):
    """Input schema for querying exception lists."""

    page: int = Field(default=1, description="Page number.")
    per_page: int = Field(default=20, description="Items per page.")
    namespace_type: str = Field(default="single", description="single or agnostic.")
    filter: str | None = Field(default=None, description="Optional KQL filter string.")


class SocEsExceptionsFindItemsInput(BaseModel):
    """Input schema for querying exception list items."""

    page: int = Field(default=1, description="Page number.")
    per_page: int = Field(default=20, description="Items per page.")
    list_id: str | None = Field(default=None, description="Optional exception list id.")
    namespace_type: str = Field(default="single", description="single or agnostic.")
    filter: str | None = Field(default=None, description="Optional KQL filter string.")


class SocEsExceptionsSummaryInput(BaseModel):
    """Input schema for reading exception list summary."""

    namespace_type: str = Field(default="single", description="single or agnostic.")


class SocEsListsReadInput(BaseModel):
    """Input schema for reading one list container."""

    id: str | None = Field(default=None, description="List SO id.")
    list_id: str | None = Field(default=None, description="List stable list_id.")
    namespace_type: str = Field(default="single", description="single or agnostic.")


class SocEsListsFindItemsInput(BaseModel):
    """Input schema for querying list items."""

    page: int = Field(default=1, description="Page number.")
    per_page: int = Field(default=20, description="Items per page.")
    list_id: str | None = Field(default=None, description="Optional list_id filter.")
    namespace_type: str = Field(default="single", description="single or agnostic.")
    filter: str | None = Field(default=None, description="Optional KQL filter string.")


def _simulated_payload(provider: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"simulated": True, "provider": provider, **detail}


def _es_headers(api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "kbn-xsrf": "kibana",
        "Accept": "application/json",
    }
    token = api_key.strip()
    if token:
        headers["Authorization"] = token if " " in token else f"ApiKey {token}"
    return headers


async def _es_request(
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    svc = load_api_service_config("elastic_security_api")
    if not svc.enabled or not svc.base_url:
        return _simulated_payload(
            "elastic_security",
            {
                "method": method,
                "path": path,
                "params": params or {},
                "note": "elastic_security_api not configured/enabled.",
            },
        )
    url = f"{svc.base_url}{path}"
    headers = _es_headers(svc.api_key)
    if body is not None:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=float(svc.timeout)) as client:
        try:
            resp = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=body,
            )
            resp.raise_for_status()
            return {
                "provider": "elastic_security",
                "method": method.upper(),
                "path": path,
                "data": resp.json(),
            }
        except Exception as exc:
            return {
                "provider": "elastic_security",
                "method": method.upper(),
                "path": path,
                "error": str(exc),
            }


def _compact_params(**kwargs: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


async def soc_es_det_search_alerts(query: dict[str, Any]) -> dict[str, Any]:
    """Find and aggregate detection alerts."""
    return await _es_request(
        method="POST",
        path="/api/detection_engine/signals/search",
        body=query or {},
    )


async def soc_es_det_get_rule(
    id: str | None = None,
    rule_id: str | None = None,
) -> dict[str, Any]:
    """Retrieve one detection rule."""
    params = _compact_params(id=id, rule_id=rule_id)
    return await _es_request(
        method="GET",
        path="/api/detection_engine/rules",
        params=params,
    )


async def soc_es_det_find_rules(
    page: int = 1,
    per_page: int = 20,
    filter: str | None = None,
    sort_field: str | None = None,
    sort_order: str | None = None,
) -> dict[str, Any]:
    """List detection rules."""
    params = _compact_params(
        page=page,
        per_page=per_page,
        filter=filter,
        sort_field=sort_field,
        sort_order=sort_order,
    )
    return await _es_request(
        method="GET",
        path="/api/detection_engine/rules/_find",
        params=params,
    )


async def soc_es_det_read_tags() -> dict[str, Any]:
    """List all detection rule tags."""
    return await _es_request(method="GET", path="/api/detection_engine/tags")


async def soc_es_case_find_cases(
    page: int = 1,
    per_page: int = 20,
    sort_field: str | None = None,
    sort_order: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Search cases."""
    params = _compact_params(
        page=page,
        per_page=per_page,
        sortField=sort_field,
        sortOrder=sort_order,
        status=status,
    )
    return await _es_request(method="GET", path="/api/cases/_find", params=params)


async def soc_es_case_get_case(case_id: str) -> dict[str, Any]:
    """Get one case by id."""
    return await _es_request(
        method="GET",
        path=f"/api/cases/{quote(case_id, safe='')}",
    )


async def soc_es_case_get_alerts(case_id: str) -> dict[str, Any]:
    """Get all alerts for one case."""
    return await _es_request(
        method="GET",
        path=f"/api/cases/{quote(case_id, safe='')}/alerts",
    )


async def soc_es_case_get_comments(case_id: str) -> dict[str, Any]:
    """Get all comments for one case."""
    return await _es_request(
        method="GET",
        path=f"/api/cases/{quote(case_id, safe='')}/comments",
    )


async def soc_es_case_get_activity(
    case_id: str,
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    """Get activity feed for one case."""
    params = _compact_params(page=page, perPage=per_page)
    return await _es_request(
        method="GET",
        path=f"/api/cases/{quote(case_id, safe='')}/activity",
        params=params,
    )


async def soc_es_exc_find_lists(
    page: int = 1,
    per_page: int = 20,
    namespace_type: str = "single",
    filter: str | None = None,
) -> dict[str, Any]:
    """Get exception lists."""
    params = _compact_params(
        page=page,
        per_page=per_page,
        namespace_type=namespace_type,
        filter=filter,
    )
    return await _es_request(method="GET", path="/api/exception_lists/_find", params=params)


async def soc_es_exc_find_items(
    page: int = 1,
    per_page: int = 20,
    list_id: str | None = None,
    namespace_type: str = "single",
    filter: str | None = None,
) -> dict[str, Any]:
    """Get exception list items."""
    params = _compact_params(
        page=page,
        per_page=per_page,
        list_id=list_id,
        namespace_type=namespace_type,
        filter=filter,
    )
    return await _es_request(
        method="GET",
        path="/api/exception_lists/items/_find",
        params=params,
    )


async def soc_es_exc_read_summary(namespace_type: str = "single") -> dict[str, Any]:
    """Get exception list summary."""
    params = _compact_params(namespace_type=namespace_type)
    return await _es_request(
        method="GET",
        path="/api/exception_lists/summary",
        params=params,
    )


async def soc_es_list_read(
    id: str | None = None,
    list_id: str | None = None,
    namespace_type: str = "single",
) -> dict[str, Any]:
    """Get list container details."""
    params = _compact_params(id=id, list_id=list_id, namespace_type=namespace_type)
    return await _es_request(method="GET", path="/api/lists", params=params)


async def soc_es_list_find_items(
    page: int = 1,
    per_page: int = 20,
    list_id: str | None = None,
    namespace_type: str = "single",
    filter: str | None = None,
) -> dict[str, Any]:
    """Get list items."""
    params = _compact_params(
        page=page,
        per_page=per_page,
        list_id=list_id,
        namespace_type=namespace_type,
        filter=filter,
    )
    return await _es_request(method="GET", path="/api/lists/items/_find", params=params)


async def soc_es_list_read_privileges() -> dict[str, Any]:
    """Get list privileges."""
    return await _es_request(method="GET", path="/api/lists/privileges")


def create_soc_alert_es_tools() -> list[StructuredTool]:
    """Create Elastic Security read-only tools for SOC alert."""
    return [
        StructuredTool.from_function(
            name="soc_es_det_search_alerts",
            description="Find and aggregate Elastic Security detection alerts.",
            func=soc_es_det_search_alerts,
            coroutine=soc_es_det_search_alerts,
            args_schema=SocEsDetSearchAlertsInput,
        ),
        StructuredTool.from_function(
            name="soc_es_det_get_rule",
            description="Retrieve one Elastic Security detection rule by id or rule_id.",
            func=soc_es_det_get_rule,
            coroutine=soc_es_det_get_rule,
            args_schema=SocEsDetGetRuleInput,
        ),
        StructuredTool.from_function(
            name="soc_es_det_find_rules",
            description="List Elastic Security detection rules.",
            func=soc_es_det_find_rules,
            coroutine=soc_es_det_find_rules,
            args_schema=SocEsDetFindRulesInput,
        ),
        StructuredTool.from_function(
            name="soc_es_det_read_tags",
            description="List all Elastic Security detection rule tags.",
            func=soc_es_det_read_tags,
            coroutine=soc_es_det_read_tags,
        ),
        StructuredTool.from_function(
            name="soc_es_case_find_cases",
            description="Search Elastic Security cases.",
            func=soc_es_case_find_cases,
            coroutine=soc_es_case_find_cases,
            args_schema=SocEsCaseFindCasesInput,
        ),
        StructuredTool.from_function(
            name="soc_es_case_get_case",
            description="Get Elastic Security case details by case id.",
            func=soc_es_case_get_case,
            coroutine=soc_es_case_get_case,
            args_schema=SocEsCaseGetByIdInput,
        ),
        StructuredTool.from_function(
            name="soc_es_case_get_alerts",
            description="Get all alerts associated with one Elastic Security case.",
            func=soc_es_case_get_alerts,
            coroutine=soc_es_case_get_alerts,
            args_schema=SocEsCaseGetByIdInput,
        ),
        StructuredTool.from_function(
            name="soc_es_case_get_comments",
            description="Get all comments associated with one Elastic Security case.",
            func=soc_es_case_get_comments,
            coroutine=soc_es_case_get_comments,
            args_schema=SocEsCaseGetByIdInput,
        ),
        StructuredTool.from_function(
            name="soc_es_case_get_activity",
            description="Get activity feed for one Elastic Security case.",
            func=soc_es_case_get_activity,
            coroutine=soc_es_case_get_activity,
            args_schema=SocEsCaseActivityInput,
        ),
        StructuredTool.from_function(
            name="soc_es_exc_find_lists",
            description="Get Elastic Security exception lists.",
            func=soc_es_exc_find_lists,
            coroutine=soc_es_exc_find_lists,
            args_schema=SocEsExceptionsFindInput,
        ),
        StructuredTool.from_function(
            name="soc_es_exc_find_items",
            description="Get Elastic Security exception list items.",
            func=soc_es_exc_find_items,
            coroutine=soc_es_exc_find_items,
            args_schema=SocEsExceptionsFindItemsInput,
        ),
        StructuredTool.from_function(
            name="soc_es_exc_read_summary",
            description="Get Elastic Security exception list summary.",
            func=soc_es_exc_read_summary,
            coroutine=soc_es_exc_read_summary,
            args_schema=SocEsExceptionsSummaryInput,
        ),
        StructuredTool.from_function(
            name="soc_es_list_read",
            description="Get Elastic Security list container details.",
            func=soc_es_list_read,
            coroutine=soc_es_list_read,
            args_schema=SocEsListsReadInput,
        ),
        StructuredTool.from_function(
            name="soc_es_list_find_items",
            description="Get Elastic Security list items.",
            func=soc_es_list_find_items,
            coroutine=soc_es_list_find_items,
            args_schema=SocEsListsFindItemsInput,
        ),
        StructuredTool.from_function(
            name="soc_es_list_read_privileges",
            description="Get Elastic Security list API privileges.",
            func=soc_es_list_read_privileges,
            coroutine=soc_es_list_read_privileges,
        ),
    ]
