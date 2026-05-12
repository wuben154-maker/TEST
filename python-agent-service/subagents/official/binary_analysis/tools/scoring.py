"""ScoringTool — deterministic rule-engine verdict (FR-13, ADR-04).

The scoring pipeline has three layers, from pure to side-effectful:

1. :func:`load_rules` — parse ``config/scoring_rules.yaml`` into an
   immutable :class:`RuleSet` (cached on the default path).
2. :func:`score_snapshot` — pure function mapping an
   :class:`~schema.evidence_chain.EvidenceChainSnapshot`
   plus a :class:`RuleSet` to a :class:`ScoringResult`.  No I/O; trivially
   unit-testable (FR-13 AC-1/2/3/4/5/6/7).
3. :class:`ScoringTool` — LangChain ``BaseTool`` wrapper that runs layer 2
   against the current :class:`~evidence_chain.store.EvidenceChainStore`
   and appends a single ``fact``-kind Indicator to the ``scoring`` bucket
   (FR-13 AC-7).

Namespace support (v1.1.0, FR-13 AC-7)
----------------------------------------

``scoring_rules.yaml`` v1.1+ uses a top-level ``binary:`` / ``document:``
namespace structure.  :func:`load_rules` detects the format automatically:

- **v1.1+ namespaced**: top-level ``rules_version:`` key, with ``binary:``
  and/or ``document:`` sub-keys.  Unknown namespaces are silently skipped
  (forward compatibility).
- **v1.0 flat (legacy)**: top-level ``version:`` key with rules/combos/
  thresholds directly at root.  The entire file is treated as the
  ``binary:`` namespace with a deprecation warning.  Verdict output is
  identical to the v1.0 engine (A-05 backward compatibility guarantee).

DocumentRole (FR-13 AC-4/5)
-----------------------------

When a ``document:`` namespace is present in the loaded rules, :func:`score_snapshot`
runs a second pass over the evidence chain using the document rules, then
evaluates the ``document_role_rules[]`` classifier (first-match semantics)
to emit :class:`~schema.document_enums.DocumentRole`.
The classification is fully deterministic — no LLM involvement.

Red lines
---------

- The rule engine is deterministic: same snapshot + same rules → same
  result.  No LLM, no randomness, no I/O inside :func:`score_snapshot`.
- Final verdict is always rule-authoritative (ADR-04).  When the
  LLM-supplied verdict (read from the ``llm_inferences`` bucket) diverges
  from the rule verdict, the LLM label is preserved as secondary evidence
  in ``verdict_divergence`` (FR-13 AC-9) but NEVER overrides the rule
  label.
- Rule revisions MUST bump the top-level ``rules_version`` (v1.1+) or
  ``version`` (v1.0) field in ``scoring_rules.yaml`` and be recorded in
  ``IMPL-PROGRESS.md`` (NFR-06 / NFR-13 audit requirement).  The version
  string is propagated into every scoring Indicator and ReportV1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from audit import log_indicator_write
from errors import BinaryAnalysisError
from evidence_chain.store import EvidenceChainStore
from schema.document_enums import DocumentRole, UnknownDowngradeReason
from schema.evidence_chain import (
    BUCKET_NAMES,
    Bucket,
    EvidenceChainSnapshot,
    canonical_bucket_str,
)
from schema.indicator import Confidence, Indicator, Severity
from schema.report import VerdictLabel

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / error class
# ---------------------------------------------------------------------------

_DEFAULT_RULES_PATH: Path = (
    Path(__file__).resolve().parents[1] / "config" / "scoring_rules.yaml"
)

_SEVERITY_VALUES = {s.value for s in Severity}
_CONFIDENCE_VALUES = {c.value for c in Confidence}

_SUPPORTED_MATCH_KEYS = {
    "severity_in",
    "confidence_in",
    "indicator_type",
    "source_fr",
    "data_equals",
    "data_tag_in",
}


class RuleEngineConfigError(BinaryAnalysisError):
    """Raised when ``scoring_rules.yaml`` is missing, malformed, or invalid.

    Maps to the ``TOOL_SCHEMA_INVALID`` error family (§5.1 / §3.3 input
    validation layer).  Triggered on:

    - missing file at the default path,
    - malformed YAML,
    - missing / non-SemVer ``version`` / ``rules_version``,
    - unknown ``bucket`` values,
    - unknown keys inside ``match``,
    - combo referencing an undefined rule ID.
    """

    error_code = "TOOL_SCHEMA_INVALID"


# ---------------------------------------------------------------------------
# Rule-set data model (plain dataclasses — no pydantic to keep this pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """Verdict-band thresholds loaded from YAML.

    Args:
        malicious: Score strictly greater than this value → MALICIOUS.
        suspicious: Score strictly greater than this (and <= `malicious`)
            → SUSPICIOUS.  Otherwise BENIGN.
        unknown_low_confidence_max: When every contributing Indicator
            carries LOW confidence AND the score is <= this value,
            downgrade the verdict to UNKNOWN (FR-13 AC-8).
    """

    malicious: int
    suspicious: int
    unknown_low_confidence_max: int


@dataclass(frozen=True)
class RuleMatch:
    """Structured predicate combined with logical AND."""

    severity_in: tuple[str, ...] | None = None
    confidence_in: tuple[str, ...] | None = None
    indicator_type: str | None = None
    source_fr: str | None = None
    data_equals: tuple[tuple[str, Any], ...] = ()
    data_tag_in: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Rule:
    """Single weighted rule in the engine."""

    id: str
    description: str
    bucket: Bucket
    weight: int
    match: RuleMatch


@dataclass(frozen=True)
class Combo:
    """Multi-rule correlation awarding a bonus weight (FR-13 AC-6)."""

    id: str
    description: str
    rule_ids: tuple[str, ...]
    bonus_weight: int


@dataclass(frozen=True)
class DocumentRoleRule:
    """Single entry in the ``document_role_rules[]`` classifier.

    Evaluation is first-match:

    - ``is_default=True``: unconditional fallback (must be last entry).
    - Otherwise: fires when ALL ``if_all`` rule IDs have fired AND at
      least one ``if_any`` rule ID has fired (empty ``if_any`` → no OR
      constraint, i.e. ``if_all`` alone is sufficient).
    """

    then: DocumentRole
    if_all: tuple[str, ...] = ()
    if_any: tuple[str, ...] = ()
    is_default: bool = False


@dataclass(frozen=True)
class DocumentRuleNamespace:
    """Document-specific scoring rules loaded from the ``document:`` namespace.

    Mirrors the ``binary:`` structure but adds ``document_role_rules`` for
    the FR-13 AC-4/5 document-role classifier.
    """

    thresholds: Thresholds
    rules: tuple[Rule, ...]
    combos: tuple[Combo, ...]
    document_role_rules: tuple[DocumentRoleRule, ...]


@dataclass(frozen=True)
class RuleSet:
    """Validated immutable rule set.

    The ``thresholds``, ``rules``, and ``combos`` fields always reflect the
    **binary** namespace (e2e01 callers are unaffected).  The optional
    ``document`` field carries the document namespace when present in the
    YAML (e2e02, FR-13 AC-3/4/5/7).
    """

    version: str
    thresholds: Thresholds
    rules: tuple[Rule, ...]
    combos: tuple[Combo, ...]
    document: DocumentRuleNamespace | None = None

    def without_combos(self) -> RuleSet:
        """Return a copy with all combos removed (used in AC-6 tests)."""
        doc: DocumentRuleNamespace | None = None
        if self.document is not None:
            doc = DocumentRuleNamespace(
                thresholds=self.document.thresholds,
                rules=self.document.rules,
                combos=(),
                document_role_rules=self.document.document_role_rules,
            )
        return RuleSet(
            version=self.version,
            thresholds=self.thresholds,
            rules=self.rules,
            combos=(),
            document=doc,
        )


# ---------------------------------------------------------------------------
# YAML loader + validation
# ---------------------------------------------------------------------------


def load_rules(path: Path | None = None) -> RuleSet:
    """Load and validate the scoring rule set.

    The default path (``config/scoring_rules.yaml``) is cached via
    :func:`_cached_default_rules`; passing an explicit ``path`` bypasses
    the cache so tests can point at a fixture file.

    Args:
        path: Override YAML location.  ``None`` → default shipped at
            ``examples/binary_analysis/config/scoring_rules.yaml``.

    Returns:
        Immutable :class:`RuleSet`.

    Raises:
        RuleEngineConfigError: On any schema / reference violation.
    """
    if path is None:
        return _cached_default_rules()
    return _load_rules_from_path(path)


@lru_cache(maxsize=1)
def _cached_default_rules() -> RuleSet:
    """Cached loader for the shipped YAML."""
    return _load_rules_from_path(_DEFAULT_RULES_PATH)


def _load_rules_from_path(path: Path) -> RuleSet:
    if not path.is_file():
        msg = f"scoring_rules.yaml not found at {path!s}"
        raise RuleEngineConfigError(
            msg, details={"reason": "rules_missing", "path": str(path)}
        )
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"scoring_rules.yaml is not valid YAML: {exc}"
        raise RuleEngineConfigError(
            msg, details={"reason": "yaml_parse_error", "path": str(path)}
        ) from exc
    if not isinstance(parsed, dict):
        msg = f"scoring_rules.yaml must be a mapping: {path!s}"
        raise RuleEngineConfigError(
            msg, details={"reason": "root_not_mapping", "path": str(path)}
        )
    return _dispatch_rules_mapping(parsed, source=path)


def _dispatch_rules_mapping(doc: dict[str, Any], *, source: Path) -> RuleSet:
    """Detect format (namespaced v1.1+ vs flat v1.0) and delegate."""
    is_namespaced = "binary" in doc or "document" in doc
    if is_namespaced:
        return _load_namespaced(doc, source=source)
    _logger.warning(
        "scoring_rules.yaml at %s uses legacy flat format (no 'binary:' / "
        "'document:' namespace keys); treating as binary: namespace. "
        "Upgrade to v1.1+ namespaced format to suppress this warning.",
        source,
    )
    return _load_flat_as_binary(doc, source=source)


def _load_namespaced(doc: dict[str, Any], *, source: Path) -> RuleSet:
    """Load a v1.1+ namespaced YAML (``rules_version:`` + ``binary:`` / ``document:``)."""
    version = doc.get("rules_version")
    if not isinstance(version, str) or not version:
        msg = (
            "namespaced scoring_rules.yaml must define a non-empty "
            "'rules_version' string"
        )
        raise RuleEngineConfigError(
            msg, details={"reason": "missing_version", "path": str(source)}
        )

    binary_doc = doc.get("binary")
    if not isinstance(binary_doc, dict):
        msg = "namespaced scoring_rules.yaml must have a 'binary' namespace mapping"
        raise RuleEngineConfigError(
            msg, details={"reason": "binary_namespace_missing", "path": str(source)}
        )
    thresholds = _parse_thresholds(binary_doc.get("thresholds"), source=source)
    rules = _parse_rules(binary_doc.get("rules"), source=source)
    combos = _parse_combos(
        binary_doc.get("combos"), known_rule_ids={r.id for r in rules}, source=source
    )

    document: DocumentRuleNamespace | None = None
    doc_ns_raw = doc.get("document")
    if isinstance(doc_ns_raw, dict):
        document = _parse_document_namespace(doc_ns_raw, source=source)
    elif doc_ns_raw is not None:
        _logger.warning(
            "scoring_rules.yaml 'document' namespace at %s is not a mapping; "
            "skipping (FR-13 AC-7).",
            source,
        )

    # Log (but do not error on) unknown top-level namespaces — forward compat.
    known_keys = {"rules_version", "binary", "document"}
    for key in doc:
        if key not in known_keys:
            _logger.debug(
                "Skipping unknown scoring namespace %r in %s (FR-13 AC-7).", key, source
            )

    return RuleSet(
        version=version,
        thresholds=thresholds,
        rules=rules,
        combos=combos,
        document=document,
    )


def _load_flat_as_binary(doc: dict[str, Any], *, source: Path) -> RuleSet:
    """Load legacy v1.0 flat format treating whole document as ``binary:`` namespace."""
    version = doc.get("version")
    if not isinstance(version, str) or not version:
        msg = "scoring_rules.yaml must define a non-empty 'version' string"
        raise RuleEngineConfigError(
            msg, details={"reason": "missing_version", "path": str(source)}
        )
    thresholds = _parse_thresholds(doc.get("thresholds"), source=source)
    rules = _parse_rules(doc.get("rules"), source=source)
    combos = _parse_combos(
        doc.get("combos"), known_rule_ids={r.id for r in rules}, source=source
    )
    return RuleSet(
        version=version,
        thresholds=thresholds,
        rules=rules,
        combos=combos,
        document=None,
    )


def _parse_document_namespace(
    doc_ns: dict[str, Any], *, source: Path
) -> DocumentRuleNamespace:
    """Parse the ``document:`` namespace into a :class:`DocumentRuleNamespace`."""
    thresholds = _parse_thresholds(doc_ns.get("thresholds"), source=source)
    rules: tuple[Rule, ...] = ()
    if doc_ns.get("rules") is not None:
        rules = _parse_rules(doc_ns["rules"], source=source)
    combos = _parse_combos(
        doc_ns.get("combos"), known_rule_ids={r.id for r in rules}, source=source
    )
    role_rules = _parse_document_role_rules(
        doc_ns.get("document_role_rules"),
        known_rule_ids={r.id for r in rules},
        source=source,
    )
    return DocumentRuleNamespace(
        thresholds=thresholds,
        rules=rules,
        combos=combos,
        document_role_rules=role_rules,
    )


def _parse_document_role_rules(
    raw: Any,
    *,
    known_rule_ids: set[str],
    source: Path,
) -> tuple[DocumentRoleRule, ...]:
    """Parse the ``document_role_rules[]`` list into a tuple of :class:`DocumentRoleRule`."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        msg = "document 'document_role_rules' must be a list"
        raise RuleEngineConfigError(
            msg, details={"reason": "doc_role_rules_not_list", "path": str(source)}
        )
    out: list[DocumentRoleRule] = []
    for idx, entry in enumerate(raw):
        out.append(
            _parse_document_role_rule_entry(
                entry, index=idx, known_rule_ids=known_rule_ids, source=source
            )
        )
    return tuple(out)


