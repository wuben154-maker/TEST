#!/usr/bin/env python3
"""SIEM Alert Parser Script.

This script parses security alerts from various SIEM platforms.
Used by the soc-alert skill for alert triage.
"""

import json
import re
from datetime import datetime
from typing import Any


def parse_splunk_alert(alert_data: dict | str) -> dict[str, Any]:
    """Parse Splunk alert format.
    
    Args:
        alert_data: Splunk alert data (dict or JSON string)
        
    Returns:
        Normalized alert dictionary
    """
    if isinstance(alert_data, str):
        alert_data = json.loads(alert_data)
    
    return {
        "source": "splunk",
        "alert_name": alert_data.get("search_name", alert_data.get("name", "Unknown")),
        "severity": normalize_severity(alert_data.get("severity", "unknown")),
        "timestamp": alert_data.get("_time", alert_data.get("timestamp")),
        "description": alert_data.get("description", ""),
        "raw_data": alert_data,
        "fields": {
            "src_ip": alert_data.get("src_ip", alert_data.get("src")),
            "dst_ip": alert_data.get("dst_ip", alert_data.get("dst")),
            "user": alert_data.get("user"),
            "host": alert_data.get("host"),
            "action": alert_data.get("action"),
        },
    }


def parse_elastic_alert(alert_data: dict | str) -> dict[str, Any]:
    """Parse Elastic/ELK alert format.
    
    Args:
        alert_data: Elastic alert data
        
    Returns:
        Normalized alert dictionary
    """
    if isinstance(alert_data, str):
        alert_data = json.loads(alert_data)
    
    source = alert_data.get("_source", alert_data)
    
    return {
        "source": "elastic",
        "alert_name": source.get("rule", {}).get("name", source.get("signal", {}).get("rule", {}).get("name", "Unknown")),
        "severity": normalize_severity(source.get("severity", source.get("signal", {}).get("rule", {}).get("severity", "unknown"))),
        "timestamp": source.get("@timestamp", source.get("timestamp")),
        "description": source.get("rule", {}).get("description", ""),
        "raw_data": alert_data,
        "fields": {
            "src_ip": source.get("source", {}).get("ip"),
            "dst_ip": source.get("destination", {}).get("ip"),
            "user": source.get("user", {}).get("name"),
            "host": source.get("host", {}).get("name"),
            "action": source.get("event", {}).get("action"),
        },
    }


def parse_sentinel_alert(alert_data: dict | str) -> dict[str, Any]:
    """Parse Microsoft Sentinel alert format.
    
    Args:
        alert_data: Sentinel alert data
        
    Returns:
        Normalized alert dictionary
    """
    if isinstance(alert_data, str):
        alert_data = json.loads(alert_data)
    
    return {
        "source": "sentinel",
        "alert_name": alert_data.get("AlertName", alert_data.get("alertName", "Unknown")),
        "severity": normalize_severity(alert_data.get("Severity", alert_data.get("severity", "unknown"))),
        "timestamp": alert_data.get("TimeGenerated", alert_data.get("timestamp")),
        "description": alert_data.get("Description", ""),
        "raw_data": alert_data,
        "fields": {
            "src_ip": alert_data.get("SourceIP"),
            "dst_ip": alert_data.get("DestinationIP"),
            "user": alert_data.get("AccountName"),
            "host": alert_data.get("Computer"),
            "action": alert_data.get("AlertType"),
        },
        "tactics": alert_data.get("Tactics", "").split(",") if alert_data.get("Tactics") else [],
        "techniques": alert_data.get("Techniques", "").split(",") if alert_data.get("Techniques") else [],
    }


def normalize_severity(severity: str) -> str:
    """Normalize severity to standard levels.
    
    Args:
        severity: Raw severity string
        
    Returns:
        Normalized severity (critical/high/medium/low/info)
    """
    severity_lower = str(severity).lower()
    
    if severity_lower in ["critical", "crit", "4", "p1"]:
        return "critical"
    elif severity_lower in ["high", "3", "p2", "severe"]:
        return "high"
    elif severity_lower in ["medium", "med", "2", "p3", "moderate"]:
        return "medium"
    elif severity_lower in ["low", "1", "p4", "minor"]:
        return "low"
    else:
        return "info"


