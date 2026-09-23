import json
from datetime import date
from pathlib import Path

import pytest

from etl import Obs, Series, SourceError, validate
from regional import REGIONS, build, missing_series, parse_periods, pick_rows

TODAY = date(2026, 9, 23)
SPEC = {
    "series_key": "x",
    "index_id": 1,
    "dics": "68,776",
    "extra_terms": (741917,),
    "name_ru": "Ряд",
    "unit": "ед.",
    "min": 0,
    "max": 500,
}


def periods(*pairs):
    return [{"name": f"{y} год", "date": f"31.12.{y}", "value": v} for y, v in pairs]


def dump(value="40.57", extra=(741917,)):
    rows = [
        {
            "terms": [int(term), *extra],
            "periods": periods(("2024", "30.1"), ("2025", value)),
        }
        for term, _name, _slug in REGIONS
    ]
    # Компонент агрегата и район: должны отсекаться сравнением terms.
    rows.append({"terms": [258742, 533590], "periods": periods(("2025", "999"))})
    rows.append({"terms": [268027, *extra], "periods": periods(("2025", "999"))})
    return rows


def test_parse_keeps_decimals_skips_gaps_and_sorts():
    obs = parse_periods(
        periods(("2025", "40.57"), ("2023", "x"), ("2024", "40,1"), ("2022", "-")), 1
    )
    assert [(o.date, o.value) for o in obs] == [("2024", 40.1), ("2025", 40.57)]


@pytest.mark.parametrize(
    "bad",
    [[{"date": "31.03.2023", "value": "1"}], [{"date": "31.12.2023", "value": "н/д"}]],
)
def test_parse_rejects_non_annual_date_and_garbage(bad):
    with pytest.raises(SourceError):
        parse_periods(bad, 1)


def test_pick_rows_matches_exact_terms_and_flags_duplicates():
    payload = dump()
    payload.append({"terms": [258742, 741917], "periods": []})
    rows, ambiguous = pick_rows(payload, SPEC)
    assert rows["247783"][-1]["value"] == "40.57"
    assert (
        "268027" in rows
    )  # район с тем же хвостом попадёт в rows, но в REGIONS его нет
    assert ambiguous == {"258742"}


@pytest.mark.parametrize("bad", [[], {}, None])
def test_pick_rows_rejects_empty_payload(bad):
    with pytest.raises(SourceError):
        pick_rows(bad, SPEC)


def test_build_covers_all_regions_and_passes_max_body(tmp_path: Path):
    calls = []

    def fetcher(url, **kwargs):
        calls.append((url, kwargs["max_body"]))
        return dump()

    data = build(
        [{**SPEC, "max_body": 123}], "kz.t", "src", tmp_path / "d.json", TODAY, fetcher
    )
    assert data["issues"] == []
    assert missing_series(data, [SPEC], "kz.t") == []
    assert calls == [
        ("https://taldau.stat.gov.kz/ru/Api/GetIndexData/1?period=7&dics=68,776", 123)
    ]
    assert data["series"][0]["obs"][-1] == {"date": "2025", "value": 40.57}


def test_duplicate_region_is_dropped_not_guessed(tmp_path: Path):
    payload = dump() + [{"terms": [258742, 741917], "periods": periods(("2025", "1"))}]
    data = build(
        [SPEC], "kz.t", "src", tmp_path / "d.json", TODAY, lambda *a, **k: payload
    )
    assert missing_series(data, [SPEC], "kz.t") == ["kz.t.x.kostanay"]
    assert any("дважды" in issue for issue in data["issues"])


def test_source_failure_falls_back_per_region_and_known_gap_is_tolerated(
    tmp_path: Path,
):
    series_id = f"kz.t.x.{REGIONS[0][2]}"
    dataset = tmp_path / "d.json"
    old = {
        "series_id": series_id,
        "obs": [{"date": "2025", "value": 1.0}],
        "stale": False,
        "note": "",
    }
    dataset.write_text(json.dumps({"series": [old]}), encoding="utf-8")

    def fail(*args, **kwargs):
        raise SourceError("источник недоступен")

    data = build([SPEC], "kz.t", "src", dataset, TODAY, fail)
    assert [(s["series_id"], s["stale"]) for s in data["series"]] == [(series_id, True)]
    assert len(data["issues"]) == len(REGIONS)
    missing = missing_series(data, [SPEC], "kz.t")
    assert series_id not in missing and len(missing) == len(REGIONS) - 1
    assert missing_series(data, [SPEC], "kz.t", frozenset(missing)) == []


def test_validate_honors_explicit_max_age():
    series = Series("s", "s", "u", "A", "src", "url", "t", obs=[Obs("2023", 1.0)])
    bounds = {"min": 0, "max": 10}
    assert any("старше" in p for p in validate(series, bounds, TODAY))
    assert validate(series, {**bounds, "max_age_days": 1200}, TODAY) == []