def _parse_document_role_rule_entry(
    entry: Any,
    *,
    index: int,
    known_rule_ids: set[str],
    source: Path,
) -> DocumentRoleRule:
    """Parse a single ``document_role_rules`` entry."""
    if not isinstance(entry, dict):
        msg = f"document_role_rules[{index}] must be a mapping"
        raise RuleEngineConfigError(
            msg,
            details={
                "reason": "doc_role_rule_not_mapping",
                "index": index,
                "path": str(source),
            },
        )
    if "default" in entry:
        default_val = entry["default"]
        try:
            role = DocumentRole(str(default_val))
        except ValueError as exc:
            msg = (
                f"document_role_rules[{index}] 'default' has unknown DocumentRole "
                f"value {default_val!r}"
            )
            raise RuleEngineConfigError(
                msg,
                details={"reason": "unknown_document_role", "index": index},
            ) from exc
        return DocumentRoleRule(then=role, is_default=True)

    then_val = entry.get("then")
    if not isinstance(then_val, str):
        msg = f"document_role_rules[{index}] must have a string 'then' value"
        raise RuleEngineConfigError(
            msg,
            details={"reason": "doc_role_rule_missing_then", "index": index},
        )
    try:
        role = DocumentRole(then_val)
    except ValueError as exc:
        msg = (
            f"document_role_rules[{index}] 'then' has unknown DocumentRole "
            f"value {then_val!r}"
        )
        raise RuleEngineConfigError(
            msg,
            details={"reason": "unknown_document_role", "index": index},
        ) from exc

    if_all_raw: list[str] = entry.get("if_all") or []
    if_any_raw: list[str] = entry.get("if_any") or []

    if not isinstance(if_all_raw, list) or not all(
        isinstance(v, str) for v in if_all_raw
    ):
        msg = f"document_role_rules[{index}] 'if_all' must be a list of strings"
        raise RuleEngineConfigError(
            msg, details={"reason": "doc_role_if_all_invalid", "index": index}
        )
    if not isinstance(if_any_raw, list) or not all(
        isinstance(v, str) for v in if_any_raw
    ):
        msg = f"document_role_rules[{index}] 'if_any' must be a list of strings"
        raise RuleEngineConfigError(
            msg, details={"reason": "doc_role_if_any_invalid", "index": index}
        )

    # Validate rule references — warn but do not error to allow forward compat.
    for rid in (*if_all_raw, *if_any_raw):
        if rid not in known_rule_ids:
            _logger.warning(
                "document_role_rules[%d] references rule %r which is not defined "
                "in the document namespace; it will never fire.",
                index,
                rid,
            )

    return DocumentRoleRule(
        then=role,
        if_all=tuple(if_all_raw),
        if_any=tuple(if_any_raw),
    )


