"""Thresholds and limits for web threat analysis."""

# Soft input cap (bytes); larger inputs are truncated with parse_status flag.
MAX_INPUT_BYTES = 256 * 1024

# Minimum corroboration: two independent pattern signals above this combined weight
# may justify high/critical without param_context/ast_sink (design.md rule).
PATTERN_CORROBORATION_WEIGHT = 0.85

# Severity caps for pattern-only findings on full blob (no structured location).
FULL_BLOB_PATTERN_MAX_SEVERITY = "medium"
