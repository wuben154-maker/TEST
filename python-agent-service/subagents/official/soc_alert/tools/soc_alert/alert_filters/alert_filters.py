"""Alert segmentation, rule filtering, and aggregation helpers for SOC triage.

Encoding:
    - All APIs accept ``str`` (Unicode). Callers must decode bytes with UTF-8 (or a
      known encoding) before calling; this module does not interpret raw bytes.
    - Segment delimiter is ASCII ``#`` (U+0023) repeated four or more times in a row.
      Splitting is done on code points, so UTF-8 text in segments is preserved.
    - YAML rule files are read with UTF-8.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from app.config.settings import SERVICE_ROOT

logger = logging.getLogger(__name__)

# Common alert id keys (first match wins).
_ALERT_ID_KEYS = (
    "id",
    "alert_id",
    "_id",
    "uuid",
    "event_id",
    "incident_id",
    "signature_id",
)


def extract_alert_id(alert: dict[str, Any]) -> str | None:
    """Return a string alert identifier if *alert* has a known id field."""
    for key in _ALERT_ID_KEYS:
        val = alert.get(key)
        if val is None or val == "":
            continue
        return str(val)
    return None


# Top-level keys ignored for :class:`AlertAggregator` bucket hash (instance identity only).
# ``signature_id`` is kept so different rules/signatures do not merge.
_AGGREGATION_HASH_EXCLUDE_KEYS = frozenset(
    {
        "id",
        "alert_id",
        "_id",
        "uuid",
        "event_id",
        "incident_id",
    }
)

# Fields commonly volatile across repeated alerts; ignored in fallback hash.
_AGGREGATION_VOLATILE_FIELDS = frozenset(
    {
        "timestamp",
        "time",
        "time_generated",
        "created_at",
        "updated_at",
        "first_seen",
        "last_seen",
    }
)


def aggregation_bucket_hash(alert: dict[str, Any]) -> str:
    """8-char MD5 hex for *alert* content used as aggregator cache key.

    Excludes instance id fields so two alerts that differ only by ``id`` (etc.) share one bucket.
    """
    ignore = _AGGREGATION_HASH_EXCLUDE_KEYS | _AGGREGATION_VOLATILE_FIELDS
    items = sorted((k, v) for k, v in alert.items() if k not in ignore)
    return hashlib.md5(str(items).encode("utf-8")).hexdigest()[:8]


def _filter_batch_log_dir() -> Path:
    env_dir = (os.getenv("SOC_ALERT_FILTER_LOG_DIR", "") or "").strip()
    if env_dir:
        return Path(env_dir)
    return SERVICE_ROOT / "logs"


# Four or more consecutive '#' (ASCII) as alert boundary.
_HASH_DELIMITER_PATTERN = re.compile(r"#{4,}")


def _to_eval_alert_view(value: Any) -> Any:
    """Recursively wrap dicts so rule expressions can use ``alert.foo`` and ``alert.get('foo')``."""
    if isinstance(value, dict):
        return _EvalAlertView(value)
    if isinstance(value, list):
        return [_to_eval_alert_view(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_to_eval_alert_view(v) for v in value)
    return value


class _EvalAlertView:
    """Dict-like rule context with attribute access for YAML expressions."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        return _to_eval_alert_view(self._data.get(key, default))

    def __getitem__(self, key: str) -> Any:
        return _to_eval_alert_view(self._data[key])

    def __getattr__(self, name: str) -> Any:
        return _to_eval_alert_view(self._data.get(name))

    def as_dict(self) -> dict[str, Any]:
        return self._data


def split_alert_text_segments(text: str) -> list[str]:
    """Split *text* into segments using 4+ consecutive ``#`` as delimiter.

    Strips each segment and drops empty strings. Delimiter runs are not included
    in any segment.
    """
    if not text:
        return []
    parts = _HASH_DELIMITER_PATTERN.split(text)
    return [p.strip() for p in parts if p.strip()]


def alert_dict_from_segment(segment: str) -> dict[str, Any]:
    """Turn one segment into an alert dict for rules / aggregation.

    If the trimmed segment is valid JSON object/array, returns that structure
    (objects used as a single alert dict; arrays are wrapped as
    ``{\"items\": ...}``). Otherwise wraps text in ``{\"raw_alert_text\": ...}``.
    """
    s = segment.strip()
    if not s:
        return {}
    try:
        parsed: Any = json.loads(s)
    except json.JSONDecodeError:
        return {"raw_alert_text": s}
    if isinstance(parsed, dict):
        return dict(parsed)
    if isinstance(parsed, list):
        return {"items": parsed}
    return {"raw_alert_text": s, "parsed_scalar": parsed}