def _parse_thresholds(raw: Any, *, source: Path) -> Thresholds:
    if not isinstance(raw, dict):
        msg = "scoring_rules.yaml 'thresholds' must be a mapping"
        raise RuleEngineConfigError(
            msg, details={"reason": "thresholds_missing", "path": str(source)}
        )
    try:
        return Thresholds(
            malicious=int(raw["malicious"]),
            suspicious=int(raw["suspicious"]),
            unknown_low_confidence_max=int(raw["unknown_low_confidence_max"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"scoring_rules.yaml 'thresholds' is invalid: {exc}"
        raise RuleEngineConfigError(
            msg, details={"reason": "thresholds_invalid", "path": str(source)}
        ) from exc


def _parse_rules(raw: Any, *, source: Path) -> tuple[Rule, ...]:
    if not isinstance(raw, list) or not raw:
        msg = "scoring_rules.yaml 'rules' must be a non-empty list"
        raise RuleEngineConfigError(
            msg, details={"reason": "rules_missing", "path": str(source)}
        )
    seen_ids: set[str] = set()
    out: list[Rule] = []
    for idx, entry in enumerate(raw):
        rule = _parse_rule_entry(entry, index=idx, source=source)
        if rule.id in seen_ids:
            msg = f"duplicate rule id '{rule.id}' in {source!s}"
            raise RuleEngineConfigError(
                msg, details={"reason": "duplicate_rule_id", "rule_id": rule.id}
            )
        seen_ids.add(rule.id)
        out.append(rule)
    return tuple(out)


def _parse_rule_entry(entry: Any, *, index: int, source: Path) -> Rule:
    if not isinstance(entry, dict):
        msg = f"scoring_rules.yaml 'rules[{index}]' must be a mapping"
        raise RuleEngineConfigError(
            msg, details={"reason": "rule_not_mapping", "path": str(source)}
        )
    try:
        rule_id = str(entry["id"])
        description = str(entry.get("description", ""))
        bucket_raw = str(entry["bucket"])
        weight = int(entry["weight"])
        match_raw = entry.get("match") or {}
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"scoring_rules.yaml 'rules[{index}]' missing required field: {exc}"
        raise RuleEngineConfigError(
            msg, details={"reason": "rule_fields_invalid", "path": str(source)}
        ) from exc
    bucket_raw = canonical_bucket_str(bucket_raw)
    if bucket_raw not in BUCKET_NAMES:
        msg = (
            f"scoring_rules.yaml 'rules[{index}]' references unknown bucket "
            f"'{bucket_raw}'; allowed: {BUCKET_NAMES!r}"
        )
        raise RuleEngineConfigError(
            msg, details={"reason": "unknown_bucket", "bucket": bucket_raw}
        )
    match = _parse_match(match_raw, rule_id=rule_id, source=source)
    return Rule(
        id=rule_id,
        description=description,
        bucket=Bucket(bucket_raw),
        weight=weight,
        match=match,
    )


def _parse_match(raw: Any, *, rule_id: str, source: Path) -> RuleMatch:
    if not isinstance(raw, dict):
        msg = f"rule '{rule_id}' 'match' must be a mapping"
        raise RuleEngineConfigError(
            msg, details={"reason": "match_not_mapping", "rule_id": rule_id}
        )
    unknown = set(raw.keys()) - _SUPPORTED_MATCH_KEYS
    if unknown:
        msg = (
            f"rule '{rule_id}' 'match' has unsupported keys: {sorted(unknown)!r}; "
            f"allowed: {sorted(_SUPPORTED_MATCH_KEYS)!r}"
        )
        raise RuleEngineConfigError(
            msg,
            details={
                "reason": "unknown_match_key",
                "rule_id": rule_id,
                "unknown_keys": sorted(unknown),
            },
        )
    severity_in = _parse_string_enum_list(
        raw.get("severity_in"),
        allowed=_SEVERITY_VALUES,
        field_name="severity_in",
        rule_id=rule_id,
    )
    confidence_in = _parse_string_enum_list(
        raw.get("confidence_in"),
        allowed=_CONFIDENCE_VALUES,
        field_name="confidence_in",
        rule_id=rule_id,
    )
    data_equals_raw = raw.get("data_equals") or {}
    if not isinstance(data_equals_raw, dict):
        msg = f"rule '{rule_id}' 'data_equals' must be a mapping"
        raise RuleEngineConfigError(
            msg, details={"reason": "data_equals_invalid", "rule_id": rule_id}
        )
    data_tag_in = _parse_optional_string_list(
        raw.get("data_tag_in"), field_name="data_tag_in", rule_id=rule_id
    )
    return RuleMatch(
        severity_in=severity_in,
        confidence_in=confidence_in,
        indicator_type=_opt_str(raw.get("indicator_type"), "indicator_type", rule_id),
        source_fr=_opt_str(raw.get("source_fr"), "source_fr", rule_id),
        data_equals=tuple(sorted(data_equals_raw.items())),
        data_tag_in=data_tag_in,
    )


def _opt_str(value: Any, field_name: str, rule_id: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"rule '{rule_id}' '{field_name}' must be a string"
        raise RuleEngineConfigError(
            msg, details={"reason": "field_not_string", "rule_id": rule_id}
        )
    return value


def _parse_optional_string_list(
    value: Any, *, field_name: str, rule_id: str
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        msg = f"rule '{rule_id}' '{field_name}' must be a list of strings"
        raise RuleEngineConfigError(
            msg, details={"reason": "field_not_str_list", "rule_id": rule_id}
        )
    return tuple(value)


def _parse_string_enum_list(
    value: Any, *, allowed: set[str], field_name: str, rule_id: str
) -> tuple[str, ...] | None:
    if value is None:
        return None
    parsed = _parse_optional_string_list(value, field_name=field_name, rule_id=rule_id)
    assert parsed is not None  # noqa: S101
    unknown = {v for v in parsed if v not in allowed}
    if unknown:
        msg = (
            f"rule '{rule_id}' '{field_name}' contains unknown value(s) "
            f"{sorted(unknown)!r}; allowed: {sorted(allowed)!r}"
        )
        raise RuleEngineConfigError(
            msg,
            details={
                "reason": "unknown_enum_value",
                "rule_id": rule_id,
                "field": field_name,
            },
        )
    return parsed


def _parse_combos(
    raw: Any, *, known_rule_ids: set[str], source: Path
) -> tuple[Combo, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        msg = "scoring_rules.yaml 'combos' must be a list"
        raise RuleEngineConfigError(
            msg, details={"reason": "combos_not_list", "path": str(source)}
        )
    out: list[Combo] = []
    seen: set[str] = set()
    for idx, entry in enumerate(raw):
        combo = _parse_combo_entry(
            entry, index=idx, known_rule_ids=known_rule_ids, source=source
        )
        if combo.id in seen:
            msg = f"duplicate combo id '{combo.id}' in {source!s}"
            raise RuleEngineConfigError(
                msg, details={"reason": "duplicate_combo_id", "combo_id": combo.id}
            )
        seen.add(combo.id)
        out.append(combo)
    return tuple(out)


def _parse_combo_entry(
    entry: Any, *, index: int, known_rule_ids: set[str], source: Path
) -> Combo:
    if not isinstance(entry, dict):
        msg = f"scoring_rules.yaml 'combos[{index}]' must be a mapping"
        raise RuleEngineConfigError(
            msg, details={"reason": "combo_not_mapping", "path": str(source)}
        )
    try:
        combo_id = str(entry["id"])
        description = str(entry.get("description", ""))
        rule_ids_raw = entry["rule_ids"]
        bonus_weight = int(entry["bonus_weight"])
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"scoring_rules.yaml 'combos[{index}]' missing required field: {exc}"
        raise RuleEngineConfigError(
            msg, details={"reason": "combo_fields_invalid", "path": str(source)}
        ) from exc
    if (
        not isinstance(rule_ids_raw, list)
        or not rule_ids_raw
        or not all(isinstance(v, str) for v in rule_ids_raw)
    ):
        msg = f"combo '{combo_id}' 'rule_ids' must be a non-empty list of strings"
        raise RuleEngineConfigError(
            msg, details={"reason": "combo_rule_ids_invalid", "combo_id": combo_id}
        )
    missing = [rid for rid in rule_ids_raw if rid not in known_rule_ids]
    if missing:
        msg = (
            f"combo '{combo_id}' references undefined rule id(s): {missing!r}; "
            f"known rules: {sorted(known_rule_ids)!r}"
        )
        raise RuleEngineConfigError(
            msg,
            details={
                "reason": "combo_unknown_rule",
                "combo_id": combo_id,
                "missing": missing,
            },
        )
    return Combo(
        id=combo_id,
        description=description,
        rule_ids=tuple(rule_ids_raw),
        bonus_weight=bonus_weight,
    )


# ---------------------------------------------------------------------------
# Scoring result model
# ---------------------------------------------------------------------------


class RuleHit(BaseModel):
    """Single rule / combo firing for audit trail."""

    rule_id: str
    weight: int
    matched_indicator_ids: list[str] = Field(default_factory=list)
    kind: Literal["rule", "combo"] = "rule"


class ScoringResult(BaseModel):
    """Deterministic scoring-engine output (FR-13 AC-1~7).

    Produced by :func:`score_snapshot` and embedded into the ``scoring``
    bucket Indicator by :class:`ScoringTool`.

    New in v1.1.0:

    - ``document_role``: :class:`~schema.document_enums.DocumentRole`
      emitted when a ``document:`` namespace is present in the loaded rules
      (FR-13 AC-4/5).  ``None`` for pure binary analysis.
    - ``unknown_downgrade_reason``: upgraded from a free string to a
      :class:`~schema.document_enums.UnknownDowngradeReason`
      enum (FR-13 AC-6).
    """

    rule_score: int = Field(ge=0, le=100)
    verdict_label: VerdictLabel
    llm_label: VerdictLabel | None = None
    verdict_divergence: str | None = None
    threat_classes: list[str] = Field(default_factory=list)
    threat_class_confidence: str | None = None
    family_name: str = "Unknown Family"
    family_confidence: str | None = None
    family_evidence_refs: list[str] = Field(default_factory=list)
    rules_version: str
    matched_rule_ids: list[str] = Field(default_factory=list)
    matched_combo_ids: list[str] = Field(default_factory=list)
    contributing_indicator_ids: list[str] = Field(default_factory=list)
    rule_hits: list[RuleHit] = Field(default_factory=list)
    unknown_downgrade_reason: UnknownDowngradeReason | None = None
    document_role: DocumentRole | None = None

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Matcher + pure scorer
# ---------------------------------------------------------------------------


def _indicator_matches(ind: Indicator, match: RuleMatch) -> bool:
    """Return True iff ``ind`` satisfies every predicate in ``match``."""
    if match.severity_in is not None and ind.severity.value not in match.severity_in:
        return False
    if match.confidence_in is not None:
        if ind.confidence is None or ind.confidence.value not in match.confidence_in:
            return False
    if match.indicator_type is not None and ind.indicator_type != match.indicator_type:
        return False
    if match.source_fr is not None and ind.source_fr != match.source_fr:
        return False
    for key, expected in match.data_equals:
        if ind.data.get(key) != expected:
            return False
    if match.data_tag_in is not None:
        tag = ind.data.get("tag")
        if not isinstance(tag, str) or tag not in match.data_tag_in:
            return False
    return True


@dataclass
class _RuleFiring:
    """Internal mutable record accumulated during scoring."""

    rule: Rule
    matched_indicator_ids: list[str] = field(default_factory=list)


def _fire_rules(
    snapshot: EvidenceChainSnapshot, rules: tuple[Rule, ...]
) -> dict[str, _RuleFiring]:
    """Return firings keyed by rule_id (empty mapping if no rule fired)."""
    firings: dict[str, _RuleFiring] = {}
    for rule in rules:
        bucket_indicators: list[Indicator] = list(getattr(snapshot, rule.bucket.value))
        matched = [
            ind for ind in bucket_indicators if _indicator_matches(ind, rule.match)
        ]
        if matched:
            firings[rule.id] = _RuleFiring(
                rule=rule, matched_indicator_ids=[i.id for i in matched]
            )
    return firings


def _fire_combos(
    firings: dict[str, _RuleFiring], combos: tuple[Combo, ...]
) -> list[Combo]:
    """Return combos whose member rules all fired."""
    fired: list[Combo] = []
    for combo in combos:
        if all(rid in firings for rid in combo.rule_ids):
            fired.append(combo)
    return fired


def _format_unsupported_ids(snapshot: EvidenceChainSnapshot) -> list[str]:
    """Return FR-01 E1 facts that force an UNKNOWN verdict."""
    return [
        ind.id
        for ind in snapshot.file_meta
        if ind.indicator_type == "format_unsupported"
    ]


def _compute_document_role(
    doc_firings: dict[str, _RuleFiring],
    role_rules: tuple[DocumentRoleRule, ...],
) -> DocumentRole:
    """Evaluate ``document_role_rules[]`` in first-match order.

    Args:
        doc_firings: Map of document rule IDs that fired.
        role_rules: Ordered tuple of :class:`DocumentRoleRule` entries.

    Returns:
        The :class:`~schema.document_enums.DocumentRole`
        of the first matching rule, or ``DocumentRole.CLEAN`` if no rule
        (including the default) matches.
    """
    for role_rule in role_rules:
        if role_rule.is_default:
            return role_rule.then
        all_ok = all(rid in doc_firings for rid in role_rule.if_all)
        any_ok = (not role_rule.if_any) or any(
            rid in doc_firings for rid in role_rule.if_any
        )
        if all_ok and any_ok:
            return role_rule.then
    return DocumentRole.CLEAN


# ---------------------------------------------------------------------------
# LLM inference extraction (AC-3 / AC-4 / AC-9)
# ---------------------------------------------------------------------------


def _extract_threat_classes(
    snapshot: EvidenceChainSnapshot,
) -> tuple[list[str], str | None]:
    """Return (classes, confidence_value) pulled from ``llm_inferences``.

    Scans for the first Indicator with ``indicator_type='threat_class'``
    carrying a ``data.classes`` list; returns its classes plus confidence.
    """
    for ind in snapshot.llm_inferences:
        if ind.indicator_type != "threat_class":
            continue
        classes = ind.data.get("classes")
        if isinstance(classes, list) and all(isinstance(c, str) for c in classes):
            conf = ind.confidence.value if ind.confidence is not None else None
            return list(classes), conf
    return [], None


def _extract_family(
    snapshot: EvidenceChainSnapshot,
) -> tuple[str, str | None, list[str]]:
    """Return (family_name, confidence, evidence_refs) from ``llm_inferences``.

    Falls back to ``"Unknown Family"`` when no ``family_candidate``
    Indicator is present (FR-13 AC-4).
    """
    for ind in snapshot.llm_inferences:
        if ind.indicator_type != "family_candidate":
            continue
        family = ind.data.get("family")
        if isinstance(family, str) and family:
            conf = ind.confidence.value if ind.confidence is not None else None
            return family, conf, list(ind.evidence_refs)
    return "Unknown Family", None, []


def _extract_llm_verdict(snapshot: EvidenceChainSnapshot) -> VerdictLabel | None:
    """Return the LLM-supplied verdict label, if any.

    Looks for the first ``indicator_type='verdict'`` Indicator in the
    ``llm_inferences`` bucket whose ``data.label`` is a valid
    :class:`VerdictLabel`.
    """
    for ind in snapshot.llm_inferences:
        if ind.indicator_type != "verdict":
            continue
        label = ind.data.get("label")
        if not isinstance(label, str):
            continue
        try:
            return VerdictLabel(label)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Verdict mapping
# ---------------------------------------------------------------------------


def _verdict_from_score(score: int, thresholds: Thresholds) -> VerdictLabel:
    if score > thresholds.malicious:
        return VerdictLabel.MALICIOUS
    if score > thresholds.suspicious:
        return VerdictLabel.SUSPICIOUS
    return VerdictLabel.BENIGN


def _all_contributing_low_confidence(
    snapshot: EvidenceChainSnapshot, contributing_ids: list[str]
) -> bool:
    """Return True iff every contributing Indicator has LOW confidence.

    Indicators without a confidence (``fact`` kind with ``None``) are
    treated as not-LOW so that purely deterministic fact-based hits do NOT
    trigger the AC-8 downgrade.  The downgrade targets the case where all
    signals are low-quality LLM inferences or explicitly LOW-confidence
    tool findings.
    """
    if not contributing_ids:
        return False
    id_set = set(contributing_ids)
    low_count = 0
    for field_name in snapshot.__class__.model_fields:
        for ind in getattr(snapshot, field_name):
            if ind.id not in id_set:
                continue
            if ind.confidence is None:
                return False
            if ind.confidence is not Confidence.LOW:
                return False
            low_count += 1
    return low_count > 0 and low_count == len(id_set)


# ---------------------------------------------------------------------------
# Pure scoring entry point
# ---------------------------------------------------------------------------


def score_snapshot(snapshot: EvidenceChainSnapshot, rules: RuleSet) -> ScoringResult:
    """Score an evidence-chain snapshot against a rule set (pure).

    The function runs two passes:

    1. **Binary namespace** (always present): fires ``rules.rules`` /
       ``rules.combos`` against ``snapshot`` to produce a binary sub-score.
    2. **Document namespace** (optional): fires ``rules.document.rules`` /
       ``rules.document.combos`` to produce a document sub-score, then
       evaluates ``document_role_rules[]`` to derive
       :class:`~schema.document_enums.DocumentRole`.

    The final ``rule_score`` is the clamped sum of both sub-scores.  The
    final ``verdict_label`` is derived from ``rule_score`` against the
    binary namespace ``thresholds``.

    Args:
        snapshot: Read-only snapshot from the evidence-chain store.
        rules: Validated rule set loaded via :func:`load_rules`.

    Returns:
        :class:`ScoringResult` carrying the rule score, final verdict,
        threat classification, family attribution, ``document_role``,
        audit trail, and any LLM-vs-rule divergence.
    """
    format_unsupported_ids = _format_unsupported_ids(snapshot)
    if format_unsupported_ids:
        return ScoringResult(
            rule_score=0,
            verdict_label=VerdictLabel.UNKNOWN,
            rules_version=rules.version,
            matched_rule_ids=["R-FORMAT-UNSUPPORTED"],
            contributing_indicator_ids=format_unsupported_ids,
            rule_hits=[
                RuleHit(
                    rule_id="R-FORMAT-UNSUPPORTED",
                    weight=0,
                    matched_indicator_ids=format_unsupported_ids,
                )
            ],
        )

    # ── Binary namespace scoring ──────────────────────────────────────────────
    firings = _fire_rules(snapshot, rules.rules)
    fired_combos = _fire_combos(firings, rules.combos)

    rule_hits: list[RuleHit] = []
    binary_score = 0
    contributing_ids: set[str] = set()

    for rid, firing in firings.items():
        binary_score += firing.rule.weight
        contributing_ids.update(firing.matched_indicator_ids)
        rule_hits.append(
            RuleHit(
                rule_id=rid,
                weight=firing.rule.weight,
                matched_indicator_ids=firing.matched_indicator_ids,
                kind="rule",
            )
        )

    for combo in fired_combos:
        binary_score += combo.bonus_weight
        rule_hits.append(
            RuleHit(
                rule_id=combo.id,
                weight=combo.bonus_weight,
                matched_indicator_ids=[],
                kind="combo",
            )
        )

    # ── Document namespace scoring ────────────────────────────────────────────
    doc_score = 0
    document_role: DocumentRole | None = None
    doc_firings: dict[str, _RuleFiring] = {}
    doc_fired_combos: list[Combo] = []

    if rules.document is not None:
        doc_firings = _fire_rules(snapshot, rules.document.rules)
        doc_fired_combos = _fire_combos(doc_firings, rules.document.combos)

        for rid, firing in doc_firings.items():
            doc_score += firing.rule.weight
            contributing_ids.update(firing.matched_indicator_ids)
            rule_hits.append(
                RuleHit(
                    rule_id=rid,
                    weight=firing.rule.weight,
                    matched_indicator_ids=firing.matched_indicator_ids,
                    kind="rule",
                )
            )

        for combo in doc_fired_combos:
            doc_score += combo.bonus_weight
            rule_hits.append(
                RuleHit(
                    rule_id=combo.id,
                    weight=combo.bonus_weight,
                    matched_indicator_ids=[],
                    kind="combo",
                )
            )

        document_role = _compute_document_role(
            doc_firings, rules.document.document_role_rules
        )

    # ── Final score + verdict ─────────────────────────────────────────────────
    raw_score = binary_score + doc_score
    clamped_score = max(0, min(100, raw_score))
    rule_verdict = _verdict_from_score(clamped_score, rules.thresholds)

    unknown_reason: UnknownDowngradeReason | None = None
    final_verdict = rule_verdict
    if (
        rule_verdict is not VerdictLabel.BENIGN
        and clamped_score <= rules.thresholds.unknown_low_confidence_max
        and _all_contributing_low_confidence(snapshot, sorted(contributing_ids))
    ):
        final_verdict = VerdictLabel.UNKNOWN
        unknown_reason = UnknownDowngradeReason.ALL_LOW_CONFIDENCE

    threat_classes, threat_conf = _extract_threat_classes(snapshot)
    family_name, family_conf, family_refs = _extract_family(snapshot)
    llm_label = _extract_llm_verdict(snapshot)

    divergence: str | None = None
    if llm_label is not None and llm_label != final_verdict:
        divergence = (
            f"rule verdict={final_verdict.value} (score={clamped_score}) "
            f"diverges from LLM verdict={llm_label.value}; "
            "rule verdict is authoritative per ADR-04."
        )

    all_firings = {**firings, **doc_firings}
    all_combo_ids = [c.id for c in fired_combos] + [c.id for c in doc_fired_combos]

    return ScoringResult(
        rule_score=clamped_score,
        verdict_label=final_verdict,
        llm_label=llm_label,
        verdict_divergence=divergence,
        threat_classes=threat_classes,
        threat_class_confidence=threat_conf,
        family_name=family_name,
        family_confidence=family_conf,
        family_evidence_refs=family_refs,
        rules_version=rules.version,
        matched_rule_ids=sorted(all_firings.keys()),
        matched_combo_ids=all_combo_ids,
        contributing_indicator_ids=sorted(contributing_ids),
        rule_hits=rule_hits,
        unknown_downgrade_reason=unknown_reason,
        document_role=document_role,
    )


# ---------------------------------------------------------------------------
# LangChain tool wrapper (AC-7 side effect)
# ---------------------------------------------------------------------------


_VERDICT_SEVERITY: dict[VerdictLabel, Severity] = {
    VerdictLabel.MALICIOUS: Severity.CRITICAL,
    VerdictLabel.SUSPICIOUS: Severity.WARNING,
    VerdictLabel.UNKNOWN: Severity.INFO,
    VerdictLabel.BENIGN: Severity.INFO,
}


class ScoringInput(BaseModel):
    """Input schema for :class:`ScoringTool`."""

    analysis_id: str

    model_config = ConfigDict(extra="forbid")


def _scoring_data_payload(result: ScoringResult) -> dict[str, Any]:
    """Serialise :class:`ScoringResult` into the Indicator ``data`` field.

    The payload is flattened so downstream consumers (C12 DecisionGateTool,
    C13 ReportGenTool) can read fields without re-running the engine.
    """
    payload = result.model_dump(mode="json")
    payload["verdict"] = result.verdict_label.value
    payload["llm_verdict"] = result.llm_label.value if result.llm_label else None
    return payload


class ScoringTool(BaseTool):
    """LangChain tool that runs the rule engine and writes the scoring bucket.

    Args:
        store: Shared per-analysis
            :class:`~evidence_chain.store.EvidenceChainStore`.
        rules_path: Override for the YAML location.  ``None`` uses the
            shipped default (cached).

    The tool is synchronous: :func:`score_snapshot` is pure and the single
    side effect (append one Indicator) is synchronous.
    """

    name: str = "scoring"
    description: str = (
        "Run the deterministic scoring rule engine over the current evidence "
        "chain. Produces Risk Score (0-100), Verdict (MALICIOUS / SUSPICIOUS "
        "/ BENIGN / UNKNOWN), threat-class list, malware-family attribution, "
        "document_role (clean / carrier / payload_host / infection_source for "
        "document analysis), and any LLM-vs-rule divergence note. Appends a "
        "single 'fact' Indicator to the 'scoring' bucket referencing every "
        "contributing Indicator ID (FR-13 AC-7)."
    )
    args_schema: type[BaseModel] = ScoringInput
    store: EvidenceChainStore
    rules_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        ScoringInput(**kwargs)
        try:
            rules = load_rules(self.rules_path)
        except RuleEngineConfigError as exc:
            return {
                "ok": False,
                "error_code": exc.error_code,
                "reason": exc.details.get("reason"),
                "message": exc.message,
                "details": exc.details,
            }
        snapshot = self.store.snapshot()
        result = score_snapshot(snapshot, rules)
        indicator = self._build_scoring_indicator(result)
        self.store.append(Bucket.scoring, indicator)
        log_indicator_write(
            indicator_id=indicator.id,
            bucket=Bucket.scoring.value,
            kind=indicator.kind,
            severity=indicator.severity.value,
            source_fr=indicator.source_fr,
        )
        payload = result.model_dump(mode="json")
        payload["indicator_id"] = indicator.id
        payload["verdict"] = result.verdict_label.value
        return payload

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        return self._run(**kwargs)

    def _build_scoring_indicator(self, result: ScoringResult) -> Indicator:
        """Build the ``scoring`` bucket Indicator for FR-13 AC-7."""
        return Indicator(
            source_fr="FR-13",
            indicator_type="scoring",
            severity=_VERDICT_SEVERITY[result.verdict_label],
            confidence=Confidence.HIGH,
            kind="fact",
            evidence_refs=list(result.contributing_indicator_ids),
            data=_scoring_data_payload(result),
        )


__all__ = [
    "Combo",
    "DocumentRoleRule",
    "DocumentRuleNamespace",
    "Rule",
    "RuleEngineConfigError",
    "RuleHit",
    "RuleMatch",
    "RuleSet",
    "ScoringInput",
    "ScoringResult",
    "ScoringTool",
    "Thresholds",
    "load_rules",
    "score_snapshot",
]
