"""Run the simulator from the command line and store validated readings.

Examples:
    python -m app.run_simulator --count 10
    python -m app.run_simulator --scenario flatline --count 8 --interval 0
"""
from __future__ import annotations

import argparse
import time

from app.database.sqlite_repo import SQLiteRepository
from app.models.tags import DEFAULT_CONFIG, load_tags
from app.pipeline import Pipeline
from app.simulator.plant import SCENARIOS, PlantSimulator


def main() -> None:
    p = argparse.ArgumentParser(description="Simulated plant telemetry (no live connections)")
    p.add_argument("--db", default="plant_data.db")
    p.add_argument("--tags", default=str(DEFAULT_CONFIG))
    p.add_argument("--scenario", default="normal", choices=SCENARIOS)
    p.add_argument("--only", nargs="*", help="limit the scenario to these tags")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()

    tags = load_tags(args.tags)
    repo = SQLiteRepository(args.db)
    repo.init()
    pipeline = Pipeline(tags, repo)
    sim = PlantSimulator(tags, seed=args.seed)
    sim.set_scenario(args.scenario, args.only)

    for i in range(args.count):
        rows = pipeline.process(sim.next_record())
        summary = ", ".join(f"{r['tag_name']}={r['value']}:{r['quality']}" for r in rows)
        print(f"[{i + 1}/{args.count}] {summary}")
        if args.interval > 0 and i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
