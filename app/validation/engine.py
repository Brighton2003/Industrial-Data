"""Validation engine. Pure functions: no database, API or dashboard imports."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence

from app.models.tags import TagConfig


class Quality(str, Enum):
    GOOD = "GOOD"
    MISSING = "MISSING"
    STALE = "STALE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    FLATLINE = "FLATLINE"
    INVALID = "INVALID"


def _to_number(value: Any) -> Optional[float]:
    """Return float for real numbers, None otherwise (bools and NaN/inf rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def parse_timestamp(ts: Any) -> Optional[datetime]:
    """Parse ISO string or datetime into an aware UTC datetime; None if impossible."""
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def check_missing(value: Any) -> bool:
    """True if the value is missing (None or blank string)."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def check_range(value: float, tag: TagConfig) -> bool:
    """True if the value lies inside the engineering range (inclusive)."""
    return tag.min <= value <= tag.max


def check_freshness(
    timestamp: Any, tag: TagConfig, now: Optional[datetime] = None
) -> Optional[bool]:
    """True if fresh, False if older than max_age_seconds, None if timestamp unparseable."""
    dt = parse_timestamp(timestamp)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = (now - dt).total_seconds()
    return age <= tag.max_age_seconds


def check_flatline(
    value: float, history: Sequence[Any], tag: TagConfig
) -> bool:
    """True if `value` plus preceding history gives >= flatline_samples identical readings.

    `history` is the previous numeric values, oldest first (excluding `value`).
    """
    needed = tag.flatline_samples
    if needed < 2:
        return False
    prior = [h for h in (_to_number(x) for x in history) if h is not None]
    run = 1
    for h in reversed(prior):
        if h == value:
            run += 1
        else:
            break
    return run >= needed


def validate_value(
    value: Any,
    timestamp: Any,
    tag: TagConfig,
    history: Sequence[Any] = (),
    now: Optional[datetime] = None,
) -> Quality:
    """Validate one reading. Check order: MISSING, INVALID, STALE, OUT_OF_RANGE, FLATLINE."""
    if check_missing(value):
        return Quality.MISSING
    number = _to_number(value)
    if number is None:
        return Quality.INVALID
    fresh = check_freshness(timestamp, tag, now)
    if fresh is None:
        return Quality.INVALID
    if not fresh:
        return Quality.STALE
    if not check_range(number, tag):
        return Quality.OUT_OF_RANGE
    if check_flatline(number, history, tag):
        return Quality.FLATLINE
    return Quality.GOOD


def validate_record(
    record: Mapping[str, Any],
    tags: Mapping[str, TagConfig],
    history: Optional[Mapping[str, Sequence[Any]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Quality]:
    """Validate a whole record. Every configured tag gets a result;
    a tag absent from the record is MISSING. Unknown keys are ignored."""
    history = history or {}
    ts = record.get("timestamp")
    # Optional per-tag timestamps let a single tag be stale while others are fresh.
    tag_ts = record.get("tag_timestamps") or {}
    return {
        name: validate_value(
            record.get(name), tag_ts.get(name, ts), tag, history.get(name, ()), now
        )
        for name, tag in tags.items()
    }
