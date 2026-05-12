"""AWS GuardDuty read-only API tools for SOC triage."""

from __future__ import annotations

from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..api_service_config import load_api_service_config


class AwsDetectorInput(BaseModel):
    """Input schema with detector id."""

    detector_id: str = Field(description="GuardDuty detector id.")


class AwsDetectorPaginationInput(AwsDetectorInput):
    """Input schema with detector id and pagination."""

    max_results: int = Field(default=50, description="Maximum records to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsListDetectorsInput(BaseModel):
    """Input schema for list detectors."""

    max_results: int = Field(default=50, description="Maximum records to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsFindingsQueryInput(AwsDetectorInput):
    """Input schema for list findings."""

    finding_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional GuardDuty finding criteria filter object."
    )
    sort_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional sorting criteria object."
    )
    max_results: int = Field(default=50, description="Maximum number of findings to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsGetFindingsInput(AwsDetectorInput):
    """Input schema for get findings."""

    finding_ids: list[str] = Field(description="List of GuardDuty finding ids.")
    sort_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional sorting criteria object."
    )


class AwsFindingsStatisticsInput(AwsDetectorInput):
    """Input schema for finding statistics."""

    finding_statistic_types: list[str] | None = Field(
        default=None,
        description="Optional statistic dimensions, e.g. COUNT_BY_SEVERITY.",
    )
    finding_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional GuardDuty finding criteria filter object."
    )
    group_by: str | None = Field(default=None, description="Optional grouping field.")
    order_by: dict[str, Any] | None = Field(default=None, description="Optional order by object.")
    max_results: int = Field(default=50, description="Maximum number of groups to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsListMembersInput(AwsDetectorInput):
    """Input schema for list members."""

    only_associated: str | None = Field(
        default=None,
        description="Optional associated filter, e.g. TRUE or FALSE.",
    )
    max_results: int = Field(default=50, description="Maximum number of members to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsGetMembersInput(AwsDetectorInput):
    """Input schema for get members."""

    account_ids: list[str] = Field(description="Member account ids.")


class AwsGetMemberDetectorsInput(AwsDetectorInput):
    """Input schema for get member detectors."""

    account_ids: list[str] = Field(description="Member account ids.")


class AwsGetFilterInput(AwsDetectorInput):
    """Input schema for get filter."""

    filter_name: str = Field(description="Filter name.")


class AwsGetThreatIntelSetInput(AwsDetectorInput):
    """Input schema for get threat intel set."""

    threat_intel_set_id: str = Field(description="Threat intel set id.")


class AwsGetIPSetInput(AwsDetectorInput):
    """Input schema for get ip set."""

    ip_set_id: str = Field(description="IP set id.")


class AwsDescribeMalwareScansInput(AwsDetectorInput):
    """Input schema for describe malware scans."""

    filter_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional malware scan filter criteria."
    )
    sort_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional malware scan sort criteria."
    )
    max_results: int = Field(default=50, description="Maximum records to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsGetMalwareScanInput(BaseModel):
    """Input schema for get malware scan."""

    scan_id: str = Field(description="Malware scan id.")


class AwsListMalwareScansInput(BaseModel):
    """Input schema for list malware scans."""

    filter_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional malware scan filter criteria."
    )
    sort_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional malware scan sort criteria."
    )
    max_results: int = Field(default=50, description="Maximum records to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsListCoverageInput(AwsDetectorInput):
    """Input schema for list coverage."""

    filter_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional coverage filter criteria."
    )
    sort_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional coverage sort criteria."
    )
    max_results: int = Field(default=50, description="Maximum records to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


class AwsCoverageStatisticsInput(AwsDetectorInput):
    """Input schema for coverage statistics."""

    filter_criteria: dict[str, Any] | None = Field(
        default=None, description="Optional coverage filter criteria."
    )


class AwsListPublishingDestinationsInput(AwsDetectorInput):
    """Input schema for list publishing destinations."""

    max_results: int = Field(default=50, description="Maximum records to return.")
    next_token: str | None = Field(default=None, description="Pagination next token.")


def _simulated(detail: dict[str, Any]) -> dict[str, Any]:
    return {"simulated": True, "provider": "aws_guardduty", **detail}


def _auth_headers(api_key: str, secret: str) -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if secret:
        headers["X-API-SECRET"] = secret
    return headers


async def _guardduty_request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    svc = load_api_service_config("aws_guardduty")
    if not svc.enabled or not svc.base_url:
        return _simulated(
            {
                "method": method,
                "path": path,
                "query": query or {},
                "payload": payload or {},
                "note": "aws_guardduty service is not configured/enabled.",
            }
        )

    params = {k: v for k, v in (query or {}).items() if v is not None}
    body = {k: v for k, v in (payload or {}).items() if v is not None}
    headers = _auth_headers(svc.api_key, svc.secret)
    url = f"{svc.base_url.rstrip('/')}{path}"

    async with httpx.AsyncClient(timeout=float(svc.timeout)) as client:
        try:
            resp = await client.request(
                method=method.upper(),
                url=url,
                params=params if params else None,
                json=body if body else None,
                headers=headers,
            )
            resp.raise_for_status()
            parsed: Any
            try:
                parsed = resp.json()
            except Exception:
                parsed = {"raw": resp.text}
            return {
                "provider": "aws_guardduty",
                "method": method.upper(),
                "path": path,
                "data": parsed,
            }
        except Exception as exc:
            return {
                "provider": "aws_guardduty",
                "method": method.upper(),
                "path": path,
                "error": str(exc),
            }


async def soc_aws_guardduty_list_detectors(
    max_results: int = 50, next_token: str | None = None
) -> dict[str, Any]:
    """List GuardDuty detector ids."""
    return await _guardduty_request(
        "GET",
        "/detector",
        query={"maxResults": max_results, "nextToken": next_token},
    )


async def soc_aws_guardduty_get_detector(detector_id: str) -> dict[str, Any]:
    """Get one GuardDuty detector detail."""
    return await _guardduty_request("GET", f"/detector/{detector_id}")


async def soc_aws_guardduty_list_findings(
    detector_id: str,
    finding_criteria: dict[str, Any] | None = None,
    sort_criteria: dict[str, Any] | None = None,
    max_results: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """List finding ids for triage."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/findings",
        payload={
            "findingCriteria": finding_criteria,
            "sortCriteria": sort_criteria,
            "maxResults": max_results,
            "nextToken": next_token,
        },
    )


async def soc_aws_guardduty_get_findings(
    detector_id: str,
    finding_ids: list[str],
    sort_criteria: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get full finding details by ids."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/findings/get",
        payload={"findingIds": finding_ids, "sortCriteria": sort_criteria},
    )


async def soc_aws_guardduty_get_findings_statistics(
    detector_id: str,
    finding_statistic_types: list[str] | None = None,
    finding_criteria: dict[str, Any] | None = None,
    group_by: str | None = None,
    order_by: dict[str, Any] | None = None,
    max_results: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """Get finding statistics."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/findings/statistics",
        payload={
            "findingStatisticTypes": finding_statistic_types,
            "findingCriteria": finding_criteria,
            "groupBy": group_by,
            "orderBy": order_by,
            "maxResults": max_results,
            "nextToken": next_token,
        },
    )


async def soc_aws_guardduty_list_members(
    detector_id: str,
    only_associated: str | None = None,
    max_results: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """List member accounts under detector."""
    return await _guardduty_request(
        "GET",
        f"/detector/{detector_id}/member",
        query={
            "onlyAssociated": only_associated,
            "maxResults": max_results,
            "nextToken": next_token,
        },
    )


async def soc_aws_guardduty_get_members(
    detector_id: str, account_ids: list[str]
) -> dict[str, Any]:
    """Get member details by account ids."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/member/get",
        payload={"accountIds": account_ids},
    )


async def soc_aws_guardduty_get_member_detectors(
    detector_id: str, account_ids: list[str]
) -> dict[str, Any]:
    """Get member detector status in organization."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/member/detector/get",
        payload={"accountIds": account_ids},
    )


async def soc_aws_guardduty_list_filters(
    detector_id: str, max_results: int = 50, next_token: str | None = None
) -> dict[str, Any]:
    """List filter names."""
    return await _guardduty_request(
        "GET",
        f"/detector/{detector_id}/filter",
        query={"maxResults": max_results, "nextToken": next_token},
    )


async def soc_aws_guardduty_get_filter(
    detector_id: str, filter_name: str
) -> dict[str, Any]:
    """Get one filter detail."""
    return await _guardduty_request(
        "GET", f"/detector/{detector_id}/filter/{filter_name}"
    )


async def soc_aws_guardduty_list_threat_intel_sets(
    detector_id: str, max_results: int = 50, next_token: str | None = None
) -> dict[str, Any]:
    """List threat intel set ids."""
    return await _guardduty_request(
        "GET",
        f"/detector/{detector_id}/threatintelset",
        query={"maxResults": max_results, "nextToken": next_token},
    )


async def soc_aws_guardduty_get_threat_intel_set(
    detector_id: str, threat_intel_set_id: str
) -> dict[str, Any]:
    """Get threat intel set detail."""
    return await _guardduty_request(
        "GET", f"/detector/{detector_id}/threatintelset/{threat_intel_set_id}"
    )


async def soc_aws_guardduty_list_ip_sets(
    detector_id: str, max_results: int = 50, next_token: str | None = None
) -> dict[str, Any]:
    """List ip set ids."""
    return await _guardduty_request(
        "GET",
        f"/detector/{detector_id}/ipset",
        query={"maxResults": max_results, "nextToken": next_token},
    )


async def soc_aws_guardduty_get_ip_set(
    detector_id: str, ip_set_id: str
) -> dict[str, Any]:
    """Get one ip set detail."""
    return await _guardduty_request("GET", f"/detector/{detector_id}/ipset/{ip_set_id}")


async def soc_aws_guardduty_describe_malware_scans(
    detector_id: str,
    filter_criteria: dict[str, Any] | None = None,
    sort_criteria: dict[str, Any] | None = None,
    max_results: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """Describe malware scans under detector."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/malware-scans",
        payload={
            "filterCriteria": filter_criteria,
            "sortCriteria": sort_criteria,
            "maxResults": max_results,
            "nextToken": next_token,
        },
    )


async def soc_aws_guardduty_get_malware_scan(scan_id: str) -> dict[str, Any]:
    """Get one malware scan detail."""
    return await _guardduty_request("GET", f"/malware-scan/{scan_id}")


async def soc_aws_guardduty_list_malware_scans(
    filter_criteria: dict[str, Any] | None = None,
    sort_criteria: dict[str, Any] | None = None,
    max_results: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """List malware scan records."""
    return await _guardduty_request(
        "POST",
        "/malware-scan",
        query={"maxResults": max_results, "nextToken": next_token},
        payload={"filterCriteria": filter_criteria, "sortCriteria": sort_criteria},
    )


async def soc_aws_guardduty_list_coverage(
    detector_id: str,
    filter_criteria: dict[str, Any] | None = None,
    sort_criteria: dict[str, Any] | None = None,
    max_results: int = 50,
    next_token: str | None = None,
) -> dict[str, Any]:
    """List GuardDuty coverage status."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/coverage",
        payload={
            "filterCriteria": filter_criteria,
            "sortCriteria": sort_criteria,
            "maxResults": max_results,
            "nextToken": next_token,
        },
    )


async def soc_aws_guardduty_get_coverage_statistics(
    detector_id: str, filter_criteria: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Get GuardDuty coverage statistics."""
    return await _guardduty_request(
        "POST",
        f"/detector/{detector_id}/coverage/statistics",
        payload={"filterCriteria": filter_criteria},
    )


async def soc_aws_guardduty_list_publishing_destinations(
    detector_id: str, max_results: int = 50, next_token: str | None = None
) -> dict[str, Any]:
    """List publishing destinations."""
    return await _guardduty_request(
        "GET",
        f"/detector/{detector_id}/publishingDestination",
        query={"maxResults": max_results, "nextToken": next_token},
    )


def create_soc_alert_aws_api_tools() -> list[StructuredTool]:
    """Create AWS GuardDuty read-only API tools for SOC triage."""
    return [
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_detectors",
            description="List GuardDuty detectors for SOC triage bootstrap.",
            func=soc_aws_guardduty_list_detectors,
            coroutine=soc_aws_guardduty_list_detectors,
            args_schema=AwsListDetectorsInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_detector",
            description="Get one GuardDuty detector details and data source status.",
            func=soc_aws_guardduty_get_detector,
            coroutine=soc_aws_guardduty_get_detector,
            args_schema=AwsDetectorInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_findings",
            description="List GuardDuty finding ids by criteria.",
            func=soc_aws_guardduty_list_findings,
            coroutine=soc_aws_guardduty_list_findings,
            args_schema=AwsFindingsQueryInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_findings",
            description="Get full GuardDuty finding details by ids.",
            func=soc_aws_guardduty_get_findings,
            coroutine=soc_aws_guardduty_get_findings,
            args_schema=AwsGetFindingsInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_findings_statistics",
            description="Get GuardDuty findings statistics for triage overview.",
            func=soc_aws_guardduty_get_findings_statistics,
            coroutine=soc_aws_guardduty_get_findings_statistics,
            args_schema=AwsFindingsStatisticsInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_members",
            description="List GuardDuty member accounts.",
            func=soc_aws_guardduty_list_members,
            coroutine=soc_aws_guardduty_list_members,
            args_schema=AwsListMembersInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_members",
            description="Get GuardDuty member account details.",
            func=soc_aws_guardduty_get_members,
            coroutine=soc_aws_guardduty_get_members,
            args_schema=AwsGetMembersInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_member_detectors",
            description="Get GuardDuty member detector statuses.",
            func=soc_aws_guardduty_get_member_detectors,
            coroutine=soc_aws_guardduty_get_member_detectors,
            args_schema=AwsGetMemberDetectorsInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_filters",
            description="List GuardDuty filters for triage policy inspection.",
            func=soc_aws_guardduty_list_filters,
            coroutine=soc_aws_guardduty_list_filters,
            args_schema=AwsDetectorPaginationInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_filter",
            description="Get one GuardDuty filter detail.",
            func=soc_aws_guardduty_get_filter,
            coroutine=soc_aws_guardduty_get_filter,
            args_schema=AwsGetFilterInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_threat_intel_sets",
            description="List GuardDuty threat intel sets.",
            func=soc_aws_guardduty_list_threat_intel_sets,
            coroutine=soc_aws_guardduty_list_threat_intel_sets,
            args_schema=AwsDetectorPaginationInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_threat_intel_set",
            description="Get one GuardDuty threat intel set detail.",
            func=soc_aws_guardduty_get_threat_intel_set,
            coroutine=soc_aws_guardduty_get_threat_intel_set,
            args_schema=AwsGetThreatIntelSetInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_ip_sets",
            description="List GuardDuty IP sets.",
            func=soc_aws_guardduty_list_ip_sets,
            coroutine=soc_aws_guardduty_list_ip_sets,
            args_schema=AwsDetectorPaginationInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_ip_set",
            description="Get one GuardDuty IP set detail.",
            func=soc_aws_guardduty_get_ip_set,
            coroutine=soc_aws_guardduty_get_ip_set,
            args_schema=AwsGetIPSetInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_describe_malware_scans",
            description="Describe GuardDuty malware scans for triage context.",
            func=soc_aws_guardduty_describe_malware_scans,
            coroutine=soc_aws_guardduty_describe_malware_scans,
            args_schema=AwsDescribeMalwareScansInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_malware_scan",
            description="Get one GuardDuty malware scan detail.",
            func=soc_aws_guardduty_get_malware_scan,
            coroutine=soc_aws_guardduty_get_malware_scan,
            args_schema=AwsGetMalwareScanInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_malware_scans",
            description="List GuardDuty malware scans.",
            func=soc_aws_guardduty_list_malware_scans,
            coroutine=soc_aws_guardduty_list_malware_scans,
            args_schema=AwsListMalwareScansInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_coverage",
            description="List GuardDuty coverage records.",
            func=soc_aws_guardduty_list_coverage,
            coroutine=soc_aws_guardduty_list_coverage,
            args_schema=AwsListCoverageInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_get_coverage_statistics",
            description="Get GuardDuty coverage statistics.",
            func=soc_aws_guardduty_get_coverage_statistics,
            coroutine=soc_aws_guardduty_get_coverage_statistics,
            args_schema=AwsCoverageStatisticsInput,
        ),
        StructuredTool.from_function(
            name="soc_aws_guardduty_list_publishing_destinations",
            description="List GuardDuty publishing destinations.",
            func=soc_aws_guardduty_list_publishing_destinations,
            coroutine=soc_aws_guardduty_list_publishing_destinations,
            args_schema=AwsListPublishingDestinationsInput,
        ),
    ]
