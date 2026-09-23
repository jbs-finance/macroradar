from datetime import date

from industry import INDUSTRY_SERIES, KNOWN_GAPS, build, missing_series
from regional import REGIONS


def periods(*pairs):
    return [{"date": f"31.12.{y}", "value": v} for y, v in pairs]


def dump_for(spec):
    return [
        {
            "terms": [int(t), *spec["extra_terms"]],
            "periods": periods(("2024", "110.4"), ("2025", "103.5")),
        }
        for t, _n, _s in REGIONS
    ]


def test_known_gap_is_a_real_series_and_only_it_is_tolerated():
    ids = {
        f"kz.industry.{s['series_key']}.{slug}"
        for s in INDUSTRY_SERIES
        for _, _, slug in REGIONS
    }
    assert KNOWN_GAPS <= ids
    data = {"series": [{"series_id": i} for i in ids - KNOWN_GAPS]}
    assert missing_series(data) == []
    other = sorted(ids - KNOWN_GAPS)[0]
    assert missing_series(
        {"series": [{"series_id": i} for i in ids - KNOWN_GAPS - {other}]}
    ) == [other]


def test_metallurgy_keeps_decimals_from_dump(tmp_path):
    by_url = {str(s["index_id"]): dump_for(s) for s in INDUSTRY_SERIES}

    def fetcher(url, **kwargs):
        return by_url[url.split("/")[-1].split("?")[0]]

    data = build(tmp_path / "i.json", date(2026, 9, 23), fetcher)
    metallurgy = next(
        s for s in data["series"] if s["series_id"] == "kz.industry.metallurgy.aktobe"
    )
    assert metallurgy["obs"][-1] == {"date": "2025", "value": 103.5}
    assert data["issues"] == []


def test_metallurgy_dump_gets_a_raised_body_limit():
    assert INDUSTRY_SERIES[0]["max_body"] > 26 * 1024 * 1024
