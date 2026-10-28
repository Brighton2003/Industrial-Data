"""Pipeline: simulator record -> validation -> repository.

Contains no web or dashboard code, so other applications can reuse it.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Mapping, Optional

from app.database.base import Repository
from app.models.tags import TagConfig
from app.validation.engine import Quality, validate_record


class Pipeline:
    def __init__(self, tags: Mapping[str, TagConfig], repo: Repository):
        self.tags = dict(tags)
        self.repo = repo
        depth = max((t.flatline_samples for t in self.tags.values()), default=5)
        self._history: Dict[str, Deque[Any]] = {
            name: deque(maxlen=depth) for name in self.tags
        }
        self._seeded = False

    def _seed_history(self) -> None:
        """Rebuild flat-line history from the database so restarts don't lose it."""
        for name, tag in self.tags.items():
            for v in self.repo.recent_values(name, tag.flatline_samples):
                if v is not None:
                    self._history[name].append(v)
        self._seeded = True

    def process(
        self, record: Mapping[str, Any], now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Validate and store one record. Returns the stored rows."""
        if not isinstance(record, Mapping):
            raise TypeError("record must be a mapping")
        if not self._seeded:
            self._seed_history()

        history = {name: list(h) for name, h in self._history.items()}
        results = validate_record(record, self.tags, history, now)
        tag_ts = record.get("tag_timestamps") or {}
        ts = record.get("timestamp")

        rows: List[Dict[str, Any]] = []
        for name, tag in self.tags.items():
            raw = record.get(name)
            quality = results[name]
            numeric = (
                float(raw)
                if isinstance(raw, (int, float)) and not isinstance(raw, bool)
                and raw == raw and abs(raw) != float("inf")
                else None
            )
            rows.append(
                {
                    "timestamp": str(tag_ts.get(name, ts)),
                    "tag_name": name,
                    "value": numeric,
                    "raw_value": None if raw is None else str(raw),
                    "unit": tag.unit,
                    "quality": quality.value,
                    "source": tag.source,
                }
            )
            # Only real numbers take part in flat-line detection.
            if numeric is not None:
                self._history[name].append(numeric)
        self.repo.insert_readings(rows)
        return rows


def summarize(counts: Mapping[str, int]) -> Dict[str, Any]:
    total = sum(counts.values())
    full = {q.value: int(counts.get(q.value, 0)) for q in Quality}
    percent = {k: (round(100 * v / total, 1) if total else 0.0) for k, v in full.items()}
    return {"total": total, "counts": full, "percent": percent}
