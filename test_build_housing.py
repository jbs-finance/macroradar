from build_housing import build
from housing import CITIES, HOUSING_SERIES, REGIONS_AND_COUNTRY

# Индексы: годовой по сегменту, у одного города отдельный рост, чтобы проверить лидера.
YOY = {"new": 113.1, "resale": 109.0, "rent": 117.0}


def obs_for(spec, slug):
    key = spec["series_key"]
    if key == "built_ytd":
        return [{"date": "2025-08", "value": 2000.0}, {"date": "2026-08", "value": 2100.0}]
    kind, market = key.split("_")
    if kind == "price":
        return [{"date": "2026-07", "value": 600000.0}, {"date": "2026-08", "value": 625435.0}]
    if kind == "yoy":
        value = 142.5 if (slug, market) == ("pavlodar", "rent") else YOY[market]
        # У Актобе индекс отстаёт на месяц: рядом с августовской ценой ему не место.
        return [{"date": "2026-05" if slug == "aktobe" else "2026-08", "value": value}]
    return [{"date": "2026-08", "value": 104.2 if market == "rent" else 99.96}]


def dataset():
    series = [
        {
            "series_id": f"kz.housing.{spec['series_key']}.{slug}",
            "name_ru": spec["name_ru"],
            "unit": spec["unit"],
            "freq": "M",
            "source": "Бюро национальной статистики",
            "source_url": f"https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/{spec['index_id']}",
            "obs": obs_for(spec, slug),
            "stale": False,
            "note": "разрез Talдау",
        }
        for spec in HOUSING_SERIES
        for _term, _name, slug in spec["places"]
    ]
    return {"generated_at": "2026-09-23T04:00:00+00:00", "series": series, "issues": []}


def test_headline_names_fastest_segment_month_and_city():
    page = build(dataset())
    assert "Аренда квартир за год подорожала на" in page
    assert "17,0%" in page and "За август подорожала на 4,2%." in page
    assert "Быстрее всего в городе Павлодар: +42,5% за год." in page
    assert "<script" not in page.lower()
    assert 'rel="canonical" href="https://jbs.finance/macroradar/housing/"' in page


def test_tables_cover_every_place_and_hide_index_of_another_month():
    page = build(dataset())
    assert page.count("<tr") == 2 + len(CITIES) + len(REGIONS_AND_COUNTRY)
    assert page.count('<td class="gap">н/д</td>') == 3  # три сегмента Актобе
    # 99,96 округляется в ноль: без знака минус.
    assert "−0,0%" not in page and "+0,0%" not in page
    assert "+5,0%" in page  # ввод 2100 против 2000
    assert 'class="table-wrap"' in page and "housing-summary" in page


def test_empty_dataset_renders_no_data_block():
    page = build({"generated_at": "2026-09-23T04:00:00+00:00", "series": [], "issues": []})
    assert "ряды по жилью не собраны" in page
