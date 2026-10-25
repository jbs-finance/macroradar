from build_national_fund import build, count_text, return_bars, table_rows


def dataset():
    return {
        "generated_at": "2026-09-05T12:00:00+00:00",
        "assets": [
            {"date": "2016-09", "value": 64.537},
            {"date": "2017-12", "value": 57.7},
            {"date": "2025-12", "value": 60.1},
            {"date": "2026-07", "value": 66.121},
        ],
        "assets_stale": False,
        "assets_source": "https://nationalbank.kz/assets",
        "returns": [
            {"date": "2016", "value": 0.84},
            {"date": "2017", "value": 7.61},
            {"date": "2025", "value": 15.09},
        ],
        "returns_stale": False,
        "returns_source": "https://nationalbank.kz/returns",
        "issues": [],
    }


def test_page_has_canonical_sources_and_honest_availability_note():
    page = build(dataset())
    assert 'rel="canonical" href="https://jbs.finance/macroradar/national-fund/"' in page
    assert 'aria-current="page">Нацфонд' in page
    assert "66,12" in page
    assert "Источники и методология" in page
    assert "Операции и трансферты" in page
    assert "Структура Национального фонда" in page
    assert "Альтернативные инструменты" in page
    assert "Международные резервы НБК" in page
    assert "Пенсионные активы ЕНПФ" in page
    assert "Сводная сумма" in page and "не считается" in page
    assert "Общая сумма для них не рассчитывается" in page
    assert "после учёта обязательств" in page
    assert 'href="https://nationalbank.kz/assets"' in page
    assert page.index('id="enpf"') < page.index('id="availability-title"')
    assert page.index('id="map-title"') < page.index("Национальный фонд: объём и результат")
    assert "$66,12" in page
    main_story = page[: page.index('id="availability-title"')]
    assert " млрд USD" not in main_story
    assert " млрд KZT" not in main_story


def test_trends_share_one_section_but_keep_units_and_scales_separate():
    page = build(dataset())
    assert "Динамика Национального фонда" in page
    assert "Месячный ряд НБРК" in page
    assert "Годовая доходность, %" in page
    assert "Годовые точки" not in page
    assert "Точные годовые значения" in page
    assert "2026 (июль)" in page
    assert 'role="img" aria-label="2017: плюс 7,6 процента"' in page


def test_return_chart_preserves_negative_sign_and_uses_its_own_scale():
    chart = return_bars([{"date": "2024", "value": 7.5}, {"date": "2025", "value": -10.0}])
    assert "return-bar--positive" in chart
    assert "return-bar--negative" in chart
    assert "--bar-height:30.0000%" in chart
    assert "--bar-height:40.0000%" in chart


def test_incomplete_year_names_the_latest_month_in_exact_table():
    rows = table_rows(dataset()["assets"], dataset()["returns"])
    assert "2026 (июль)" in rows
    assert "2025 (декабрь)" not in rows


def test_page_marks_saved_data_without_removing_it():
    data = dataset()
    data["issues"] = ["активы НБРК не обновились"]
    page = build(data)
    assert "Часть данных не обновилась" in page
    assert "66,12" in page


def test_count_text_uses_russian_forms():
    assert count_text(121, ("точка", "точки", "точек")) == "121 точка"
    assert count_text(122, ("точка", "точки", "точек")) == "122 точки"
    assert count_text(119, ("точка", "точки", "точек")) == "119 точек"
