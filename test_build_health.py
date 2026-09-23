from build_health import build
from health import HEALTH_SERIES
from regional import REGIONS


def dataset(missing_slug: str | None = None):
    series = [
        {
            "series_id": f"kz.health.{spec['series_key']}.{slug}",
            "name_ru": spec["name_ru"],
            "unit": spec["unit"],
            "freq": "A",
            "source": "Бюро национальной статистики (данные Минздрава РК)",
            "source_url": f"https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/{spec['index_id']}",
            "obs": [{"date": "2022", "value": 40.1}, {"date": "2023", "value": 40.57}],
            "stale": False,
            "note": "область, разрез Talдау",
        }
        for spec in HEALTH_SERIES
        for _term, _name, slug in REGIONS
        if slug != missing_slug
    ]
    return {"generated_at": "2026-09-23T04:00:00+00:00", "series": series, "issues": []}


def test_page_has_canonical_all_regions_decimals_and_no_script():
    page = build(dataset())
    assert 'rel="canonical" href="https://jbs.finance/macroradar/health/"' in page
    assert page.count("<tr>") == len(HEALTH_SERIES) * (len(REGIONS) + 1)
    assert "40,57" in page
    assert "данные Минздрава РК" in page
    assert "<script" not in page.lower()


def test_table_and_tabs_fit_narrow_screens():
    page = build(dataset())
    # Общее правило table { min-width: 640px } давало горизонтальную прокрутку на телефоне.
    assert ".region-table { width: 100%; min-width: 0;" in page
    # Девять вкладок с заголовком не влезают на 1024 px, активная уходила за край.
    assert "@media (max-width: 1100px) { .tabs .title { display: none; } }" in page


def test_old_observation_is_marked_outdated_and_missing_region_is_named():
    page = build(dataset(missing_slug=REGIONS[0][2]))
    assert "устарело: 2023" in page
    assert "нет ряда" in page
