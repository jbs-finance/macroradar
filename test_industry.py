from datetime import date

from industry import INDUSTRY_SERIES, KNOWN_GAPS, build, missing_series
from regional import REGIONS, places_of


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
        for _, _, slug in places_of(s)
    }
    assert KNOWN_GAPS <= ids
    data = {"series": [{"series_id": i} for i in ids - KNOWN_GAPS]}
    assert missing_series(data) == []
    other = sorted(ids - KNOWN_GAPS)[0]
    assert missing_series(
        {"series": [{"series_id": i} for i in ids - KNOWN_GAPS - {other}]}
    ) == [other]


def test_metallurgy_keeps_decimals_from_dump(tmp_path):
    by_index: dict[str, list] = {}
    for s in INDUSTRY_SERIES:
        by_index.setdefault(str(s["index_id"]), []).extend(dump_for(s))

    calls = []

    def fetcher(url, **kwargs):
        calls.append(url)
        return by_index[url.split("/")[-1].split("?")[0]]

    data = build(tmp_path / "i.json", date(2026, 9, 23), fetcher)
    # Пять рядов ГМК читают один дамп 26 МБ: он качается один раз.
    assert len(calls) == len(set(calls)) == 2
    metallurgy = next(
        s for s in data["series"] if s["series_id"] == "kz.industry.metallurgy.aktobe"
    )
    assert metallurgy["obs"][-1] == {"date": "2025", "value": 103.5}
    assert data["issues"] == []


def test_metallurgy_dump_gets_a_raised_body_limit():
    for spec in INDUSTRY_SERIES:
        if spec["index_id"] == 701625:
            assert spec["max_body"] > 26 * 1024 * 1024


def test_gmk_series_cover_only_publishing_regions():
    by_key = {s["series_key"]: s for s in INDUSTRY_SERIES}
    assert len(places_of(by_key["metallurgy_all"])) == 20
    assert "almaty" not in {slug for *_, slug in places_of(by_key["mining"])}
    assert len(places_of(by_key["metal_ores"])) == 12
    assert len(places_of(by_key["nonferrous"])) == 16