def default_system_rules_path() -> Path:
    """Resolve default ``system_rules.yaml`` next to this package."""
    override = (os.getenv("SOC_ALERT_SYSTEM_RULES_PATH", "") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "system_rules.yaml"


class SystemRuleEngine:
    def __init__(self, rule_file: str | Path | None = None) -> None:
        path = Path(rule_file) if rule_file is not None else default_system_rules_path()
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except yaml.YAMLError as exc:
                logger.error("Failed to parse system rules YAML: %s (%s)", path, exc)
                data = {}
            raw_rules = data.get("rules")
            self.rules: list[dict[str, Any]] = list(raw_rules) if isinstance(raw_rules, list) else []
        else:
            self.rules = []

    def evaluate_with_meta(self, alert: dict[str, Any]) -> tuple[str, str | None]:
        """Return ``(action, matched_rule_name)``. *action* is normalized to known literals."""
        eval_alert = _to_eval_alert_view(alert)
        for rule in self.rules:
            try:
                if eval(rule["condition"], {}, {"alert": eval_alert, "re": re}):
                    raw = rule.get("action", "pass")
                    act = str(raw) if raw is not None else "pass"
                    if act not in ("discard", "pass", "escalate"):
                        act = "pass"
                    name = rule.get("name")
                    rname = str(name) if name is not None else None
                    return act, rname
            except Exception as exc:
                logger.warning("rule %s failed: %s", rule.get("name", "?"), exc)
        return "pass", None

    def evaluate(self, alert: dict[str, Any]) -> str:
        """Evaluate *alert*; return ``discard``, ``pass``, or ``escalate``."""
        action, _ = self.evaluate_with_meta(alert)
        return action

    def add_rule(
        self,
        name: str,
        condition: str,
        action: str = "discard",
        description: str = "",
    ) -> None:
        self.rules.append(
            {
                "name": name,
                "condition": condition,
                "action": action,
                "description": description,
            }
        )


@dataclass
class AggregatedAlert:
    """Aggregated alert bucket."""

    base_alert: dict[str, Any]
    count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    related_alerts: list[dict[str, Any]] = field(default_factory=list)
    alert_hash: str = ""

    def __post_init__(self) -> None:
        if not self.alert_hash:
            self.alert_hash = self._generate_hash()
        if not self.related_alerts:
            self.related_alerts = [self.base_alert.copy()]

    def _generate_hash(self) -> str:
        key_parts = [
            str(self.base_alert.get("src_ip", "")),
            str(self.base_alert.get("dst_ip", "")),
            str(self.base_alert.get("alert_type", "")),
            str(self.base_alert.get("signature_id", "")),
        ]
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()[:8]


class AlertAggregator:
    """Merges alerts in a time window.

    Bucket selection is strategy-first:
      1) if ``strategy_key`` exists, use that strategy output as the primary grouping key;
      2) otherwise, fallback to :func:`aggregation_bucket_hash` (ignore id-like + volatile fields).
    """

    def __init__(
        self,
        time_window: int = 60,
        max_count: int = 100,
        aggregation_strategies: dict[str, Any] | None = None,
    ) -> None:
        self.time_window = time_window
        self.max_count = max_count
        self.aggregation_cache: dict[str, AggregatedAlert] = {}
        self.strategies = aggregation_strategies or self._default_strategies()
        self.stats: dict[str, Any] = {
            "total_alerts": 0,
            "aggregated_alerts": 0,
            "unique_alerts": 0,
            "compression_ratio": 0.0,
        }

    def _default_strategies(self) -> dict[str, Any]:
        return {
            "same_src_dst": lambda a: (
                f"{a.get('src_ip')}-{a.get('dst_ip')}-{a.get('alert_type')}"
                f"-{a.get('severity')}-{a.get('dst_port')}"
            ),
            "same_attacker": lambda a: f"{a.get('src_ip')}-{a.get('signature_id')}",
            "same_victim": lambda a: f"{a.get('dst_ip')}-{a.get('alert_type')}",
        }

    def _bucket_hash(self, alert: dict[str, Any], strategy_key: str) -> str:
        if strategy_key in self.strategies:
            try:
                group = self.strategies[strategy_key](alert)
                gtxt = "" if group is None else str(group).strip()
                # If strategy output is effectively empty/unknown, fallback to normalized content hash.
                if gtxt and "None" not in gtxt and "null" not in gtxt.lower():
                    raw = f"{strategy_key}:{gtxt}".encode("utf-8")
                    return hashlib.md5(raw).hexdigest()[:8]
            except Exception:
                logger.warning("aggregation strategy %s failed; fallback to hash", strategy_key)
        return aggregation_bucket_hash(alert)

    def add_alert(self, alert: dict[str, Any], strategy_key: str = "same_src_dst") -> dict[str, Any] | None:
        self.stats["total_alerts"] += 1
        now = time.time()
        alert_hash = self._bucket_hash(alert, strategy_key)
        if alert_hash in self.aggregation_cache:
            agg_alert = self.aggregation_cache[alert_hash]
            if now - agg_alert.first_seen <= self.time_window:
                agg_alert.count += 1
                agg_alert.last_seen = now
                agg_alert.related_alerts.append(alert.copy())
                if agg_alert.count >= self.max_count:
                    return self._finalize_aggregation(alert_hash)
                self.stats["aggregated_alerts"] += 1
                return None
            finalized = self._finalize_aggregation(alert_hash)
            self.aggregation_cache[alert_hash] = AggregatedAlert(base_alert=alert, alert_hash=alert_hash)
            self.stats["unique_alerts"] += 1
            return finalized
        self.aggregation_cache[alert_hash] = AggregatedAlert(base_alert=alert, alert_hash=alert_hash)
        self.stats["unique_alerts"] += 1
        return None

    def _finalize_aggregation(self, alert_hash: str) -> dict[str, Any] | None:
        if alert_hash not in self.aggregation_cache:
            return None
        agg_alert = self.aggregation_cache.pop(alert_hash)
        if agg_alert.count > 1:
            agg_alert.base_alert["aggregated_info"] = {
                "count": agg_alert.count,
                "time_window_sec": agg_alert.last_seen - agg_alert.first_seen,
                "first_seen": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(agg_alert.first_seen)),
                "last_seen": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(agg_alert.last_seen)),
                "is_aggregated": True,
            }
            if self.stats["total_alerts"] > 0:
                self.stats["compression_ratio"] = (
                    self.stats["aggregated_alerts"] / self.stats["total_alerts"]
                )
            return agg_alert.base_alert
        return None

    def flush_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for alert_hash in list(self.aggregation_cache.keys()):
            finalized = self._finalize_aggregation(alert_hash)
            if finalized:
                results.append(finalized)
        return results

    def drain_all_pending(self) -> list[dict[str, Any]]:
        """Pop every cached alert: singles as copies; multi-count with aggregated_info."""
        results: list[dict[str, Any]] = []
        for alert_hash in list(self.aggregation_cache.keys()):
            agg_alert = self.aggregation_cache.pop(alert_hash)
            if agg_alert.count > 1:
                agg_alert.base_alert["aggregated_info"] = {
                    "count": agg_alert.count,
                    "time_window_sec": agg_alert.last_seen - agg_alert.first_seen,
                    "first_seen": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(agg_alert.first_seen)),
                    "last_seen": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(agg_alert.last_seen)),
                    "is_aggregated": True,
                }
                if self.stats["total_alerts"] > 0:
                    self.stats["compression_ratio"] = (
                        self.stats["aggregated_alerts"] / self.stats["total_alerts"]
                    )
                results.append(agg_alert.base_alert)
            else:
                results.append(agg_alert.base_alert.copy())
        return results

    def get_stats(self) -> dict[str, Any]:
        return self.stats.copy()


