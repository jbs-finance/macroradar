"""Тесты чтения .xls и сбора областных отчётов."""

import struct

import pytest

import xls
from minfin import category_code, parse_income, report_layout
from minfin_block import oblast_section, plural
from oblast import parse_period, summarize, too_old


def record(code: int, body: bytes) -> bytes:
    return struct.pack("<HH", code, len(body)) + body


def unicode_string(text: str) -> bytes:
    return struct.pack("<HB", len(text), 1) + text.encode("utf-16-le")


def label_row(row: int, col: int, index: int) -> bytes:
    return record(xls.LABELSST, struct.pack("<HHHI", row, col, 0, index))


def number_row(row: int, col: int, value: float) -> bytes:
    return record(
        xls.NUMBER, struct.pack("<HHH", row, col, 0) + struct.pack("<d", value)
    )


# --- Записи BIFF ---------------------------------------------------------------


def test_records_glue_continuation():
    """Длинная запись разрезана на CONTINUE, читаться должна как одна."""
    stream = (
        record(xls.SST, b"\x01\x02")
        + record(xls.CONTINUE, b"\x03")
        + record(xls.EOF, b"")
    )
    codes = [(code, body) for code, body in xls.records(stream)]
    assert codes[0] == (xls.SST, b"\x01\x02\x03")


def test_rk_value_decodes_all_four_shapes():
    """Упакованное число бывает целым и дробным, с делением на сто и без."""
    assert xls._rk_value((100 << 2) | 0x02) == 100.0
    assert xls._rk_value((12345 << 2) | 0x03) == pytest.approx(123.45)
    packed = struct.unpack("<Q", struct.pack("<d", 2.5))[0] >> 32
    assert xls._rk_value(int(packed) << 0 & 0xFFFFFFFC) == pytest.approx(2.5)


def test_unicode_string_reads_both_encodings():
    wide = struct.pack("<HB", 3, 1) + "Абв".encode("utf-16-le")
    assert xls._unicode_string(wide, 0)[0] == "Абв"
    narrow = struct.pack("<HB", 3, 0) + "abc".encode("cp1251")
    assert xls._unicode_string(narrow, 0)[0] == "abc"


def test_shared_strings_reads_table():
    body = struct.pack("<II", 2, 2) + unicode_string("Налоги") + unicode_string("План")
    assert xls.shared_strings(body) == ["Налоги", "План"]


def test_sheet_rows_places_cells_by_address():
    """Пропущенные ячейки не должны сдвигать колонки влево."""
    stream = (
        label_row(0, 0, 0)
        + label_row(0, 4, 1)
        + number_row(1, 4, 12.5)
        + record(xls.EOF, b"")
    )
    rows = xls.sheet_rows(stream, 0, ["Код", "Наименование"])
    assert rows[0] == ["Код", "", "", "", "Наименование"]
    assert rows[1][4] == "12.5"


def test_sheet_rows_reads_mulrk():
    body = struct.pack("<HH", 0, 1)
    for value in (100.0, 200.0):
        body += struct.pack("<HI", 0, (int(value) << 2) | 0x02)
    body += struct.pack("<H", 2)
    rows = xls.sheet_rows(record(xls.MULRK, body) + record(xls.EOF, b""), 0, [])
    assert rows[0][1:3] == ["100", "200"]


def test_workbook_stream_rejects_foreign_file():
    with pytest.raises(xls.XlsError):
        xls.workbook_stream(b"PK\x03\x04not an ole2 file")


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


# --- Сбор по регионам ----------------------------------------------------------


def test_parse_period_reads_both_date_styles():
    assert parse_period(
        "Отчет об исполнении бюджета области на 1 августа 2026 года"
    ) == (2026, 7)
    assert parse_period("отчет об исполнении бюджета на 01.08.2026г.") == (2026, 7)


def test_parse_period_skips_other_documents():
    assert parse_period("Гражданский бюджет на 01.08.2026 год") is None
    assert parse_period("Отчет о кассовом исполнении на 1 августа 2026 года") is None
    assert parse_period("Протокол собрания") is None


def test_parse_period_january_covers_previous_year():
    assert parse_period("Отчет об исполнении бюджета на 1 января 2026 года") == (
        2025,
        12,
    )


def test_too_old_cuts_stale_reports():
    assert too_old(2022, 7) is True
    assert too_old(2026, 7) is False


def sample_income() -> list[dict]:
    return [
        {"code": "1", "name": "Налоговые поступления", "plan": 100.0, "fact": 96.0},
        {"code": "2", "name": "Неналоговые поступления", "plan": 10.0, "fact": 12.0},
        {"code": "5", "name": "Поступления трансфертов", "plan": 90.0, "fact": 82.0},
    ]


def test_summarize_counts_own_share():
    report = {"year": 2026, "months": 7, "published": "2026-08-11", "id": 1}
    summary = summarize(sample_income(), "Тестовая", report, "test-karzhy")
    assert summary["total"] == pytest.approx(190.0)
    assert summary["transfers"] == pytest.approx(82.0)
    assert summary["own_share"] == pytest.approx(56.8, abs=0.1)
    assert summary["period"] == "2026-07"


# --- Блок на странице ----------------------------------------------------------


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
    assert "Астана" in html and "январь-июль 2026" in html
    assert "865 млрд" in html


def test_oblast_section_says_how_many_reported():
    """Неполный список нельзя подавать как картину по стране."""
    html = oblast_section(sample_oblast())
    assert "1 региона из двадцати" in html


def test_oblast_section_empty_without_data():
    assert oblast_section(None) == ""
    assert oblast_section({"regions": []}) == ""


def test_plural_declension():
    assert plural(1, "регион", "регионов", "региона") == "1 регион"
    assert plural(3, "регион", "регионов", "региона") == "3 региона"
    assert plural(6, "регион", "регионов", "региона") == "6 регионов"
    assert plural(11, "регион", "регионов", "региона") == "11 регионов"
