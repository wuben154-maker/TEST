"""Vendor/action mapping registry for SOC action adaptor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..api.splunk.api_splunk_tools import (
    soc_splunk_get_job,
    soc_splunk_get_job_events,
    soc_splunk_get_job_search_log,
    soc_splunk_get_job_timeline,
    soc_splunk_get_saved_search,
    soc_splunk_list_jobs,
    soc_splunk_list_saved_searches,
    soc_splunk_query_domain_admin_enum,
    soc_splunk_query_file_activity,
    soc_splunk_query_host_timeline,
    soc_splunk_query_indicator_search,
    soc_splunk_query_lateral_movement,
    soc_splunk_query_ldap_activity,
    soc_splunk_query_network_connections,
    soc_splunk_query_powershell_bypass,
    soc_splunk_query_process_tree,
    soc_splunk_query_user_activity,
    soc_splunk_search_export,
)
from ..api.virustotal.api_virustotal_tools import (
    soc_vt_analysis_status,
    soc_vt_domain_query,
    soc_vt_file_query,
    soc_vt_file_scan,
    soc_vt_ip_query,
    soc_vt_url_query,
    soc_vt_url_scan,
)

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ActionMapping:
    """Vendor mapping from generic action to concrete tool invocation."""

    tool_name: str
    handler: ToolHandler
    param_map: dict[str, str] = field(default_factory=dict)
    required_params: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)


VENDOR_ACTION_MAP: dict[str, dict[str, ActionMapping]] = {
    # ES mappings are intentionally disabled for now.
    # "elastic_security": _ELASTIC_SECURITY_ACTION_MAP,
    "splunk": {
        "query_alerts": ActionMapping(
            tool_name="soc_splunk_search_export",
            handler=soc_splunk_search_export,
            param_map={
                "search": "search",
                "earliest_time": "earliest_time",
                "latest_time": "latest_time",
                "output_mode": "output_mode",
            },
            defaults={
                "search": "search index=*",
                "earliest_time": "-24h",
                "latest_time": "now",
                "output_mode": "json",
            },
        ),
        "query_rules": ActionMapping(
            tool_name="soc_splunk_list_saved_searches",
            handler=soc_splunk_list_saved_searches,
            param_map={"count": "count", "offset": "offset", "output_mode": "output_mode"},
            defaults={"count": 20, "offset": 0, "output_mode": "json"},
        ),
        "query_rule_detail": ActionMapping(
            tool_name="soc_splunk_get_saved_search",
            handler=soc_splunk_get_saved_search,
            param_map={"search_name": "search_name", "output_mode": "output_mode"},
            required_params=("search_name",),
            defaults={"output_mode": "json"},
        ),
        "query_cases": ActionMapping(
            tool_name="soc_splunk_list_jobs",
            handler=soc_splunk_list_jobs,
            param_map={"count": "count", "offset": "offset", "output_mode": "output_mode"},
            defaults={"count": 20, "offset": 0, "output_mode": "json"},
        ),
        "query_case_detail": ActionMapping(
            tool_name="soc_splunk_get_job",
            handler=soc_splunk_get_job,
            param_map={"sid": "sid", "output_mode": "output_mode"},
            required_params=("sid",),
            defaults={"output_mode": "json"},
        ),
        "query_case_alerts": ActionMapping(
            tool_name="soc_splunk_get_job_events",
            handler=soc_splunk_get_job_events,
            param_map={
                "sid": "sid",
                "count": "count",
                "offset": "offset",
                "output_mode": "output_mode",
            },
            required_params=("sid",),
            defaults={"count": 100, "offset": 0, "output_mode": "json"},
        ),
        "query_case_comments": ActionMapping(
            tool_name="soc_splunk_get_job_search_log",
            handler=soc_splunk_get_job_search_log,
            param_map={"sid": "sid", "output_mode": "output_mode"},
            required_params=("sid",),
            defaults={"output_mode": "json"},
        ),
        "query_case_activity": ActionMapping(
            tool_name="soc_splunk_get_job_timeline",
            handler=soc_splunk_get_job_timeline,
            param_map={"sid": "sid", "output_mode": "output_mode"},
            required_params=("sid",),
            defaults={"output_mode": "json"},
        ),
        "hunt_powershell_bypass": ActionMapping(
            tool_name="soc_splunk_query_powershell_bypass",
            handler=soc_splunk_query_powershell_bypass,
            param_map={
                "index": "index",
                "host": "host",
                "user": "user",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "query_host_timeline": ActionMapping(
            tool_name="soc_splunk_query_host_timeline",
            handler=soc_splunk_query_host_timeline,
            param_map={
                "index": "index",
                "host": "host",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=("host",),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "query_user_process_activity": ActionMapping(
            tool_name="soc_splunk_query_user_activity",
            handler=soc_splunk_query_user_activity,
            param_map={
                "index": "index",
                "user": "user",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=("user",),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "query_network_connections": ActionMapping(
            tool_name="soc_splunk_query_network_connections",
            handler=soc_splunk_query_network_connections,
            param_map={
                "index": "index",
                "host": "host",
                "dest_ip": "dest_ip",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "query_ldap_activity": ActionMapping(
            tool_name="soc_splunk_query_ldap_activity",
            handler=soc_splunk_query_ldap_activity,
            param_map={
                "index": "index",
                "host": "host",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "hunt_domain_admin_enumeration": ActionMapping(
            tool_name="soc_splunk_query_domain_admin_enum",
            handler=soc_splunk_query_domain_admin_enum,
            param_map={
                "index": "index",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "detect_lateral_movement": ActionMapping(
            tool_name="soc_splunk_query_lateral_movement",
            handler=soc_splunk_query_lateral_movement,
            param_map={
                "index": "index",
                "indicator": "indicator",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=("indicator",),
            defaults={"index": "*", "earliest": "-30m", "latest": "now"},
        ),
        "query_process_tree": ActionMapping(
            tool_name="soc_splunk_query_process_tree",
            handler=soc_splunk_query_process_tree,
            param_map={
                "index": "index",
                "process_name": "process_name",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=("process_name",),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "query_file_activity": ActionMapping(
            tool_name="soc_splunk_query_file_activity",
            handler=soc_splunk_query_file_activity,
            param_map={
                "index": "index",
                "file_path": "file_path",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "search_indicator": ActionMapping(
            tool_name="soc_splunk_query_indicator_search",
            handler=soc_splunk_query_indicator_search,
            param_map={
                "index": "index",
                "indicator": "indicator",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=("indicator",),
            defaults={"index": "*", "earliest": "-24h", "latest": "now"},
        ),
        # Compatibility aliases for existing node3 outputs.
        "query_process_events": ActionMapping(
            tool_name="soc_splunk_query_process_tree",
            handler=soc_splunk_query_process_tree,
            param_map={
                "index": "index",
                "process_name": "process_name",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "process_name": "*", "earliest": "-15m", "latest": "now"},
        ),
        "query_events": ActionMapping(
            tool_name="soc_splunk_search_export",
            handler=soc_splunk_search_export,
            param_map={
                "search": "search",
                "earliest_time": "earliest_time",
                "latest_time": "latest_time",
                "output_mode": "output_mode",
            },
            required_params=(),
            defaults={
                "search": "search index=*",
                "earliest_time": "-1h",
                "latest_time": "now",
                "output_mode": "json",
            },
        ),
        "query_file_events": ActionMapping(
            tool_name="soc_splunk_query_file_activity",
            handler=soc_splunk_query_file_activity,
            param_map={
                "index": "index",
                "file_path": "file_path",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
        "query_network_events": ActionMapping(
            tool_name="soc_splunk_query_network_connections",
            handler=soc_splunk_query_network_connections,
            param_map={
                "index": "index",
                "host": "host",
                "dest_ip": "dest_ip",
                "earliest": "earliest",
                "latest": "latest",
            },
            required_params=(),
            defaults={"index": "*", "earliest": "-15m", "latest": "now"},
        ),
    },
    "virustotal": {
        # WEB class canonical generic actions
        "query_domain_reputation": ActionMapping(
            tool_name="soc_vt_domain_query",
            handler=soc_vt_domain_query,
            param_map={"domain": "domain"},
            required_params=("domain",),
            defaults={},
        ),
        "query_ip_reputation": ActionMapping(
            tool_name="soc_vt_ip_query",
            handler=soc_vt_ip_query,
            param_map={"ip": "ip"},
            required_params=("ip",),
            defaults={},
        ),
        "query_url_reputation": ActionMapping(
            tool_name="soc_vt_url_query",
            handler=soc_vt_url_query,
            param_map={"url": "url"},
            required_params=("url",),
            defaults={},
        ),
        "query_file_reputation": ActionMapping(
            tool_name="soc_vt_file_query",
            handler=soc_vt_file_query,
            param_map={"file_hash": "file_hash"},
            required_params=("file_hash",),
            defaults={},
        ),
        "submit_url_scan": ActionMapping(
            tool_name="soc_vt_url_scan",
            handler=soc_vt_url_scan,
            param_map={"url": "url"},
            required_params=("url",),
            defaults={},
        ),
        "submit_file_scan": ActionMapping(
            tool_name="soc_vt_file_scan",
            handler=soc_vt_file_scan,
            param_map={"file_path": "file_path"},
            required_params=("file_path",),
            defaults={},
        ),
        "query_analysis_status": ActionMapping(
            tool_name="soc_vt_analysis_status",
            handler=soc_vt_analysis_status,
            param_map={"analysis_id": "analysis_id"},
            required_params=("analysis_id",),
            defaults={},
        ),
        # Legacy aliases (phase-1 compatibility)
        "soc_vt_domain_query": ActionMapping(
            tool_name="soc_vt_domain_query",
            handler=soc_vt_domain_query,
            param_map={"domain": "domain"},
            required_params=("domain",),
            defaults={},
        ),
        "soc_vt_ip_query": ActionMapping(
            tool_name="soc_vt_ip_query",
            handler=soc_vt_ip_query,
            param_map={"ip": "ip"},
            required_params=("ip",),
            defaults={},
        ),
        "soc_vt_url_query": ActionMapping(
            tool_name="soc_vt_url_query",
            handler=soc_vt_url_query,
            param_map={"url": "url"},
            required_params=("url",),
            defaults={},
        ),
        "soc_vt_file_query": ActionMapping(
            tool_name="soc_vt_file_query",
            handler=soc_vt_file_query,
            param_map={"file_hash": "file_hash"},
            required_params=("file_hash",),
            defaults={},
        ),
        "soc_vt_url_scan": ActionMapping(
            tool_name="soc_vt_url_scan",
            handler=soc_vt_url_scan,
            param_map={"url": "url"},
            required_params=("url",),
            defaults={},
        ),
        "soc_vt_file_scan": ActionMapping(
            tool_name="soc_vt_file_scan",
            handler=soc_vt_file_scan,
            param_map={"file_path": "file_path"},
            required_params=("file_path",),
            defaults={},
        ),
        "soc_vt_analysis_status": ActionMapping(
            tool_name="soc_vt_analysis_status",
            handler=soc_vt_analysis_status,
            param_map={"analysis_id": "analysis_id"},
            required_params=("analysis_id",),
            defaults={},
        ),
    },
}

VENDOR_ALIASES: dict[str, str] = {
    "elastic": "elastic_security",
    "elasticsecurity": "elastic_security",
    "elastic_security": "elastic_security",
    "elastic-siem": "elastic_security",
    "elasticsearch": "elastic_security",
    "kibana": "elastic_security",
    "splunk": "splunk",
    "splunk_enterprise": "splunk",
    "splunk_cloud": "splunk",
    "virustotal": "virustotal",
    "virus_total": "virustotal",
    "vt": "virustotal",
}

