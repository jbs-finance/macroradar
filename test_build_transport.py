from build_transport import build
from regional import REGIONS
from transport import DIRECTIONS, TRANSPORT_SERIES

ANNUAL = {"total": 520.9, "international": 311.7, "export": 139.5, "import": 51.7, "transit": 120.5, "domestic": 188.9}


def obs_for(key, slug):
    if key == "cargo_yoy":
        history = [{"date": f"2025-{m:02d}", "value": 100.0 + m} for m in range(1, 13)]
        return [*history, {"date": "2026-07", "value": 95.0}, {"date": "2026-08", "value": 89.9}]
    if key == "passenger_yoy":
        # У Улытау последний месяц отстаёт: рядом с августом ему не место.
        month = "2026-06" if slug == "ulytau" else "2026-08"
        return [{"date": month, "value": 198.4 if slug == "kostanay" else 112.6}]
    base = ANNUAL[key.removeprefix("cargo_")] * 1e9
    return [{"date": "2024", "value": base}, {"date": "2025", "value": base * 1.049}]


def dataset():
    series = [
        {
            "series_id": f"kz.transport.{spec['series_key']}.{slug}",
            "name_ru": spec["name_ru"],
            "unit": spec["unit"],
            "freq": spec.get("freq", "A"),
            "source": "Бюро национальной статистики",
            "source_url": f"https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/{spec['index_id']}",
            "obs": obs_for(spec["series_key"], slug),
            "stale": False,
            "note": "разрез Talдау",
        }
        for spec in TRANSPORT_SERIES
        for _term, _name, slug in spec["places"]
    ]
    return {"generated_at": "2026-09-25T04:00:00+00:00", "series": series, "issues": []}


def test_headline_reports_cargo_drop_as_series_minimum_and_transit():
    page = build(dataset())
    assert "Грузооборот за август 2026 года" in page
    assert "сократился на 10,1%</span> к прошлому году, это минимум ряда с 2025 года." in page
    assert "Пассажирооборот вырос на 12,6%." in page
    assert "Транзит грузов за 2025 год" in page and "+4,9% к 2024 году." in page
    assert 'rel="canonical" href="https://jbs.finance/macroradar/transport/"' in page
    assert "<script" not in page.lower()


def test_tables_cover_directions_and_regions_and_hide_other_month():
    page = build(dataset())
    assert page.count("<tr") == 2 + len(DIRECTIONS) + len(REGIONS) + 1
    assert page.count('<td class="gap">н/д</td>') == 1  # Улытау
    assert "+98,4%" in page  # Костанайская первой после страны
    assert "Грузооборот по регионам не показан" in page


def test_empty_dataset_renders_no_data_block():
    page = build({"generated_at": "2026-09-25T04:00:00+00:00", "series": [], "issues": []})
    assert "ряды по транспорту не собраны" in page
