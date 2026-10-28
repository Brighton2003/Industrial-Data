"""Simulated plant telemetry with deliberate bad-data injection.

SIMULATION ONLY: this module never talks to a PLC/DCS/SIS.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from app.models.tags import TagConfig

SCENARIOS = ("normal", "missing", "stale", "flatline", "out_of_range", "invalid")


class PlantSimulator:
    def __init__(self, tags: Dict[str, TagConfig], seed: Optional[int] = None):
        self.tags = tags
        self._rng = random.Random(seed)
        self._scenario = "normal"
        self._scenario_tags: Optional[set] = None  # None => all tags
        self._frozen: Dict[str, float] = {}
        self._last: Dict[str, float] = {}

    # ---- scenario control -------------------------------------------------
    @property
    def scenario(self) -> str:
        return self._scenario

    def set_scenario(self, scenario: str, tags: Optional[Iterable[str]] = None) -> None:
        """Persistently apply a scenario to `tags` (all tags if None) until changed."""
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}'. Choose from {SCENARIOS}")
        selected = set(tags) if tags is not None else None
        if selected is not None:
            unknown = selected - set(self.tags)
            if unknown:
                raise ValueError(f"Unknown tags: {sorted(unknown)}")
        self._scenario = scenario
        self._scenario_tags = selected
        self._frozen = {}  # restart flat-line capture

    def reset(self) -> None:
        self.set_scenario("normal")

    # ---- generation -------------------------------------------------------
    def _normal_value(self, tag: TagConfig) -> float:
        nominal = tag.nominal if tag.nominal is not None else (tag.min + tag.max) / 2
        value = self._rng.gauss(nominal, tag.noise)
        value = min(max(value, tag.min), tag.max)
        return round(value, 3)

    def _out_of_range_value(self, tag: TagConfig) -> float:
        span = tag.max - tag.min
        return round(tag.max + 0.2 * span + 1, 3)

    def next_record(
        self,
        scenario: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Produce one record. A `scenario` argument overrides the persistent mode
        for this call only."""
        if scenario is None:
            scenario, affected = self._scenario, self._scenario_tags
        else:
            if scenario not in SCENARIOS:
                raise ValueError(f"Unknown scenario '{scenario}'. Choose from {SCENARIOS}")
            affected = set(tags) if tags is not None else None
        now = now or datetime.now(timezone.utc)
        record: Dict[str, Any] = {"timestamp": now.isoformat(timespec="milliseconds")}
        tag_timestamps: Dict[str, str] = {}

        for name, tag in self.tags.items():
            hit = scenario != "normal" and (affected is None or name in affected)
            value: Any = self._normal_value(tag)
            if hit:
                if scenario == "missing":
                    value = None
                elif scenario == "out_of_range":
                    value = self._out_of_range_value(tag)
                elif scenario == "invalid":
                    value = "ERR"
                elif scenario == "flatline":
                    value = self._frozen.setdefault(name, value)
                elif scenario == "stale":
                    old = now - timedelta(seconds=tag.max_age_seconds * 3 + 1)
                    tag_timestamps[name] = old.isoformat(timespec="milliseconds")
            record[name] = value
        if tag_timestamps:
            record["tag_timestamps"] = tag_timestamps
        return record
