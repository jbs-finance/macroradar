from build_national_fund import build, count_text


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
    assert "Операции и трансферты: пока не включены" in page
    assert "Состав сберегательного портфеля" in page
    assert "36,3%" in page and "Альтернативные инструменты" in page
    assert "не доли всего Нацфонда на текущую дату" in page
    assert "за вычетом обязательств" in page
    assert 'href="https://nationalbank.kz/assets"' in page


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
