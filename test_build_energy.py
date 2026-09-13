from build_energy import build


def dataset(stale: bool = False):
    series = []
    for index, key in enumerate((
        "kz.energy.intensity", "kz.energy.primary_consumption",
        "kz.energy.final_consumption", "kz.energy.renewable_share",
    )):
        series.append({
            "series_id": key, "name_ru": f"Ряд {index + 1}", "unit": "%" if index == 3 else "тыс. т н. э.",
            "freq": "A", "source": "Бюро национальной статистики",
            "source_url": f"https://stat.gov.kz/example/{index}",
            "obs": [{"date": "2024", "value": 10.25 + index}, {"date": "2025", "value": 11.5 + index}],
            "stale": stale, "note": "источник недоступен" if stale else "национальный разрез БНС",
        })
    return {"generated_at": "2026-09-13T04:00:00+00:00", "series": series, "issues": ["тестовая ошибка"] if stale else []}


def test_builder_has_canonical_four_series_exact_observation_and_no_script():
    page = build(dataset())
    assert 'rel="canonical" href="https://jbs.finance/macroradar/energy/"' in page
    assert page.count('class="card energy-card"') == 4
    assert "2025 год" in page and "11,5" in page and "тыс. т н. э." in page
    assert 'href="https://stat.gov.kz/example/0"' in page
    assert "<script" not in page.lower()
    assert ".energy-grid > * { min-width: 0; }" in page
    assert ".series-table caption { position: absolute;" in page


def test_builder_makes_stale_failure_visible():
    page = build(dataset(stale=True))
    assert "данные устарели" in page
    assert "Последняя сборка не подтвердила ряд" in page
    assert "Часть данных не обновилась" in page
