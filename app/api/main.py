"""FastAPI service. Read-only with respect to plant systems: it only exposes
simulated, stored data and never writes to any control system."""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database.sqlite_repo import SQLiteRepository
from app.models.tags import DEFAULT_CONFIG, load_tags
from app.pipeline import Pipeline, summarize
from app.simulator.plant import SCENARIOS, PlantSimulator

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"


class ScenarioRequest(BaseModel):
    scenario: str
    tags: Optional[List[str]] = None


def _parse_iso(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"'{field}' must be an ISO 8601 timestamp")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Stored timestamps are UTC isoformat strings.
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def create_app(
    db_path: Optional[str] = None,
    tags_path: Optional[str] = None,
    autostart: Optional[bool] = None,
    interval_seconds: float = 2.0,
    seed: Optional[int] = None,
) -> FastAPI:
    db_path = db_path or os.getenv("DB_PATH", "plant_data.db")
    tags_path = tags_path or os.getenv("TAGS_PATH", str(DEFAULT_CONFIG))
    if autostart is None:
        autostart = os.getenv("SIMULATOR_AUTOSTART", "1") == "1"

    tags = load_tags(tags_path)
    repo = SQLiteRepository(db_path)
    repo.init()
    pipeline = Pipeline(tags, repo)
    simulator = PlantSimulator(tags, seed=seed)
    lock = threading.Lock()
    stop = threading.Event()

    def step(scenario: Optional[str] = None, only: Optional[list] = None) -> None:
        with lock:
            pipeline.process(simulator.next_record(scenario, only))

    def loop() -> None:
        while not stop.is_set():
            try:
                step()
            except Exception:  # keep the simulator alive on any single failure
                pass
            stop.wait(interval_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        thread = None
        if autostart:
            thread = threading.Thread(target=loop, daemon=True)
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=2)

    app = FastAPI(title="Industrial Data Monitor (simulated)", lifespan=lifespan)
    app.state.repo = repo
    app.state.pipeline = pipeline
    app.state.simulator = simulator
    app.state.step = step

    @app.get("/health")
    def health():
        return {"status": "ok", "tags": len(tags), "simulator_scenario": simulator.scenario}

    @app.get("/tags")
    def get_tags():
        return {
            name: {
                "description": t.description,
                "unit": t.unit,
                "min": t.min,
                "max": t.max,
                "max_age_seconds": t.max_age_seconds,
                "flatline_samples": t.flatline_samples,
                "sample_rate_seconds": t.sample_rate_seconds,
                "source": t.source,
            }
            for name, t in tags.items()
        }

    @app.get("/latest")
    def latest():
        rows = repo.latest()
        if not rows:
            return {"timestamp": None, "data": {}}
        data = {
            r["tag_name"]: {
                "value": r["value"] if r["value"] is not None else r["raw_value"],
                "quality": r["quality"],
                "unit": r["unit"],
            }
            for r in rows
        }
        # Newest sample time (a stale tag carries an old timestamp of its own).
        return {"timestamp": max(r["timestamp"] for r in rows), "data": data}

    @app.get("/data/{tag}")
    def data(
        tag: str,
        limit: int = Query(100, ge=1, le=1000),
        start: Optional[str] = None,
        end: Optional[str] = None,
    ):
        if tag not in tags:
            raise HTTPException(status_code=404, detail=f"Unknown tag '{tag}'")
        rows = repo.history(tag, limit, _parse_iso(start, "start"), _parse_iso(end, "end"))
        return {
            "tag": tag,
            "unit": tags[tag].unit,
            "count": len(rows),
            "data": [
                {
                    "timestamp": r["timestamp"],
                    "value": r["value"] if r["value"] is not None else r["raw_value"],
                    "quality": r["quality"],
                }
                for r in rows
            ],
        }

    @app.get("/quality-summary")
    def quality_summary(window: int = Query(500, ge=1, le=100000)):
        result = summarize(repo.quality_counts(window))
        result["window"] = window
        return result

    @app.post("/simulate/scenario")
    def set_scenario(req: ScenarioRequest):
        with lock:
            try:
                simulator.set_scenario(req.scenario, req.tags)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        return {"scenario": simulator.scenario, "available": list(SCENARIOS)}

    @app.post("/simulate/step")
    def simulate_step(scenario: Optional[str] = None):
        if scenario is not None and scenario not in SCENARIOS:
            raise HTTPException(status_code=400, detail=f"Unknown scenario '{scenario}'")
        step(scenario)
        return {"status": "stepped", "scenario": scenario or simulator.scenario}

    @app.get("/", include_in_schema=False)
    def dashboard():
        index = DASHBOARD_DIR / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return FileResponse(index)

    return app