def extract_iocs(alert: dict) -> dict[str, list]:
    """Extract IOCs from parsed alert.
    
    Args:
        alert: Parsed alert dictionary
        
    Returns:
        Dictionary of IOC types to values
    """
    iocs = {
        "ips": [],
        "domains": [],
        "hashes": [],
        "emails": [],
        "urls": [],
    }
    
    # Convert alert to string for regex matching
    alert_str = json.dumps(alert)
    
    # IP addresses
    ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    ips = re.findall(ip_pattern, alert_str)
    iocs["ips"] = list(set(ip for ip in ips if not ip.startswith("10.") and not ip.startswith("192.168.") and not ip.startswith("127.")))
    
    # Domains
    domain_pattern = r'\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b'
    domains = re.findall(domain_pattern, alert_str.lower())
    iocs["domains"] = list(set(d for d in domains if not d.endswith(".local") and not d.endswith(".internal")))
    
    # Hashes (MD5, SHA1, SHA256)
    md5_pattern = r'\b[a-f0-9]{32}\b'
    sha1_pattern = r'\b[a-f0-9]{40}\b'
    sha256_pattern = r'\b[a-f0-9]{64}\b'
    
    iocs["hashes"] = list(set(
        re.findall(sha256_pattern, alert_str.lower()) +
        re.findall(sha1_pattern, alert_str.lower()) +
        re.findall(md5_pattern, alert_str.lower())
    ))
    
    return iocs


def assess_priority(alert: dict) -> dict[str, Any]:
    """Assess alert priority based on multiple factors.
    
    Args:
        alert: Parsed alert dictionary
        
    Returns:
        Priority assessment
    """
    severity = alert.get("severity", "info")
    
    # Base priority from severity
    priority_map = {
        "critical": "P1",
        "high": "P2",
        "medium": "P3",
        "low": "P4",
        "info": "P4",
    }
    
    base_priority = priority_map.get(severity, "P4")
    
    # Check for priority modifiers
    modifiers = []
    
    # Check for known high-value targets
    fields = alert.get("fields", {})
    if fields.get("user") and any(x in str(fields.get("user", "")).lower() for x in ["admin", "root", "system"]):
        modifiers.append("privileged_user")
    
    # Check for external IPs (potential C2)
    iocs = extract_iocs(alert)
    if iocs.get("ips"):
        modifiers.append("external_ips")
    
    return {
        "priority": base_priority,
        "severity": severity,
        "modifiers": modifiers,
        "iocs": iocs,
    }


def auto_detect_format(alert_data: dict | str) -> str:
    """Auto-detect SIEM format from alert data.
    
    Args:
        alert_data: Raw alert data
        
    Returns:
        Detected format name
    """
    if isinstance(alert_data, str):
        alert_data = json.loads(alert_data)
    
    # Splunk indicators
    if "_time" in alert_data or "search_name" in alert_data:
        return "splunk"
    
    # Elastic indicators
    if "_source" in alert_data or "@timestamp" in alert_data:
        return "elastic"
    
    # Sentinel indicators
    if "TimeGenerated" in alert_data or "AlertName" in alert_data:
        return "sentinel"
    
    return "unknown"


if __name__ == "__main__":
    # Example Splunk alert
    splunk_alert = {
        "search_name": "Brute Force Detection",
        "severity": "high",
        "_time": "2024-01-01T12:00:00Z",
        "src_ip": "192.168.1.100",
        "dst_ip": "10.0.0.50",
        "user": "admin",
        "action": "failed_login",
        "count": 50,
    }
    
    parsed = parse_splunk_alert(splunk_alert)
    priority = assess_priority(parsed)
    
    print("Parsed Splunk Alert:")
    print(f"  Name: {parsed['alert_name']}")
    print(f"  Severity: {parsed['severity']}")
    print(f"  Priority: {priority['priority']}")
    print(f"  IOCs: {priority['iocs']}")
