#!/usr/bin/env python3
"""Payload Decoder Script.

This script decodes various obfuscated and encoded payloads.
Used by the general-security skill for content analysis.
"""

import base64
import codecs
import html
import re
from typing import Any
from urllib.parse import unquote


def decode_base64(data: str) -> tuple[str | None, str]:
    """Decode Base64 encoded data.
    
    Args:
        data: Base64 encoded string
        
    Returns:
        Tuple of (decoded_string, encoding_used)
    """
    # Try standard base64
    try:
        # Remove whitespace
        clean = re.sub(r'\s', '', data)
        # Add padding if needed
        padding = 4 - len(clean) % 4
        if padding != 4:
            clean += '=' * padding
        
        decoded = base64.b64decode(clean)
        
        # Try to decode as text
        try:
            return decoded.decode('utf-8'), "base64-utf8"
        except UnicodeDecodeError:
            try:
                return decoded.decode('latin-1'), "base64-latin1"
            except Exception:
                return decoded.hex(), "base64-hex"
    except Exception:
        pass
    
    # Try URL-safe base64
    try:
        decoded = base64.urlsafe_b64decode(data + '==')
        return decoded.decode('utf-8', errors='replace'), "base64-urlsafe"
    except Exception:
        pass
    
    return None, "failed"


def decode_url(data: str) -> str:
    """Decode URL-encoded data.
    
    Args:
        data: URL-encoded string
        
    Returns:
        Decoded string
    """
    # Multiple passes for double encoding
    result = data
    for _ in range(3):  # Max 3 passes
        decoded = unquote(result)
        if decoded == result:
            break
        result = decoded
    return result


def decode_html_entities(data: str) -> str:
    """Decode HTML entities.
    
    Args:
        data: String with HTML entities
        
    Returns:
        Decoded string
    """
    return html.unescape(data)


def decode_unicode_escapes(data: str) -> str:
    """Decode Unicode escape sequences.
    
    Args:
        data: String with Unicode escapes (\uXXXX)
        
    Returns:
        Decoded string
    """
    try:
        # Handle \uXXXX format
        return codecs.decode(data, 'unicode_escape')
    except Exception:
        return data


def decode_hex(data: str) -> str | None:
    """Decode hex-encoded data.
    
    Args:
        data: Hex string (with or without \x prefix)
        
    Returns:
        Decoded string or None
    """
    try:
        # Remove common prefixes
        clean = data.replace('\\x', '').replace('0x', '').replace(' ', '')
        
        # Ensure even length
        if len(clean) % 2 != 0:
            clean = '0' + clean
        
        decoded = bytes.fromhex(clean)
        return decoded.decode('utf-8', errors='replace')
    except Exception:
        return None


def decode_xor(data: bytes, key: bytes) -> bytes:
    """XOR decode data with key.
    
    Args:
        data: Encoded bytes
        key: XOR key
        
    Returns:
        Decoded bytes
    """
    return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))


def detect_and_decode(data: str) -> dict[str, Any]:
    """Auto-detect encoding and decode.
    
    Args:
        data: Potentially encoded data
        
    Returns:
        Decoding results
    """
    result = {
        "original": data,
        "decoded": data,
        "encodings_detected": [],
        "decoding_chain": [],
    }
    
    current = data
    
    # Try URL decoding first
    url_decoded = decode_url(current)
    if url_decoded != current:
        result["encodings_detected"].append("url")
        result["decoding_chain"].append({
            "encoding": "url",
            "input": current[:100],
            "output": url_decoded[:100],
        })
        current = url_decoded
    
    # Try HTML entity decoding
    html_decoded = decode_html_entities(current)
    if html_decoded != current:
        result["encodings_detected"].append("html_entities")
        result["decoding_chain"].append({
            "encoding": "html_entities",
            "input": current[:100],
            "output": html_decoded[:100],
        })
        current = html_decoded
    
    # Try Base64 decoding
    if re.match(r'^[A-Za-z0-9+/=]+$', current.replace('\n', '').replace(' ', '')):
        b64_decoded, encoding = decode_base64(current)
        if b64_decoded and encoding != "failed":
            result["encodings_detected"].append("base64")
            result["decoding_chain"].append({
                "encoding": encoding,
                "input": current[:100],
                "output": b64_decoded[:100],
            })
            current = b64_decoded
    
    # Try Unicode escape decoding
    if '\\u' in current:
        unicode_decoded = decode_unicode_escapes(current)
        if unicode_decoded != current:
            result["encodings_detected"].append("unicode_escape")
            result["decoding_chain"].append({
                "encoding": "unicode_escape",
                "input": current[:100],
                "output": unicode_decoded[:100],
            })
            current = unicode_decoded
    
    # Try hex decoding
    if re.match(r'^(\\x[0-9a-fA-F]{2})+$', current) or re.match(r'^[0-9a-fA-F]+$', current):
        hex_decoded = decode_hex(current)
        if hex_decoded:
            result["encodings_detected"].append("hex")
            result["decoding_chain"].append({
                "encoding": "hex",
                "input": current[:100],
                "output": hex_decoded[:100],
            })
            current = hex_decoded
    
    result["decoded"] = current
    return result


