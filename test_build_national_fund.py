from build_national_fund import asset_chart, build, count_text, return_bars, table_rows


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
    assert "Как вложены средства Нацфонда" in page
    assert "Альтернативные инструменты" in page
    assert "Международные резервы НБК" in page
    assert "Пенсионные средства граждан" in page
    assert "Общая сумма для них не рассчитывается" in page
    assert "после учёта обязательств" in page
    assert 'href="https://nationalbank.kz/assets"' in page
    assert page.index('id="enpf"') < page.index('id="availability-title"')
    assert page.index('id="map-title"') < page.index('id="national-fund-title"')
    assert "Три пула, три задачи" in page
    assert page.index('id="children"') < page.index('id="reserves"') < page.index('id="enpf"')
    assert "Пенсионные средства граждан" in page
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
    assert "Точные годовые значения" not in page
    assert "июль 2026" in page
    assert 'role="img" aria-label="2017 год: плюс 7,6 процента"' in page
    assert ">+7,6%</span>" in page


def test_return_chart_preserves_negative_sign_and_uses_its_own_scale():
    chart = return_bars([{"date": "2024", "value": 7.5}, {"date": "2025", "value": -10.0}])
    assert "return-bar--positive" in chart
    assert "return-bar--negative" in chart
    assert "--bar-height:30.0000%" in chart
    assert "--bar-height:40.0000%" in chart


def test_incomplete_year_names_the_latest_month_in_exact_table():
    rows = table_rows(dataset()["assets"], dataset()["returns"])
    assert "июль 2026" in rows
    assert "декабрь 2025" not in rows


def test_asset_chart_labels_three_keyboard_focusable_anchor_points():
    chart = asset_chart(dataset()["assets"])
    assert chart.count('class="spark-anchor"') == 3
    assert chart.count('tabindex="0"') == 3
    assert "сентябрь 2016" in chart
    assert "декабрь 2017" in chart
    assert "июль 2026" in chart
    assert "$64,54" in chart and "$57,70" in chart and "$66,12" in chart


def test_visible_dates_are_human_readable_and_unambiguous():
    page = build(dataset())
    story = page[: page.index('id="availability-title"')]
    assert "июль 2026" in story
    assert "30 сентября 2026" in story
    assert "1 октября 2026" in story
    assert "2026-07" not in story
    assert "30.09.2026" not in story
    assert "01.10.2026" not in story


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
