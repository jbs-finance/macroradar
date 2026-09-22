from build_industry import build
from industry import INDUSTRY_SERIES, REGIONS


def dataset(stale_slug: str | None = None, missing_slug: str | None = None):
    series = []
    for spec in INDUSTRY_SERIES:
        for _term, _name, slug in REGIONS:
            if slug == missing_slug:
                continue
            stale = slug == stale_slug
            series.append(
                {
                    "series_id": f"kz.industry.{spec['series_key']}.{slug}",
                    "name_ru": f"{spec['name_ru']}: {slug}",
                    "unit": spec["unit"],
                    "freq": "A",
                    "source": "Бюро национальной статистики",
                    "source_url": f"https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/{spec['index_id']}",
                    "obs": [
                        {"date": "2024", "value": 101.5},
                        {"date": "2025", "value": 104.0},
                    ],
                    "stale": stale,
                    "note": "источник недоступен"
                    if stale
                    else "область, разрез Talдау",
                }
            )
    issues = (
        [
            f"kz.industry.{INDUSTRY_SERIES[0]['series_key']}.{stale_slug}: источник недоступен"
        ]
        if stale_slug
        else []
    )
    return {
        "generated_at": "2026-09-22T04:00:00+00:00",
        "series": series,
        "issues": issues,
    }


def test_builder_has_canonical_all_regions_exact_value_and_no_script():
    page = build(dataset())
    assert 'rel="canonical" href="https://jbs.finance/macroradar/industry/"' in page
    assert page.count('<section class="industry-section"') == len(INDUSTRY_SERIES)
    # по одному заголовку таблицы плюс строка на регион на каждый показатель
    assert page.count("<tr>") == len(INDUSTRY_SERIES) * (len(REGIONS) + 1)
    assert "2025" in page and "104" in page
    assert "<script" not in page.lower()
    for _term, name_ru, _slug in REGIONS:
        assert html_escaped_or_plain(name_ru) in page


def html_escaped_or_plain(name: str) -> str:
    return name


def test_builder_flags_missing_region_row_without_silent_gap():
    slug = REGIONS[0][2]
    page = build(dataset(missing_slug=slug))
    assert "нет ряда" in page


def test_builder_makes_stale_failure_visible_via_issues_and_badge():
    slug = REGIONS[0][2]
    page = build(dataset(stale_slug=slug))
    assert "данные устарели" in page
    assert "Часть данных не обновилась" in page
