#!/usr/bin/env python3
"""CVE Parser Script.

This script parses and enriches CVE information.
Used by the vuln-scan skill for vulnerability analysis.
"""

import re
from typing import Any
from dataclasses import dataclass


@dataclass
class CVSSVector:
    """Parsed CVSS v3.x vector."""
    attack_vector: str = "N"  # N=Network, A=Adjacent, L=Local, P=Physical
    attack_complexity: str = "L"  # L=Low, H=High
    privileges_required: str = "N"  # N=None, L=Low, H=High
    user_interaction: str = "N"  # N=None, R=Required
    scope: str = "U"  # U=Unchanged, C=Changed
    confidentiality: str = "N"  # N=None, L=Low, H=High
    integrity: str = "N"  # N=None, L=Low, H=High
    availability: str = "N"  # N=None, L=Low, H=High
    
    def to_string(self) -> str:
        return f"CVSS:3.1/AV:{self.attack_vector}/AC:{self.attack_complexity}/PR:{self.privileges_required}/UI:{self.user_interaction}/S:{self.scope}/C:{self.confidentiality}/I:{self.integrity}/A:{self.availability}"


def parse_cvss_vector(vector_string: str) -> CVSSVector | None:
    """Parse CVSS vector string.
    
    Args:
        vector_string: CVSS vector string (e.g., "CVSS:3.1/AV:N/AC:L/...")
        
    Returns:
        Parsed CVSSVector or None if invalid
    """
    if not vector_string:
        return None
    
    try:
        # Extract components
        components = {}
        for part in vector_string.split("/"):
            if ":" in part:
                key, value = part.split(":", 1)
                components[key] = value
        
        return CVSSVector(
            attack_vector=components.get("AV", "N"),
            attack_complexity=components.get("AC", "L"),
            privileges_required=components.get("PR", "N"),
            user_interaction=components.get("UI", "N"),
            scope=components.get("S", "U"),
            confidentiality=components.get("C", "N"),
            integrity=components.get("I", "N"),
            availability=components.get("A", "N"),
        )
    except Exception:
        return None


def severity_from_score(score: float) -> str:
    """Get severity level from CVSS score.
    
    Args:
        score: CVSS score (0-10)
        
    Returns:
        Severity string
    """
    if score >= 9.0:
        return "critical"
    elif score >= 7.0:
        return "high"
    elif score >= 4.0:
        return "medium"
    elif score > 0:
        return "low"
    else:
        return "none"


def parse_cve_id(text: str) -> list[str]:
    """Extract CVE IDs from text.
    
    Args:
        text: Text containing CVE references
        
    Returns:
        List of CVE IDs
    """
    pattern = r'CVE-\d{4}-\d{4,}'
    return list(set(re.findall(pattern, text, re.IGNORECASE)))


def analyze_cve(cve_data: dict) -> dict[str, Any]:
    """Analyze CVE data and provide risk assessment.
    
    Args:
        cve_data: CVE information dictionary
        
    Returns:
        Analysis results
    """
    result = {
        "cve_id": cve_data.get("id", "Unknown"),
        "description": cve_data.get("description", ""),
        "cvss_score": cve_data.get("cvss_score", 0),
        "cvss_vector": cve_data.get("cvss_vector", ""),
        "severity": "unknown",
        "exploitability": "unknown",
        "risk_factors": [],
        "priority": "P4",
    }
    
    # Determine severity
    score = float(result["cvss_score"])
    result["severity"] = severity_from_score(score)
    
    # Parse vector for risk factors
    vector = parse_cvss_vector(result["cvss_vector"])
    if vector:
        # Network accessible
        if vector.attack_vector == "N":
            result["risk_factors"].append("Network accessible")
        
        # No auth required
        if vector.privileges_required == "N":
            result["risk_factors"].append("No authentication required")
        
        # No user interaction
        if vector.user_interaction == "N":
            result["risk_factors"].append("No user interaction needed")
        
        # High impact
        if vector.confidentiality == "H":
            result["risk_factors"].append("High confidentiality impact")
        if vector.integrity == "H":
            result["risk_factors"].append("High integrity impact")
        if vector.availability == "H":
            result["risk_factors"].append("High availability impact")
    
    # Check for exploit indicators
    description_lower = result["description"].lower()
    exploit_keywords = ["exploit", "actively exploited", "in the wild", "poc", "proof of concept"]
    if any(kw in description_lower for kw in exploit_keywords):
        result["exploitability"] = "high"
        result["risk_factors"].append("Exploit references in description")
    
    # RCE check
    rce_keywords = ["remote code execution", "rce", "arbitrary code"]
    if any(kw in description_lower for kw in rce_keywords):
        result["risk_factors"].append("Remote Code Execution")
        result["exploitability"] = "critical"
    
    # Determine priority
    if score >= 9.0 and result["exploitability"] in ["high", "critical"]:
        result["priority"] = "P0"
    elif score >= 9.0 or result["exploitability"] == "critical":
        result["priority"] = "P1"
    elif score >= 7.0:
        result["priority"] = "P2"
    elif score >= 4.0:
        result["priority"] = "P3"
    else:
        result["priority"] = "P4"
    
    return result


def prioritize_cves(cves: list[dict]) -> list[dict]:
    """Prioritize a list of CVEs by risk.
    
    Args:
        cves: List of CVE data dictionaries
        
    Returns:
        Sorted list with analysis
    """
    analyzed = [analyze_cve(cve) for cve in cves]
    
    # Sort by priority (P0 first) then by score
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    analyzed.sort(key=lambda x: (priority_order.get(x["priority"], 5), -x["cvss_score"]))
    
    return analyzed


if __name__ == "__main__":
    # Example CVE data
    test_cves = [
        {
            "id": "CVE-2024-1234",
            "description": "Remote code execution vulnerability in Example Software allows unauthenticated attackers to execute arbitrary code.",
            "cvss_score": 9.8,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        },
        {
            "id": "CVE-2024-5678",
            "description": "Information disclosure vulnerability allows authenticated users to access sensitive data.",
            "cvss_score": 4.3,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N",
        },
    ]
    
    print("CVE Prioritization Results:")
    print("=" * 50)
    
    prioritized = prioritize_cves(test_cves)
    for cve in prioritized:
        print(f"\n{cve['cve_id']} - Priority: {cve['priority']}")
        print(f"  Severity: {cve['severity']} (CVSS: {cve['cvss_score']})")
        print(f"  Risk Factors: {', '.join(cve['risk_factors']) or 'None'}")
