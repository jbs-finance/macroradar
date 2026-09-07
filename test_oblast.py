"""Тесты разбора бюллетеня Минфина по регионам и форм отчётов."""

import pytest

from budget import SourceError
from minfin import category_code, parse_income, report_layout
from minfin_block import oblast_section, plural
from oblast import REGION_NAMES, clean, parse_period, read_income, sheet_title


# --- Формы отчётов -------------------------------------------------------------


def oblast_rows() -> list[list[str]]:
    """Областная форма: наименование в четвёртой колонке, факт в двенадцатой."""
    head = [""] * 15
    header = [""] * 15
    header[0] = "Коды бюджетной классификации"
    header[4] = "Наименование"
    header[8] = "Сводный план поступлений и финансирования"
    header[12] = "Исполнение поступлениий бюджета"
    header[13] = "Исп-е бюджета к плану на период, %"

    def row(name, plan, fact):
        line = [""] * 15
        line[4] = name
        line[8] = str(plan * 1e6)
        line[12] = str(fact * 1e6)
        line[13] = f"{fact / plan * 100:.4f}"
        return line

    return [
        head,
        header,
        row("I. ДОХОДЫ", 200.0, 190.0),
        row("НАЛОГОВЫЕ ПОСТУПЛЕНИЯ", 100.0, 96.0),
        row("НЕНАЛОГОВЫЕ ПОСТУПЛЕНИЯ", 10.0, 12.0),
        row("ПОСТУПЛЕНИЯ ТРАНСФЕРТОВ", 90.0, 82.0),
    ]


def test_report_layout_reads_oblast_form():
    assert report_layout(oblast_rows()) == (8, 12, 13, 4)


def test_parse_income_reads_uppercase_names():
    """В областной форме факт стоит в строке заглавными, без кода классификации."""
    income = parse_income(oblast_rows())
    assert [i["code"] for i in income] == ["1", "2", "5"]
    assert income[0]["fact"] == pytest.approx(96.0)


def test_report_layout_merges_split_header():
    rows = oblast_rows()
    header = rows[1]
    rows[1] = [c if i != 8 else "" for i, c in enumerate(header)]
    rows.insert(2, [c if i == 8 else "" for i, c in enumerate(header)])
    assert report_layout(rows)[0] == 8


def test_category_code_ignores_unrelated_rows():
    assert category_code("Поступления в бюджет области, ВСЕГО") is None
    assert category_code("Налоговые поступления") == "1"
    assert category_code("Неналоговые поступления") == "2"


# --- Разбор бюллетеня Минфина --------------------------------------------------


def bulletin_rows() -> list[list[str]]:
    """Лист региона так, как его отдаёт бюллетень: казахский слева, русский в
    седьмой колонке, план и факт в пятой и шестой."""
    return [
        ["12-кесте", "Таблица 12", "", "", "", "", ""],
        ["АБАЙ ОБЛЫСЫ", "ИСПОЛНЕНИЕ БЮДЖЕТА", "", "", "", "", ""],
        ["БЮДЖЕТІНІҢ АТҚАРЫЛУЫ", "ОБЛАСТЬ АБАЙ", "", "", "", "", ""],
        ["(млн.теңге)", "(млн. теңге)", "", "", "", "", ""],
        ["Атауы", "2023", "2024", "2025",
         "2026 ж. қантар-шілде есеп/январь-июль отчет 2026 г.", "", "Наименование"],
        ["жылдық/ годовой", "", "", "", "қантар-шілде/январь-июль", "", ""],
        ["1", "2", "3", "4", "5", "6", "7"],
        ["I. КІРІСТЕР", "", "", "", "260000", "252000", "I. ДОХОДЫ"],
        ["Салықтық түсімдер", "", "", "", "80000", "78000",
         "Налоговые поступления,_x000D_\r\n в том числе:"],
        ["Салықтық емес түсімдер", "", "", "", "4000", "4032",
         "Неналоговые поступления"],
        ["Негізгі капиталды сату", "", "", "", "8000", "8612",
         "Поступления от продажи основного капитала"],
        ["Арнаулы түсімдер", "", "", "", "0", "0", "Специальные поступления"],
        ["Трансферттердің түсімдері", "", "", "", "168000", "161356",
         "Поступления трансфертов"],
        ["II. ШЫҒЫНДАР", "", "", "", "250000", "240538", "II. ЗАТРАТЫ"],
    ]


def test_region_names_cover_all_administrative_units():
    """Три города республиканского значения не должны выпасть из разбора."""
    assert len(REGION_NAMES) == 20
    names = {name for name, _ in REGION_NAMES.values()}
    assert {"Астана", "Алматы", "Шымкент"} <= names
    assert REGION_NAMES["ОБЛАСТЬ АБАЙ"] == ("Абай", "abai")


def test_sheet_title_takes_region_not_table_number():
    """Номер таблицы внутри листа не совпадает с его именем, опора на название."""
    assert sheet_title(bulletin_rows()) == "ОБЛАСТЬ АБАЙ"


def test_parse_period_reads_month_range_from_header():
    assert parse_period(bulletin_rows()) == (2026, 7)


def test_parse_period_reads_single_month():
    rows = [["", "", "", "", "2026 ж. қаңтар есеп/январь отчет 2026 г.", "", ""]]
    assert parse_period(rows) == (2026, 1)


def test_parse_period_without_header_raises():
    with pytest.raises(SourceError):
        parse_period([["Атауы", "", "", "", "", "", "Наименование"]])


