#!/usr/bin/env python3
"""IOC Extraction Script.

This script extracts Indicators of Compromise from text data.
Used by the general-security skill for threat analysis.
"""

import re
from typing import Any
from dataclasses import dataclass, field


@dataclass
class IOCCollection:
    """Collection of extracted IOCs."""
    ipv4: list[str] = field(default_factory=list)
    ipv6: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    md5: list[str] = field(default_factory=list)
    sha1: list[str] = field(default_factory=list)
    sha256: list[str] = field(default_factory=list)
    filenames: list[str] = field(default_factory=list)
    registry_keys: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, list]:
        return {
            "ipv4": self.ipv4,
            "ipv6": self.ipv6,
            "domains": self.domains,
            "urls": self.urls,
            "emails": self.emails,
            "md5": self.md5,
            "sha1": self.sha1,
            "sha256": self.sha256,
            "filenames": self.filenames,
            "registry_keys": self.registry_keys,
        }
    
    def count(self) -> int:
        return sum(len(v) for v in self.to_dict().values())


# Regex patterns for IOC extraction
PATTERNS = {
    "ipv4": r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
    "ipv6": r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b|\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b',
    "domain": r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b',
    "url": r'https?://[^\s<>"{}|\\^`\[\]]+',
    "email": r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
    "md5": r'\b[a-fA-F0-9]{32}\b',
    "sha1": r'\b[a-fA-F0-9]{40}\b',
    "sha256": r'\b[a-fA-F0-9]{64}\b',
    "filename": r'\b[\w-]+\.(?:exe|dll|scr|bat|ps1|vbs|js|jar|doc|docm|xls|xlsm|pdf|zip|rar|7z)\b',
    "registry": r'\b(?:HKEY_[A-Z_]+|HKLM|HKCU|HKU|HKCR)\\[^\s]+\b',
}

# Known benign patterns to filter
BENIGN_PATTERNS = {
    "domains": [
        r'\.google\.com$',
        r'\.microsoft\.com$',
        r'\.windows\.com$',
        r'\.github\.com$',
        r'\.example\.com$',
        r'\.localhost$',
        r'\.local$',
        r'\.internal$',
    ],
    "ips": [
        r'^10\.',
        r'^172\.(1[6-9]|2[0-9]|3[0-1])\.',
        r'^192\.168\.',
        r'^127\.',
        r'^0\.',
        r'^255\.',
    ],
}


def is_benign(ioc_type: str, value: str) -> bool:
    """Check if an IOC is likely benign.
    
    Args:
        ioc_type: Type of IOC (domains, ips, etc.)
        value: IOC value
        
    Returns:
        True if likely benign
    """
    patterns = BENIGN_PATTERNS.get(ioc_type, [])
    for pattern in patterns:
        if re.search(pattern, value, re.IGNORECASE):
            return True
    return False


