import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "api.db"), autostart=False, seed=1)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_tags_structure(client):
    body = client.get("/tags").json()
    assert "ore_feed_tph" in body
    assert {"description", "unit", "min", "max", "max_age_seconds"} <= set(body["ore_feed_tph"])


def test_latest_empty_before_any_data(client):
    assert client.get("/latest").json() == {"timestamp": None, "data": {}}


def test_latest_structure(client):
    client.post("/simulate/step")
    body = client.get("/latest").json()
    assert body["timestamp"]
    assert set(body["data"]) == set(client.get("/tags").json())
    for item in body["data"].values():
        assert {"value", "quality"} <= set(item)
    assert body["data"]["ph"]["quality"] == "GOOD"


@pytest.mark.parametrize(
    "scenario,expected",
    [("missing", "MISSING"), ("stale", "STALE"), ("out_of_range", "OUT_OF_RANGE"), ("invalid", "INVALID")],
)
def test_bad_data_exposed_through_api(client, scenario, expected):
    client.post("/simulate/step", params={"scenario": scenario})
    data = client.get("/latest").json()["data"]
    assert {v["quality"] for v in data.values()} == {expected}


def test_flatline_exposed_through_api(client):
    client.post("/simulate/scenario", json={"scenario": "flatline"})
    for _ in range(5):
        client.post("/simulate/step")
    data = client.get("/latest").json()["data"]
    assert {v["quality"] for v in data.values()} == {"FLATLINE"}


def test_history_endpoint(client):
    for _ in range(3):
        client.post("/simulate/step")
    body = client.get("/data/ph", params={"limit": 2}).json()
    assert body["tag"] == "ph" and body["count"] == 2
    assert {"timestamp", "value", "quality"} <= set(body["data"][0])


def test_history_time_filter(client):
    client.post("/simulate/step")
    assert client.get("/data/ph", params={"start": "2999-01-01T00:00:00Z"}).json()["count"] == 0
    assert client.get("/data/ph", params={"start": "2000-01-01T00:00:00Z"}).json()["count"] == 1


def test_quality_summary(client):
    for _ in range(3):
        client.post("/simulate/step")
    client.post("/simulate/step", params={"scenario": "missing"})
    body = client.get("/quality-summary").json()
    assert body["total"] == 28
    assert body["counts"]["MISSING"] == 7
    assert body["percent"]["MISSING"] == 25.0
    assert set(body["counts"]) == {"GOOD", "MISSING", "STALE", "OUT_OF_RANGE", "FLATLINE", "INVALID"}


# --- malformed requests: must return 4xx, never crash -----------------------
def test_unknown_tag_404(client):
    assert client.get("/data/not_a_tag").status_code == 404


@pytest.mark.parametrize("params", [{"limit": "abc"}, {"limit": 0}, {"limit": 100000}, {"limit": -5}])
def test_bad_limit_422(client, params):
    assert client.get("/data/ph", params=params).status_code == 422


@pytest.mark.parametrize("params", [{"start": "garbage"}, {"end": "2026-13-45"}])
def test_bad_timestamps_400(client, params):
    assert client.get("/data/ph", params=params).status_code == 400


def test_bad_scenario_requests(client):
    assert client.post("/simulate/scenario", json={"scenario": "explode"}).status_code == 400
    assert client.post("/simulate/scenario", json={"scenario": "missing", "tags": ["x"]}).status_code == 400
    assert client.post("/simulate/scenario", json={}).status_code == 422
    assert client.post("/simulate/scenario", content="{not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/simulate/step", params={"scenario": "explode"}).status_code == 400


def test_unknown_route_and_method(client):
    assert client.get("/nope").status_code == 404
    assert client.post("/health").status_code == 405


def test_service_still_healthy_after_bad_requests(client):
    client.get("/data/x")
    client.get("/data/ph", params={"limit": "abc"})
    assert client.get("/health").status_code == 200


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "INDUSTRIAL DATA MONITOR" in r.text
