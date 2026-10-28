"""SQLite implementation of the Repository interface."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any, Dict, List, Optional, Sequence

from app.database.base import Repository

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    tag_name  TEXT    NOT NULL,
    value     REAL,
    raw_value TEXT,
    unit      TEXT,
    quality   TEXT    NOT NULL,
    source    TEXT
);
CREATE INDEX IF NOT EXISTS idx_readings_tag_id ON readings (tag_name, id);
CREATE INDEX IF NOT EXISTS idx_readings_tag_ts ON readings (tag_name, timestamp);
"""


class SQLiteRepository(Repository):
    def __init__(self, path: str = "plant_data.db"):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def insert_readings(self, rows: Sequence[Dict[str, Any]]) -> None:
        if not rows:
            return
        with closing(self._connect()) as conn:
            conn.executemany(
                "INSERT INTO readings (timestamp, tag_name, value, raw_value, unit, quality, source) "
                "VALUES (:timestamp, :tag_name, :value, :raw_value, :unit, :quality, :source)",
                rows,
            )
            conn.commit()

    def latest(self) -> List[Dict[str, Any]]:
        sql = (
            "SELECT r.* FROM readings r JOIN "
            "(SELECT tag_name, MAX(id) AS mid FROM readings GROUP BY tag_name) m "
            "ON r.id = m.mid ORDER BY r.tag_name"
        )
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(sql)]

    def history(
        self,
        tag_name: str,
        limit: int = 100,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM readings WHERE tag_name = ?"
        params: List[Any] = [tag_name]
        if start:
            sql += " AND timestamp >= ?"
            params.append(start)
        if end:
            sql += " AND timestamp <= ?"
            params.append(end)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def recent_values(self, tag_name: str, n: int) -> List[Any]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT value FROM readings WHERE tag_name = ? ORDER BY id DESC LIMIT ?",
                (tag_name, n),
            ).fetchall()
        return [r["value"] for r in reversed(rows)]

    def quality_counts(self, window: int) -> Dict[str, int]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT quality, COUNT(*) AS c FROM "
                "(SELECT quality FROM readings ORDER BY id DESC LIMIT ?) GROUP BY quality",
                (window,),
            ).fetchall()
        return {r["quality"]: r["c"] for r in rows}