def analyze_decoded_content(decoded: str) -> dict[str, Any]:
    """Analyze decoded content for suspicious patterns.
    
    Args:
        decoded: Decoded content
        
    Returns:
        Analysis results
    """
    result = {
        "content_type": "unknown",
        "suspicious_indicators": [],
        "risk_level": "low",
    }
    
    lower = decoded.lower()
    
    # Detect content type
    if '<script' in lower or 'javascript:' in lower:
        result["content_type"] = "javascript"
    elif '<html' in lower or '<!doctype' in lower:
        result["content_type"] = "html"
    elif 'powershell' in lower or '$env:' in lower:
        result["content_type"] = "powershell"
    elif 'cmd' in lower and '/c' in lower:
        result["content_type"] = "command"
    elif decoded.startswith('MZ') or decoded.startswith('TVq'):
        result["content_type"] = "executable"
    
    # Check for suspicious patterns
    suspicious_patterns = [
        (r'eval\s*\(', "eval() function"),
        (r'document\.write', "document.write()"),
        (r'fromCharCode', "String.fromCharCode()"),
        (r'\.exe\b', "executable reference"),
        (r'powershell', "PowerShell reference"),
        (r'cmd\.exe|cmd\s+/c', "cmd.exe reference"),
        (r'http[s]?://\d+\.\d+\.\d+\.\d+', "IP-based URL"),
        (r'WScript\.Shell', "WScript.Shell"),
        (r'ActiveXObject', "ActiveXObject"),
        (r'-enc\s+[A-Za-z0-9+/=]+', "encoded PowerShell"),
    ]
    
    for pattern, description in suspicious_patterns:
        if re.search(pattern, decoded, re.IGNORECASE):
            result["suspicious_indicators"].append(description)
    
    # Determine risk level
    indicator_count = len(result["suspicious_indicators"])
    if indicator_count >= 3:
        result["risk_level"] = "high"
    elif indicator_count >= 1:
        result["risk_level"] = "medium"
    
    return result


if __name__ == "__main__":
    # Test samples
    test_cases = [
        # Base64 encoded JavaScript
        "PGlmcmFtZSBzcmM9Imh0dHA6Ly9ldmlsLmNvbS9tYWx3YXJlIj48L2lmcmFtZT4=",
        # URL encoded
        "%3Cscript%3Ealert%28%27XSS%27%29%3C%2Fscript%3E",
        # HTML entities
        "&#60;script&#62;alert('XSS')&#60;/script&#62;",
        # Unicode escapes
        "\\u003cscript\\u003ealert('XSS')\\u003c/script\\u003e",
    ]
    
    print("Payload Decoding Tests:")
    print("=" * 50)
    
    for test in test_cases:
        print(f"\nInput: {test[:50]}...")
        result = detect_and_decode(test)
        print(f"Encodings: {', '.join(result['encodings_detected']) or 'None'}")
        print(f"Decoded: {result['decoded'][:100]}")
        
        analysis = analyze_decoded_content(result['decoded'])
        print(f"Content Type: {analysis['content_type']}")
        print(f"Risk Level: {analysis['risk_level']}")
