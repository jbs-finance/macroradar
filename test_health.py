import json
from datetime import date
from pathlib import Path

import pytest

from etl import Obs, Series, SourceError, validate
from health import HEALTH_SERIES, build, missing_series, parse_periods, region_rows
from industry import REGIONS

TODAY = date(2026, 9, 23)


def periods(*pairs):
    return [{"name": f"{y} год", "date": f"31.12.{y}", "value": v} for y, v in pairs]


def dump(value="40.57"):
    rows = [
        {
            "terms": [741880],
            "termNames": ["РЕСПУБЛИКА КАЗАХСТАН"],
            "periods": periods(("2023", value)),
        }
    ]
    rows += [
        {
            "terms": [int(term)],
            "termNames": [name],
            "periods": periods(("2022", "30.1"), ("2023", value)),
        }
        for term, name, _slug in REGIONS
    ]
    # Разрез глубже региона должен игнорироваться.
    rows.append(
        {
            "terms": [258742, 741917],
            "termNames": ["X", "Y"],
            "periods": periods(("2023", "999")),
        }
    )
    return rows


def test_parse_keeps_decimals_skips_gaps_and_sorts():
    obs = parse_periods(
        periods(("2023", "40.57"), ("2021", "x"), ("2022", "40,1")), 704316
    )
    assert [(o.date, o.value) for o in obs] == [("2022", 40.1), ("2023", 40.57)]


def test_parse_rejects_non_annual_date():
    with pytest.raises(SourceError):
        parse_periods([{"date": "31.03.2023", "value": "1"}], 704316)


def test_region_rows_keeps_only_single_term_rows():
    rows = region_rows(dump(), 704316)
    assert rows["258742"][-1]["value"] == "40.57"
    assert len(rows) == len(REGIONS) + 1


def test_build_covers_all_regions_with_known_lag(tmp_path: Path):
    data = build(tmp_path / "health.json", today=TODAY, fetcher=lambda *a, **k: dump())
    assert data["issues"] == []
    assert missing_series(data) == []
    assert len(data["series"]) == len(HEALTH_SERIES) * len(REGIONS)


def test_series_older_than_own_limit_is_rejected(tmp_path: Path):
    data = build(
        tmp_path / "health.json", today=date(2027, 6, 1), fetcher=lambda *a, **k: dump()
    )
    assert data["series"] == []
    assert all("старше 1200 дней" in issue for issue in data["issues"])


def test_source_failure_falls_back_per_region(tmp_path: Path):
    spec = HEALTH_SERIES[0]
    series_id = f"kz.health.{spec['series_key']}.{REGIONS[0][2]}"
    old = {
        "series_id": series_id,
        "obs": [{"date": "2023", "value": 61.17}],
        "stale": False,
        "note": "",
    }
    dataset = tmp_path / "health.json"
    dataset.write_text(json.dumps({"series": [old]}), encoding="utf-8")

    def fail(*args, **kwargs):
        raise SourceError("источник недоступен")

    data = build(dataset, today=TODAY, fetcher=fail)
    assert [s["series_id"] for s in data["series"]] == [series_id]
    assert data["series"][0]["stale"] is True
    assert missing_series(data)


def test_validate_honors_explicit_max_age():
    series = Series("s", "s", "u", "A", "src", "url", "t", obs=[Obs("2023", 1.0)])
    bounds = {"min": 0, "max": 10}
    assert any("старше" in p for p in validate(series, bounds, TODAY))
    assert validate(series, {**bounds, "max_age_days": 1200}, TODAY) == []
