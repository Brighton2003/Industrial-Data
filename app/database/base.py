"""Storage interface. Validation and API depend on this, not on SQLite."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence


class Repository(ABC):
    """Replace with a TimescaleDB implementation later without touching callers."""

    @abstractmethod
    def init(self) -> None: ...

    @abstractmethod
    def insert_readings(self, rows: Sequence[Dict[str, Any]]) -> None:
        """rows: dicts with timestamp, tag_name, value, raw_value, unit, quality, source."""

    @abstractmethod
    def latest(self) -> List[Dict[str, Any]]:
        """Most recently stored reading per tag."""

    @abstractmethod
    def history(
        self,
        tag_name: str,
        limit: int = 100,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Newest first."""

    @abstractmethod
    def recent_values(self, tag_name: str, n: int) -> List[Any]:
        """Last n stored raw values for a tag, oldest first."""

    @abstractmethod
    def quality_counts(self, window: int) -> Dict[str, int]:
        """Quality counts over the most recent `window` readings (all tags)."""
