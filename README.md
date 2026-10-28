# Industrial Process Intelligence: Data Validation & Simulation Module

A **simulated, read-only** industrial data pipeline with data-quality validation:

```
Simulated Plant Telemetry -> Validation Engine -> SQLite -> FastAPI -> Dashboard
```

> **Engineering boundary:** this project never connects to a live PLC, DCS, SIS or
> production control system, and has no control or set-point write-back. All data is simulated.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

**Service + dashboard** (the simulator starts automatically and writes a reading every 2 s):

```bash
uvicorn app.api.main:create_app --factory --reload
```

- Dashboard: http://127.0.0.1:8000/
- API docs: http://127.0.0.1:8000/docs

Use the scenario buttons on the dashboard (or `POST /simulate/scenario`) to inject bad data.

**Simulator only (command line):**

```bash
python -m app.run_simulator --count 10                        # normal data
python -m app.run_simulator --scenario missing --count 3 --interval 0
python -m app.run_simulator --scenario flatline --count 6 --interval 0
python -m app.run_simulator --scenario out_of_range --only ph --count 3 --interval 0
```

Scenarios: `normal`, `missing`, `stale`, `flatline`, `out_of_range`, `invalid`.

**Tests:**

```bash
pytest
```

Environment variables: `DB_PATH` (default `plant_data.db`), `TAGS_PATH` (default `config/tags.yaml`),
`SIMULATOR_AUTOSTART` (`1`/`0`, default `1`).

## Architecture

```
app/
  models/tags.py        Tag dictionary dataclass + YAML loader (with config validation)
  simulator/plant.py    PlantSimulator: realistic values + on-demand bad-data scenarios
  validation/engine.py  Pure validation functions (no DB / API / UI imports)
  database/base.py      Repository interface (storage-agnostic)
  database/sqlite_repo.py  SQLite implementation
  pipeline.py           simulator record -> validate -> store (reusable by other apps)
  api/main.py           FastAPI app factory
  run_simulator.py      CLI runner
config/tags.yaml        Tag dictionary
dashboard/index.html    Static dashboard; talks to the API only
tests/                  pytest suite
```

Key design decisions:

- **Separation of concerns.** The validation engine is pure functions. The pipeline depends on the
  `Repository` interface, so SQLite can be swapped for TimescaleDB by adding another implementation.
  The dashboard only calls the HTTP API.
- **Configuration-driven.** Ranges, freshness limits, units and flat-line thresholds live in
  `config/tags.yaml`; nothing is hard-coded in the validators.
- **Every tag always gets a quality state.** A tag absent from a record is `MISSING`.
- **Raw values are preserved** (`raw_value` column) so a non-numeric input such as `"ERR"` is stored
  and labelled `INVALID` rather than lost.

## Quality rules

Checks run in this order and the first match wins:

| Order | Condition | Result |
|---|---|---|
| 1 | `None` or blank string | `MISSING` |
| 2 | Not a finite number (string, list, bool, NaN, inf) or unparseable timestamp | `INVALID` |
| 3 | Timestamp older than `max_age_seconds` | `STALE` |
| 4 | Outside `[min, max]` (inclusive) | `OUT_OF_RANGE` |
| 5 | Same value for `flatline_samples` consecutive readings (including the current one) | `FLATLINE` |
| 6 | Otherwise | `GOOD` |

## Database

Table `readings`: `id, timestamp, tag_name, value, raw_value, unit, quality, source`
(indexed by tag and id / timestamp). `timestamp` is stored as a UTC ISO 8601 string.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Service is running |
| `GET /tags` | Configured tags |
| `GET /latest` | Latest value and quality per tag |
| `GET /data/{tag}?limit=&start=&end=` | History for a tag, newest first (limit 1-1000, default 100) |
| `GET /quality-summary?window=` | Quality percentages over the last N readings (dashboard) |
| `POST /simulate/scenario` | Set the simulator scenario, body `{"scenario": "missing", "tags": ["ph"]}` |
| `POST /simulate/step?scenario=` | Generate one record immediately (used in tests/demos) |

Errors: unknown tag -> 404, invalid query parameters / body -> 422, malformed
timestamps or unknown scenario -> 400. The simulate endpoints only affect simulated data.

Example `/latest` response:

```json
{"timestamp": "2026-10-28T10:30:02.000+00:00",
 "data": {"ph": {"value": 1.62, "quality": "GOOD", "unit": "pH"}}}
```

## Assumptions and limitations

- A tag flagged `FLATLINE` needs `flatline_samples` identical values, so detection appears on the
  Nth sample, not the first repeat. Flat-line history is rebuilt from the database on restart.
- Stale data is simulated with a per-tag `tag_timestamps` entry in the record; a real source would
  supply a per-tag source timestamp in the same way.
- `/latest` returns the most recently *stored* reading per tag; its top-level `timestamp` is the
  newest sample time among them.
- Timestamps without a timezone are treated as UTC.
- SQLite opens a short-lived connection per call; adequate for this scope, not for high throughput.
- No authentication, since the service only exposes simulated data. Add it before any real deployment.

## Demo checklist

1. Start the service and open the dashboard (values and `GOOD` states update).
2. Click `missing`, `stale`, `out of range`, `flatline` (the flat-line flag appears after ~5 samples),
   `invalid`; each shows its quality state and the summary percentages shift.
3. Click `normal` to recover.
4. `curl http://127.0.0.1:8000/latest` and `/data/ph?limit=5` to see the stored states.
5. `pytest` to run the suite.
