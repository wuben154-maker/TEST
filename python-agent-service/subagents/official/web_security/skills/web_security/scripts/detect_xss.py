#!/usr/bin/env python3
"""XSS Detection Script.

This script detects Cross-Site Scripting (XSS) patterns in HTTP parameters.
Used by the web-security skill for XSS analysis.
"""

import re
import html
from typing import Any
from urllib.parse import unquote


# XSS patterns by category
XSS_PATTERNS = {
    "script_tag": [
        r"<script[^>]*>",
        r"</script>",
        r"<script[^>]*src\s*=",
    ],
    "event_handler": [
        r"\bon\w+\s*=",  # onclick, onerror, onload, etc.
        r"javascript\s*:",
        r"vbscript\s*:",
    ],
    "html_injection": [
        r"<img[^>]+onerror",
        r"<svg[^>]+onload",
        r"<body[^>]+onload",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
    ],
    "data_uri": [
        r"data\s*:\s*text/html",
        r"data\s*:\s*application/javascript",
    ],
    "encoding_bypass": [
        r"&#x?[0-9a-f]+;",  # HTML entities
        r"\\u[0-9a-f]{4}",  # Unicode escapes
        r"\\x[0-9a-f]{2}",  # Hex escapes
    ],
    "dom_xss": [
        r"document\.write\s*\(",
        r"document\.cookie",
        r"window\.location",
        r"eval\s*\(",
        r"innerHTML\s*=",
        r"outerHTML\s*=",
    ],
}

# Severity mapping
SEVERITY_MAP = {
    "script_tag": "high",
    "event_handler": "high",
    "html_injection": "high",
    "data_uri": "medium",
    "encoding_bypass": "medium",
    "dom_xss": "high",
}


def decode_value(value: str) -> str:
    """Decode various encodings in a value.
    
    Args:
        value: Encoded value
        
    Returns:
        Decoded value
    """
    # URL decode
    decoded = unquote(value)
    
    # HTML entity decode
    decoded = html.unescape(decoded)
    
    # Unicode escape decode
    try:
        decoded = decoded.encode().decode('unicode_escape')
    except Exception:
        pass
    
    return decoded


def detect_xss(value: str) -> dict[str, Any]:
    """Detect XSS patterns in a value.
    
    Args:
        value: Parameter value to analyze
        
    Returns:
        Detection results dictionary
    """
    result = {
        "value": value,
        "decoded": decode_value(value),
        "is_xss": False,
        "patterns_matched": [],
        "severity": "none",
        "categories": set(),
    }
    
    # Check original and decoded values
    values_to_check = [value.lower(), result["decoded"].lower()]
    
    for check_value in values_to_check:
        for category, patterns in XSS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, check_value, re.IGNORECASE):
                    result["is_xss"] = True
                    result["categories"].add(category)
                    
                    # Avoid duplicate pattern matches
                    match_key = f"{category}:{pattern}"
                    if not any(p.get("key") == match_key for p in result["patterns_matched"]):
                        result["patterns_matched"].append({
                            "key": match_key,
                            "category": category,
                            "pattern": pattern,
                            "severity": SEVERITY_MAP.get(category, "medium"),
                        })
    
    # Determine overall severity
    if result["is_xss"]:
        severities = [p["severity"] for p in result["patterns_matched"]]
        if "critical" in severities:
            result["severity"] = "critical"
        elif "high" in severities:
            result["severity"] = "high"
        elif "medium" in severities:
            result["severity"] = "medium"
        else:
            result["severity"] = "low"
    
    # Clean up results
    result["categories"] = list(result["categories"])
    for p in result["patterns_matched"]:
        del p["key"]
    
    return result


def analyze_xss_context(value: str, context: str = "html") -> dict[str, Any]:
    """Analyze XSS based on injection context.
    
    Args:
        value: Payload value
        context: Injection context (html, attribute, script, url)
        
    Returns:
        Context-aware analysis
    """
    detection = detect_xss(value)
    
    # Add context-specific analysis
    context_risks = {
        "html": "Direct HTML injection possible",
        "attribute": "Event handler injection possible",
        "script": "Direct JavaScript execution possible",
        "url": "JavaScript URI injection possible",
    }
    
    detection["context"] = context
    detection["context_risk"] = context_risks.get(context, "Unknown context")
    
    # Adjust severity based on context
    if context == "script" and detection["is_xss"]:
        detection["severity"] = "critical"
    
    return detection


def generate_waf_rules(detections: list[dict]) -> list[str]:
    """Generate WAF rules based on detections.
    
    Args:
        detections: List of XSS detections
        
    Returns:
        List of WAF rule suggestions
    """
    rules = []
    categories = set()
    
    for detection in detections:
        if detection.get("is_xss"):
            categories.update(detection.get("categories", []))
    
    if "script_tag" in categories:
        rules.append("Block requests containing <script> tags")
    if "event_handler" in categories:
        rules.append("Block requests with on* event handlers")
    if "html_injection" in categories:
        rules.append("Block requests with dangerous HTML tags (iframe, object, embed)")
    if "data_uri" in categories:
        rules.append("Block data: URI schemes in parameters")
    
    return rules


if __name__ == "__main__":
    # Test examples
    test_cases = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert(1)>",
        "javascript:alert(document.cookie)",
        "<svg onload=alert('XSS')>",
        "&#60;script&#62;alert('XSS')&#60;/script&#62;",
        "normal_text_value",
    ]
    
    print("XSS Detection Tests:")
    print("=" * 50)
    
    for test in test_cases:
        result = detect_xss(test)
        status = "🚨 XSS" if result["is_xss"] else "✓ Clean"
        print(f"\n{status}: {test[:50]}")
        if result["is_xss"]:
            print(f"  Severity: {result['severity']}")
            print(f"  Categories: {', '.join(result['categories'])}")