RuleAction = Literal["discard", "pass", "escalate"]


@dataclass(frozen=True)
class DiscardedAlertInfo:
    """One segment dropped during :func:`filter_alert_batch`."""

    segment_index: int
    alert: dict[str, Any]
    filter_function: str
    detail: str


def _write_discarded_alerts_log(
    *,
    input_label: str,
    discarded: list[DiscardedAlertInfo],
) -> Path | None:
    """Write one JSON line per discarded alert; return log path or None if nothing to write."""
    if not discarded:
        return None
    log_dir = _filter_batch_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(input_label).stem.strip()) or "input"
    log_path = log_dir / f"{stamp}_alert_filter_discard_{safe}.log"
    utc_now = datetime.now(timezone.utc).isoformat()
    with open(log_path, encoding="utf-8", mode="w") as f:
        for d in discarded:
            alert_id = extract_alert_id(d.alert)
            line = {
                "ts_utc": utc_now,
                "input": input_label,
                "segment_index": d.segment_index,
                "alert_id": alert_id,
                "filter_function": d.filter_function,
                "detail": d.detail,
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return log_path


@dataclass
class FilteredAlertRecord:
    """One alert after rule evaluation (before aggregation drain)."""

    alert: dict[str, Any]
    rule_action: RuleAction


@dataclass
class AlertBatchFilterResult:
    """Outcome of :func:`filter_alert_batch`."""

    segments: list[str]
    kept_after_rules: list[FilteredAlertRecord]
    discarded: list[DiscardedAlertInfo]
    aggregated_alerts: list[dict[str, Any]]
    aggregator_stats: dict[str, Any]
    discard_log_path: str | None = None


def filter_alert_batch(
    raw_text: str,
    *,
    rule_engine: SystemRuleEngine | None = None,
    aggregator: AlertAggregator | None = None,
    strategy_key: str = "same_src_dst",
    write_discard_log: bool = True,
    input_label: str = "stdin",
) -> AlertBatchFilterResult:
    """Split *raw_text* on 4+ ``#``, parse segments, apply rules, then aggregate.

    - Segments that parse to empty dicts are skipped (not fed to rules).
    - ``discard`` removes the alert from aggregation; ``pass`` and ``escalate`` are kept.
    - Alerts that pass rules are fed to :class:`AlertAggregator`; any immediate
      outputs from ``add_alert`` plus :meth:`AlertAggregator.drain_all_pending`
      form ``aggregated_alerts``.
    - If *write_discard_log* is True and any alert is discarded or skipped, writes
      JSON lines under ``SERVICE_ROOT/logs`` (or ``SOC_ALERT_FILTER_LOG_DIR``), with
      ``alert_id`` when present and ``filter_function`` identifying the step.
    """
    segments = split_alert_text_segments(raw_text)
    engine = rule_engine if rule_engine is not None else SystemRuleEngine()
    agg = aggregator if aggregator is not None else AlertAggregator()

    kept_records: list[FilteredAlertRecord] = []
    discarded: list[DiscardedAlertInfo] = []
    aggregated_alerts: list[dict[str, Any]] = []

    for idx, seg in enumerate(segments):
        alert = alert_dict_from_segment(seg)
        if not alert:
            discarded.append(
                DiscardedAlertInfo(
                    segment_index=idx,
                    alert={},
                    filter_function="filter_alert_batch.skip_empty_parsed_alert",
                    detail="alert_dict_from_segment returned empty dict",
                )
            )
            continue
        action_raw, matched_rule = engine.evaluate_with_meta(alert)
        action: RuleAction
        if action_raw in ("discard", "pass", "escalate"):
            action = action_raw  # type: ignore[assignment]
        else:
            action = "pass"
        if action == "discard":
            detail = f"action=discard rule_name={matched_rule!r}"
            discarded.append(
                DiscardedAlertInfo(
                    segment_index=idx,
                    alert=alert,
                    filter_function="SystemRuleEngine.evaluate",
                    detail=detail,
                )
            )
            continue
        meta = alert.copy()
        meta["_filter_rule_action"] = action
        kept_records.append(FilteredAlertRecord(alert=meta, rule_action=action))
        burst = agg.add_alert(meta, strategy_key=strategy_key)
        if burst is not None:
            aggregated_alerts.append(burst)

    aggregated_alerts.extend(agg.drain_all_pending())

    log_path: Path | None = None
    if write_discard_log and discarded:
        log_path = _write_discarded_alerts_log(input_label=input_label, discarded=discarded)

    return AlertBatchFilterResult(
        segments=segments,
        kept_after_rules=kept_records,
        discarded=discarded,
        aggregated_alerts=aggregated_alerts,
        aggregator_stats=agg.get_stats(),
        discard_log_path=str(log_path) if log_path else None,
    )
