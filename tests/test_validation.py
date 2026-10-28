from datetime import timedelta

import pytest

from app.models.tags import TagConfigError, load_tags
from app.validation import (
    Quality,
    check_flatline,
    check_freshness,
    check_missing,
    check_range,
    validate_record,
    validate_value,
)


def test_valid_value_is_good(ore_tag, now):
    assert validate_value(31.25, now.isoformat(), ore_tag, now=now) == Quality.GOOD


def test_integer_value_is_good(ore_tag, now):
    assert validate_value(30, now, ore_tag, now=now) == Quality.GOOD


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_missing_value_detected(ore_tag, now, bad):
    assert check_missing(bad)
    assert validate_value(bad, now, ore_tag, now=now) == Quality.MISSING


def test_stale_timestamp_detected(ore_tag, now):
    old = now - timedelta(seconds=ore_tag.max_age_seconds + 1)
    assert check_freshness(old, ore_tag, now) is False
    assert validate_value(31.0, old, ore_tag, now=now) == Quality.STALE


def test_age_exactly_at_limit_is_fresh(ore_tag, now):
    edge = now - timedelta(seconds=ore_tag.max_age_seconds)
    assert validate_value(31.0, edge, ore_tag, now=now) == Quality.GOOD


@pytest.mark.parametrize("value", [-0.1, 100.1, 1e6])
def test_out_of_range_detected(ore_tag, now, value):
    assert not check_range(value, ore_tag)
    assert validate_value(value, now, ore_tag, now=now) == Quality.OUT_OF_RANGE


@pytest.mark.parametrize("value", [0, 100])
def test_range_bounds_inclusive(ore_tag, now, value):
    assert validate_value(value, now, ore_tag, now=now) == Quality.GOOD


def test_flatline_detected(ore_tag, now):
    history = [31.25] * (ore_tag.flatline_samples - 1)
    assert check_flatline(31.25, history, ore_tag)
    assert validate_value(31.25, now, ore_tag, history, now) == Quality.FLATLINE


def test_not_flatline_when_run_too_short_or_broken(ore_tag, now):
    short = [31.25] * (ore_tag.flatline_samples - 2)
    assert validate_value(31.25, now, ore_tag, short, now) == Quality.GOOD
    broken = [31.25, 31.25, 30.0, 31.25, 31.25]
    assert validate_value(31.25, now, ore_tag, broken, now) == Quality.GOOD


@pytest.mark.parametrize("bad", ["abc", [1, 2], {"v": 1}, True, float("nan"), float("inf")])
def test_invalid_data_type_detected(ore_tag, now, bad):
    assert validate_value(bad, now, ore_tag, now=now) == Quality.INVALID


def test_unparseable_timestamp_is_invalid(ore_tag, now):
    assert validate_value(31.0, "not-a-date", ore_tag, now=now) == Quality.INVALID
    assert validate_value(31.0, None, ore_tag, now=now) == Quality.INVALID


def test_validate_record_covers_every_tag_and_flags_absent_as_missing(tags, now):
    record = {"timestamp": now.isoformat(), "ore_feed_tph": 31.25, "unknown_key": 1}
    result = validate_record(record, tags, now=now)
    assert set(result) == set(tags)
    assert result["ore_feed_tph"] == Quality.GOOD
    assert result["ph"] == Quality.MISSING


def test_validate_record_per_tag_timestamp(tags, now):
    old = (now - timedelta(seconds=999)).isoformat()
    record = {"timestamp": now.isoformat(), "ph": 1.6, "tag_timestamps": {"ph": old}}
    assert validate_record(record, tags, now=now)["ph"] == Quality.STALE


def test_tag_configuration_loaded(tags):
    assert {"ore_feed_tph", "cu_grade_pct", "ph", "temperature_c",
            "flow_m3h", "current_a", "voltage_v"} <= set(tags)
    t = tags["ore_feed_tph"]
    assert (t.unit, t.min, t.max, t.max_age_seconds) == ("t/h", 0, 100, 10)
    assert t.source == "SIM_PLANT"


def test_bad_tag_config_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("tags:\n  x:\n    description: d\n    unit: u\n    min: 5\n    max: 1\n    max_age_seconds: 1\n")
    with pytest.raises(TagConfigError):
        load_tags(p)
    p.write_text("tags:\n  x:\n    description: d\n")
    with pytest.raises(TagConfigError):
        load_tags(p)
    with pytest.raises(TagConfigError):
        load_tags(tmp_path / "missing.yaml")
