"""Each bad-data scenario must be detected, labelled correctly and stored."""
import pytest

from app.simulator.plant import SCENARIOS


def run(pipeline, sim, scenario, n=1, only=None):
    sim.set_scenario(scenario, only)
    rows = []
    for _ in range(n):
        rows = pipeline.process(sim.next_record())
    return {r["tag_name"]: r["quality"] for r in rows}


def test_normal_data_is_all_good(pipeline, sim):
    q = run(pipeline, sim, "normal", n=10)
    assert set(q.values()) == {"GOOD"}


def test_missing_scenario(pipeline, sim):
    assert set(run(pipeline, sim, "missing").values()) == {"MISSING"}


def test_stale_scenario(pipeline, sim):
    assert set(run(pipeline, sim, "stale").values()) == {"STALE"}


def test_out_of_range_scenario(pipeline, sim):
    assert set(run(pipeline, sim, "out_of_range").values()) == {"OUT_OF_RANGE"}


def test_invalid_scenario(pipeline, sim):
    assert set(run(pipeline, sim, "invalid").values()) == {"INVALID"}


def test_flatline_scenario(pipeline, sim, tags):
    n = max(t.flatline_samples for t in tags.values())
    q = run(pipeline, sim, "flatline", n=n)
    assert set(q.values()) == {"FLATLINE"}


def test_flatline_not_flagged_before_threshold(pipeline, sim):
    q = run(pipeline, sim, "flatline", n=2)
    assert set(q.values()) == {"GOOD"}


def test_scenario_limited_to_one_tag(pipeline, sim):
    q = run(pipeline, sim, "out_of_range", only=["ph"])
    assert q["ph"] == "OUT_OF_RANGE"
    assert all(v == "GOOD" for k, v in q.items() if k != "ph")


def test_recovery_after_bad_data(pipeline, sim):
    run(pipeline, sim, "missing")
    assert set(run(pipeline, sim, "normal").values()) == {"GOOD"}


def test_unknown_scenario_and_tag_rejected(sim):
    with pytest.raises(ValueError):
        sim.set_scenario("explode")
    with pytest.raises(ValueError):
        sim.set_scenario("missing", ["nope"])
    with pytest.raises(ValueError):
        sim.next_record("explode")


def test_readings_and_quality_are_stored(pipeline, sim, repo, tags):
    run(pipeline, sim, "normal")
    run(pipeline, sim, "missing")
    latest = {r["tag_name"]: r for r in repo.latest()}
    assert set(latest) == set(tags)
    assert latest["ph"]["quality"] == "MISSING"
    assert latest["ph"]["value"] is None
    hist = repo.history("ph", limit=10)
    assert [h["quality"] for h in hist] == ["MISSING", "GOOD"]  # newest first
    row = hist[0]
    for col in ("id", "timestamp", "tag_name", "value", "unit", "quality", "source"):
        assert col in row


def test_flatline_history_survives_pipeline_restart(tags, repo, sim):
    from app.pipeline import Pipeline

    n = max(t.flatline_samples for t in tags.values())
    sim.set_scenario("flatline")
    p1 = Pipeline(tags, repo)
    for _ in range(n - 1):
        p1.process(sim.next_record())
    p2 = Pipeline(tags, repo)  # fresh instance re-seeds from the database
    rows = p2.process(sim.next_record())
    assert {r["quality"] for r in rows} == {"FLATLINE"}


def test_all_scenarios_listed():
    assert set(SCENARIOS) == {"normal", "missing", "stale", "flatline", "out_of_range", "invalid"}
