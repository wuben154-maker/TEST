#!/usr/bin/env python3
"""SQL Injection Detection Script.

This script detects SQL injection patterns in HTTP parameters.
Used by the web-security skill for SQLi analysis.
"""

import re
from typing import Any
from urllib.parse import parse_qs, unquote


# SQL injection patterns by category
SQLI_PATTERNS = {
    "union": [
        r"union\s+(all\s+)?select",
        r"union\s+select\s+null",
    ],
    "boolean": [
        r"'\s*or\s+'?\d+'?\s*=\s*'?\d+",
        r"'\s*or\s+''='",
        r"'\s*and\s+'?\d+'?\s*=\s*'?\d+",
        r"1\s*=\s*1",
        r"1\s*=\s*0",
    ],
    "time_based": [
        r"sleep\s*\(\s*\d+\s*\)",
        r"waitfor\s+delay",
        r"benchmark\s*\(",
        r"pg_sleep\s*\(",
    ],
    "error_based": [
        r"extractvalue\s*\(",
        r"updatexml\s*\(",
        r"convert\s*\(.+using",
        r"exp\s*\(\s*~",
    ],
    "stacked": [
        r";\s*drop\s+",
        r";\s*delete\s+",
        r";\s*insert\s+",
        r";\s*update\s+",
        r";\s*create\s+",
    ],
    "comment": [
        r"--\s*$",
        r"/\*.*\*/",
        r"#\s*$",
    ],
    "encoding": [
        r"char\s*\(\d+\)",
        r"0x[0-9a-f]+",
        r"concat\s*\(",
    ],
}

# Severity mapping
SEVERITY_MAP = {
    "union": "high",
    "stacked": "critical",
    "time_based": "high",
    "error_based": "medium",
    "boolean": "medium",
    "comment": "low",
    "encoding": "low",
}


def detect_sqli(value: str) -> dict[str, Any]:
    """Detect SQL injection patterns in a value.
    
    Args:
        value: Parameter value to analyze
        
    Returns:
        Detection results dictionary
    """
    result = {
        "value": value,
        "decoded": unquote(value),
        "is_sqli": False,
        "patterns_matched": [],
        "severity": "none",
        "categories": set(),
    }
    
    # Decode and normalize
    decoded = unquote(value).lower()
    
    # Check each pattern category
    for category, patterns in SQLI_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, decoded, re.IGNORECASE):
                result["is_sqli"] = True
                result["categories"].add(category)
                result["patterns_matched"].append({
                    "category": category,
                    "pattern": pattern,
                    "severity": SEVERITY_MAP.get(category, "medium"),
                })
    
    # Determine overall severity
    if result["is_sqli"]:
        severities = [p["severity"] for p in result["patterns_matched"]]
        if "critical" in severities:
            result["severity"] = "critical"
        elif "high" in severities:
            result["severity"] = "high"
        elif "medium" in severities:
            result["severity"] = "medium"
        else:
            result["severity"] = "low"
    
    result["categories"] = list(result["categories"])
    return result


def analyze_request(url: str, body: str = "") -> dict[str, Any]:
    """Analyze HTTP request for SQL injection.
    
    Args:
        url: Full URL with query string
        body: Request body (for POST requests)
        
    Returns:
        Analysis results
    """
    result = {
        "url": url,
        "vulnerabilities": [],
        "overall_severity": "none",
    }
    
    # Parse URL parameters
    if "?" in url:
        query_string = url.split("?", 1)[1]
        params = parse_qs(query_string, keep_blank_values=True)
        
        for param, values in params.items():
            for value in values:
                detection = detect_sqli(value)
                if detection["is_sqli"]:
                    result["vulnerabilities"].append({
                        "location": "url",
                        "parameter": param,
                        **detection,
                    })
    
    # Parse body parameters
    if body:
        try:
            body_params = parse_qs(body, keep_blank_values=True)
            for param, values in body_params.items():
                for value in values:
                    detection = detect_sqli(value)
                    if detection["is_sqli"]:
                        result["vulnerabilities"].append({
                            "location": "body",
                            "parameter": param,
                            **detection,
                        })
        except Exception:
            # Body might not be form-encoded
            detection = detect_sqli(body)
            if detection["is_sqli"]:
                result["vulnerabilities"].append({
                    "location": "body",
                    "parameter": "raw_body",
                    **detection,
                })
    
    # Determine overall severity
    if result["vulnerabilities"]:
        severities = [v["severity"] for v in result["vulnerabilities"]]
        if "critical" in severities:
            result["overall_severity"] = "critical"
        elif "high" in severities:
            result["overall_severity"] = "high"
        elif "medium" in severities:
            result["overall_severity"] = "medium"
        else:
            result["overall_severity"] = "low"
    
    return result


if __name__ == "__main__":
    # Test examples
    test_cases = [
        "' OR '1'='1",
        "1 UNION SELECT username, password FROM users--",
        "1; DROP TABLE users;--",
        "1' AND SLEEP(5)--",
        "normal_value",
    ]
    
    print("SQL Injection Detection Tests:")
    print("=" * 50)
    
    for test in test_cases:
        result = detect_sqli(test)
        status = "🚨 SQLI" if result["is_sqli"] else "✓ Clean"
        print(f"\n{status}: {test[:50]}")
        if result["is_sqli"]:
            print(f"  Severity: {result['severity']}")
            print(f"  Categories: {', '.join(result['categories'])}")
