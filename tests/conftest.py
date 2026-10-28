from datetime import datetime, timezone

import pytest

from app.database.sqlite_repo import SQLiteRepository
from app.models.tags import load_tags
from app.pipeline import Pipeline
from app.simulator.plant import PlantSimulator


@pytest.fixture
def tags():
    return load_tags()


@pytest.fixture
def ore_tag(tags):
    return tags["ore_feed_tph"]


@pytest.fixture
def now():
    return datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_path):
    r = SQLiteRepository(str(tmp_path / "test.db"))
    r.init()
    return r


@pytest.fixture
def pipeline(tags, repo):
    return Pipeline(tags, repo)


@pytest.fixture
def sim(tags):
    return PlantSimulator(tags, seed=42)
