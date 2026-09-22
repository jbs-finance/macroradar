import json
from pathlib import Path

import pytest

from etl import SourceError
from industry import (
    INDUSTRY_SERIES,
    KNOWN_GAPS,
    REGIONS,
    build,
    missing_series,
    parse_dynamics,
)


def payload(dates=None, values=None):
    return {
        "dateList": dates or ["122023", "122024", "122025"],
        "valueList": values or ["98", "102", "104"],
    }


def test_parses_dates_and_sorts():
    obs = parse_dynamics(payload(), 701625)
    assert [(item.date, item.value) for item in obs] == [
        ("2023", 98.0),
        ("2024", 102.0),
        ("2025", 104.0),
    ]


def test_skips_suppressed_x_and_dash_and_empty_without_raising():
    obs = parse_dynamics(
        payload(
            dates=["122021", "122022", "122023", "122025"], values=["x", "-", "", "104"]
        ),
        20385164,
    )
    assert [(item.date, item.value) for item in obs] == [("2025", 104.0)]


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"dateList": [], "valueList": []},
        {"dateList": ["122025"], "valueList": ["104", "105"]},
        [],
    ],
)
def test_malformed_payload_is_rejected(bad):
    with pytest.raises(SourceError):
        parse_dynamics(bad, 701625)


def test_non_numeric_value_other_than_known_gaps_is_rejected():
    with pytest.raises(SourceError):
        parse_dynamics(payload(values=["н/д"]), 701625)


def test_build_covers_every_region_for_every_series(tmp_path: Path):
    dataset = tmp_path / "industry.json"

    def fake_fetcher(index_id, dic_ids, terms, raw_name):
        return payload()

    data = build(dataset, fetcher=fake_fetcher)
    got_ids = {item["series_id"] for item in data["series"]}
    expected_ids = {
        f"kz.industry.{spec['series_key']}.{slug}"
        for spec in INDUSTRY_SERIES
        for _, _, slug in REGIONS
    }
    assert got_ids == expected_ids
    assert data["issues"] == []


def test_missing_series_ignores_known_gap_but_flags_new_loss():
    all_ids = {
        f"kz.industry.{spec['series_key']}.{slug}"
        for spec in INDUSTRY_SERIES
        for _, _, slug in REGIONS
    }
    assert KNOWN_GAPS <= all_ids, "KNOWN_GAPS ссылается на несуществующий ряд"

    complete = {"series": [{"series_id": series_id} for series_id in all_ids]}
    assert missing_series(complete) == []

    without_known_gap = {
        "series": [{"series_id": s} for s in all_ids if s not in KNOWN_GAPS]
    }
    assert missing_series(without_known_gap) == []

    other_id = next(iter(all_ids - KNOWN_GAPS))
    without_other = {"series": [{"series_id": s} for s in all_ids if s != other_id]}
    assert missing_series(without_other) == [other_id]


def test_stale_fallback_on_source_error_keeps_previous_region(tmp_path: Path):
    spec = INDUSTRY_SERIES[0]
    _term, _name, slug = REGIONS[0]
    series_id = f"kz.industry.{spec['series_key']}.{slug}"
    old = {
        "series_id": series_id,
        "name_ru": f"{spec['name_ru']}: {slug}",
        "unit": spec["unit"],
        "freq": "A",
        "source": "Бюро национальной статистики",
        "source_url": "https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/701625",
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "obs": [{"date": "2025", "value": 104.0}],
        "stale": False,
        "note": "область, разрез Talдау",
    }
    dataset = tmp_path / "industry.json"
    dataset.write_text(json.dumps({"series": [old]}), encoding="utf-8")

    def fail(*args, **kwargs):
        raise SourceError("источник недоступен")

    data = build(dataset, fetcher=fail)
    fallback = next(item for item in data["series"] if item["series_id"] == series_id)
    assert fallback["stale"] is True
    assert fallback["note"] == "источник недоступен"
    assert any(series_id in issue for issue in data["issues"])