def extract_iocs(text: str, filter_benign: bool = True) -> IOCCollection:
    """Extract IOCs from text.
    
    Args:
        text: Text to analyze
        filter_benign: Whether to filter out known benign IOCs
        
    Returns:
        Collection of extracted IOCs
    """
    iocs = IOCCollection()
    
    # Extract IPv4
    for match in re.finditer(PATTERNS["ipv4"], text):
        ip = match.group()
        if not filter_benign or not is_benign("ips", ip):
            if ip not in iocs.ipv4:
                iocs.ipv4.append(ip)
    
    # Extract IPv6
    for match in re.finditer(PATTERNS["ipv6"], text):
        ip = match.group()
        if ip not in iocs.ipv6:
            iocs.ipv6.append(ip)
    
    # Extract URLs first (before domains to avoid duplicates)
    for match in re.finditer(PATTERNS["url"], text, re.IGNORECASE):
        url = match.group().rstrip('.,;:!?"\')]')
        if url not in iocs.urls:
            iocs.urls.append(url)
    
    # Extract domains (excluding those in URLs)
    url_domains = set()
    for url in iocs.urls:
        domain_match = re.search(r'https?://([^/]+)', url)
        if domain_match:
            url_domains.add(domain_match.group(1).lower())
    
    for match in re.finditer(PATTERNS["domain"], text):
        domain = match.group().lower()
        if domain not in url_domains:
            if not filter_benign or not is_benign("domains", domain):
                if domain not in iocs.domains:
                    iocs.domains.append(domain)
    
    # Extract emails
    for match in re.finditer(PATTERNS["email"], text):
        email = match.group()
        if email not in iocs.emails:
            iocs.emails.append(email)
    
    # Extract hashes (check length to avoid overlaps)
    potential_hashes = set()
    
    # SHA256 first (longest)
    for match in re.finditer(PATTERNS["sha256"], text, re.IGNORECASE):
        hash_val = match.group().lower()
        if hash_val not in iocs.sha256:
            iocs.sha256.append(hash_val)
            potential_hashes.add(hash_val)
    
    # SHA1 (exclude substrings of SHA256)
    for match in re.finditer(PATTERNS["sha1"], text, re.IGNORECASE):
        hash_val = match.group().lower()
        if not any(hash_val in h for h in iocs.sha256):
            if hash_val not in iocs.sha1:
                iocs.sha1.append(hash_val)
                potential_hashes.add(hash_val)
    
    # MD5 (exclude substrings of SHA1/SHA256)
    for match in re.finditer(PATTERNS["md5"], text, re.IGNORECASE):
        hash_val = match.group().lower()
        if not any(hash_val in h for h in potential_hashes):
            if hash_val not in iocs.md5:
                iocs.md5.append(hash_val)
    
    # Extract filenames
    for match in re.finditer(PATTERNS["filename"], text, re.IGNORECASE):
        filename = match.group()
        if filename not in iocs.filenames:
            iocs.filenames.append(filename)
    
    # Extract registry keys
    for match in re.finditer(PATTERNS["registry"], text):
        key = match.group()
        if key not in iocs.registry_keys:
            iocs.registry_keys.append(key)
    
    return iocs


def analyze_iocs(iocs: IOCCollection) -> dict[str, Any]:
    """Analyze extracted IOCs for threat assessment.
    
    Args:
        iocs: Extracted IOC collection
        
    Returns:
        Analysis results
    """
    result = {
        "total_iocs": iocs.count(),
        "summary": {},
        "high_priority": [],
        "assessment": "clean",
    }
    
    # Summarize counts
    for ioc_type, values in iocs.to_dict().items():
        if values:
            result["summary"][ioc_type] = len(values)
    
    # Identify high-priority IOCs
    # External IPs
    for ip in iocs.ipv4:
        if not is_benign("ips", ip):
            result["high_priority"].append({
                "type": "ipv4",
                "value": ip,
                "reason": "External IP address",
            })
    
    # Executable files
    exe_extensions = [".exe", ".dll", ".scr", ".ps1", ".vbs", ".js", ".bat"]
    for filename in iocs.filenames:
        if any(filename.lower().endswith(ext) for ext in exe_extensions):
            result["high_priority"].append({
                "type": "filename",
                "value": filename,
                "reason": "Executable file",
            })
    
    # Hashes (always noteworthy)
    for hash_val in iocs.sha256[:5]:  # Limit to top 5
        result["high_priority"].append({
            "type": "sha256",
            "value": hash_val,
            "reason": "File hash - verify with threat intelligence",
        })
    
    # Assessment
    if len(result["high_priority"]) > 5:
        result["assessment"] = "suspicious"
    elif len(result["high_priority"]) > 0:
        result["assessment"] = "review_needed"
    
    return result


if __name__ == "__main__":
    # Test data
    sample_text = """
    Threat Report:
    
    The malware connects to 45.33.32.156 and downloads payload from 
    https://malicious-domain.tk/payload.exe
    
    File hashes:
    MD5: d41d8cd98f00b204e9800998ecf8427e
    SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    
    Persistence via registry:
    HKLM\Software\Microsoft\Windows\CurrentVersion\Run\malware
    
    Contact: attacker@evil.com
    
    Drops file: trojan.exe in C:\Windows\Temp\
    """
    
    print("IOC Extraction Results:")
    print("=" * 50)
    
    iocs = extract_iocs(sample_text)
    analysis = analyze_iocs(iocs)
    
    print(f"\nTotal IOCs: {analysis['total_iocs']}")
    print(f"Assessment: {analysis['assessment']}")
    
    print("\nSummary:")
    for ioc_type, count in analysis["summary"].items():
        print(f"  {ioc_type}: {count}")
    
    print("\nHigh Priority IOCs:")
    for item in analysis["high_priority"]:
        print(f"  [{item['type']}] {item['value']}")
        print(f"    Reason: {item['reason']}")
