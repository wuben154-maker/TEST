"""Feature extractors (XSS/SQLi) reused from legacy heuristics on parameter values."""

from .sqli_patterns import detect_sqli
from .xss_patterns import detect_xss

__all__ = ["detect_sqli", "detect_xss"]