def test_clean_strips_source_garbage():
    assert clean("Налоговые поступления,_x000D_\r\n в том числе:") == (
        "Налоговые поступления, в том числе:"
    )


def test_read_income_converts_millions_to_billions():
    income, total, plan = read_income(bulletin_rows())
    assert total == pytest.approx(252.0)
    assert plan == pytest.approx(260.0)
    assert [i["code"] for i in income] == ["1", "2", "3", "4", "5"]
    taxes = next(i for i in income if i["code"] == "1")
    assert taxes["fact"] == pytest.approx(78.0)
    assert taxes["name"] == "Налоговые поступления"
    assert next(i for i in income if i["code"] == "5")["fact"] == pytest.approx(161.356)


def test_read_income_without_total_raises():
    rows = [r for r in bulletin_rows() if "I. ДОХОДЫ" not in r[6]]
    with pytest.raises(SourceError):
        read_income(rows)


# --- Блок на странице ----------------------------------------------------------


def sample_income() -> list[dict]:
    return [
        {"code": "1", "name": "Налоговые поступления", "plan": 700.0, "fact": 680.4},
        {"code": "2", "name": "Неналоговые поступления", "plan": 50.0, "fact": 48.3},
        {"code": "5", "name": "Поступления трансфертов", "plan": 140.0, "fact": 136.4},
    ]


def sample_oblast() -> dict:
    return {
        "regions": [
            {
                "name": "Астана",
                "slug": "astana-karzhy",
                "period": "2026-07",
                "year": 2026,
                "months": 7,
                "total": 865.1,
                "taxes": 680.4,
                "transfers": 136.4,
                "plan": 902.0,
                "pct": 96.0,
                "income": sample_income(),
            }
        ],
        "issues": ["Актюбинская: в файле нет разбираемого отчёта"],
    }


def test_oblast_section_lists_regions_with_periods():
    html = oblast_section(sample_oblast())
    assert "Астана" in html and "865 млрд" in html
    assert "план 96%" in html


def test_oblast_section_names_the_single_period():
    """Период называется один раз в шапке, а не двадцать раз в строках."""
    html = oblast_section(sample_oblast())
    assert "Все двадцать регионов за один период, январь-июль 2026" in html
    assert html.count("январь-июль 2026") == 1


def test_oblast_section_empty_without_data():
    assert oblast_section(None) == ""
    assert oblast_section({"regions": []}) == ""


def test_plural_declension():
    assert plural(1, "регион", "регионов", "региона") == "1 регион"
    assert plural(3, "регион", "регионов", "региона") == "3 региона"
    assert plural(6, "регион", "регионов", "региона") == "6 регионов"
    assert plural(11, "регион", "регионов", "региона") == "11 регионов"


# --- Формы без процента и текстовые документы ----------------------------------


def no_percent_rows() -> list[list[str]]:
    """Сводка, где рядом стоят прошлые годы, а колонки процента нет."""
    header = [""] * 8
    header[0] = "Наименование"
    header[4] = "План за 2026 г."
    header[5] = "План на 1.07.2026 г."
    header[6] = "Исполнение на 1.07.2026 г."

    def row(name, plan, fact):
        line = [""] * 8
        line[0] = name
        line[4] = str(plan * 2e6)
        line[5] = str(plan * 1e6)
        line[6] = str(fact * 1e6)
        return line

    return [
        ["Исполнение бюджета области"] + [""] * 7,
        header,
        row("Поступления в бюджет области, ВСЕГО", 200.0, 190.0),
        row("Налоговые поступления", 100.0, 96.0),
        row("Неналоговые поступления", 10.0, 12.0),
        row("Поступления трансфертов", 90.0, 82.0),
    ]


def test_report_layout_without_percent_column():
    """Часть управлений печатает план и исполнение без процента исполнения."""
    layout = report_layout(no_percent_rows())
    assert layout[0] == 5 and layout[1] == 6 and layout[2] == -1


def test_parse_income_reads_form_without_percent():
    income = parse_income(no_percent_rows())
    assert [i["code"] for i in income] == ["1", "2", "5"]
    assert income[0]["fact"] == pytest.approx(96.0)


def word_document(text: str) -> bytes:
    """Минимальный docx с одним абзацем."""
    import io
    import zipfile

    body = "".join(f"<w:t>{part}</w:t>" for part in text.split(" "))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml", f"<w:document><w:p>{body}</w:p></w:document>"
        )
    return buffer.getvalue()


def presentation_document(text: str) -> bytes:
    """Минимальная презентация с текстом слайда."""
    import io
    import zipfile

    body = "".join(f"<a:t>{part}</a:t>" for part in text.split("|"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f"<p:sld>{body}</p:sld>")
    return buffer.getvalue()


def test_oblast_row_shapes_by_kind():
    from minfin_block import oblast_row

    base = {
        "name": "Тест",
        "year": 2026,
        "months": 7,
        "total": 100.0,
        "taxes": 60.0,
        "transfers": 20.0,
        "pct": 98.0,
    }
    assert "своих 80%" in oblast_row({**base, "kind": "full"})
    assert "только налоги" in oblast_row({**base, "kind": "taxes"})
    # Краткая справка не даёт разреза доходов: на месте, где у полной формы стоит
    # доля, должна стоять названная сумма налогов, а не число, читаемое как процент.
    brief = oblast_row({**base, "kind": "brief"})
    assert "налогов 60 млрд" in brief
    assert "доля своих не считается" in brief


# --- Устойчивость обхода -------------------------------------------------------


