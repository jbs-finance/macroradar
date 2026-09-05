"""Тесты отчётов Минфина и блоков исполнения бюджета и сравнения регионов."""

import json
import re
from pathlib import Path

import pytest

from budget import Workbook, column_index
from compare_block import compare_block, compare_rules, region_stats, spark
from minfin import covered_period, level_of, monthly, parse_report, parse_title
from minfin_block import (
    clean_name,
    minfin_section,
    month_chart,
    period_label,
    plan_table,
)


class FakeBook:
    def __init__(self, rows: list[list[str]]):
        self.sheets = [("ОИБ", "path/1")]
        self._rows = rows

    def rows(self, path):
        return self._rows


def money(value: float) -> str:
    return str(value * 1e6)


def report_rows() -> list[list[str]]:
    """Отчёт: коды в первой колонке, наименование сдвигается по уровню вложенности."""
    head = [""] * 17
    row = lambda code, level, name, plan, fact, pct: (
        [code]
        + ["" if i != level else name for i in range(1, 7)]
        + ["", "", ""]
        + [money(plan), money(fact), "", "", "", pct, ""]
    )
    return [
        head,
        ["I. ДОХОДЫ"]
        + [""] * 6
        + ["", "", "", money(200), money(190), "", "", "", "95", ""],
        row("1", 1, "Налоговые поступления", 100, 96, "96"),
        row("01", 2, "Подоходный налог", 60, 54, "90"),
        row("1", 3, "КПН", 40, 36, "90"),
        row("03", 2, "Социальный налог", 40, 42, "105"),
        row("2", 1, "Неналоговые поступления", 50, 40, "80"),
        row("01", 2, "Доходы от аренды", 50, 40, "80"),
    ]


# --- Разбор отчёта -------------------------------------------------------------


def test_column_index_handles_double_letters():
    assert column_index("A") == 0
    assert column_index("H") == 7
    assert column_index("AA") == 26


def test_parse_title_reads_both_languages():
    assert parse_title(
        "Report on the execution of the state budget as of June 1, 2026"
    ) == (2026, 6)
    assert parse_title(
        "Отчет об исполнении государственного бюджета на 1 июня 2026 года"
    ) == (2026, 6)
    assert (
        parse_title("Отчет об исполнении местного бюджета на 1 июня 2026 года") is None
    )


def test_covered_period_shifts_by_one_month():
    """Отчёт «на 1 июня» это январь-май, а «на 1 января» весь прошлый год."""
    assert covered_period(2026, 6) == (2026, 5)
    assert covered_period(2026, 1) == (2025, 12)


def test_level_of_reads_indent():
    assert level_of(["1", "Налоговые поступления"]) == 1
    assert level_of(["01", "", "Подоходный налог"]) == 2


def test_parse_report_takes_only_tax_block():
    """Ниже по отчёту те же заголовки повторяются в других разрезах бюджета."""
    parsed = parse_report(FakeBook(report_rows()))
    assert parsed["total"]["fact"] == pytest.approx(96.0)
    assert [i["name"] for i in parsed["items"]] == [
        "Подоходный налог",
        "Социальный налог",
    ]
    assert parsed["items"][0]["fact"] == pytest.approx(54.0)


def test_parse_report_ignores_deeper_levels():
    """Строка КПН вложена в подоходный налог: если её сложить, налог удвоится."""
    parsed = parse_report(FakeBook(report_rows()))
    assert sum(i["fact"] for i in parsed["items"]) == pytest.approx(96.0)


def test_parse_report_rejects_mismatch():
    rows = report_rows()
    rows[3][10] = money(600)  # план подоходного, факт оставим прежним
    rows[3][11] = money(500)
    with pytest.raises(Exception):
        parse_report(FakeBook(rows))


# --- Помесячные разности -------------------------------------------------------


def points(*specs) -> list[dict]:
    return [{"year": y, "months": m, "fact": f, "plan": p} for y, m, f, p in specs]


def test_monthly_differences():
    out = monthly(points((2026, 1, 100, 90), (2026, 2, 250, 240), (2026, 3, 400, 380)))
    assert [(m["period"], m["value"]) for m in out] == [
        ("2026-01", 100.0),
        ("2026-02", 150.0),
        ("2026-03", 150.0),
    ]
    assert out[1]["plan"] == pytest.approx(150.0)


def test_monthly_skips_gap_instead_of_splitting():
    """Пропущенный отчёт значит пропуск: делить разность на два месяца нельзя."""
    out = monthly(points((2026, 1, 100, 90), (2026, 3, 400, 380), (2026, 4, 500, 480)))
    assert [m["period"] for m in out] == ["2026-01", "2026-04"]


def test_monthly_january_equals_cumulative():
    out = monthly(points((2026, 1, 120, 100)))
    assert out[0]["value"] == pytest.approx(120.0)


# --- Блок исполнения -----------------------------------------------------------


def sample_minfin() -> dict:
    return {
        "latest": {
            "year": 2026,
            "months": 7,
            "period": "2026-07",
            "url": "https://www.gov.kz/x",
            "total": {"plan": 14690.0, "fact": 14112.0, "pct": 96.1},
            "items": [
                {
                    "code": "05",
                    "name": "Внутренние налоги",
                    "plan": 6185.0,
                    "fact": 5918.0,
                    "pct": 95.7,
                },
                {
                    "code": "01",
                    "name": "Подоходный налог",
                    "plan": 5486.0,
                    "fact": 5259.0,
                    "pct": 95.9,
                },
                {
                    "code": "07",
                    "name": "Прочие налоги",
                    "plan": 0.0,
                    "fact": 3.0,
                    "pct": 2399.0,
                },
            ],
            "year_ago": {"period": "2025-07", "fact": 12073.5},
        },
        "monthly": [
            {
                "period": "2026-01",
                "year": 2026,
                "month": 1,
                "value": 1541.0,
                "plan": 1305.0,
            },
            {
                "period": "2026-02",
                "year": 2026,
                "month": 2,
                "value": 2901.0,
                "plan": 2533.0,
            },
            {
                "period": "2026-05",
                "year": 2026,
                "month": 5,
                "value": 1642.0,
                "plan": 1831.0,
            },
        ],
        "issues": [],
    }


def test_period_label_spells_range():
    assert period_label(2026, 7) == "январь-июль 2026"
    assert period_label(2026, 1) == "январь 2026"


def test_clean_name_shortens_by_code():
    assert (
        clean_name({"code": "05", "name": "Внутренние налоги на товары"})
        == "НДС, акцизы и прочие внутренние"
    )


def test_clean_name_fixes_latin_letter():
    """В отчёте попадается латинская H в начале русских слов."""
    assert clean_name({"code": "99", "name": "Hалоги на что-то"}).startswith("Н")


def test_plan_table_hides_meaningless_percent():
    """У прочих налогов план нулевой, и процент исполнения был бы 2399%."""
    html = plan_table(sample_minfin()["latest"])
    assert "плана нет" in html
    assert "2 399" not in html


def test_plan_table_has_total_row():
    html = plan_table(sample_minfin()["latest"])
    assert "Все налоговые поступления" in html and "96,1%" in html


def test_month_chart_marks_missing_months():
    """Март и апрель отчётом не покрыты: столбиков нет, но подпись одна."""
    svg = month_chart(sample_minfin()["monthly"])
    assert svg.count("нет отчёта") == 1
    assert svg.count("<rect") == 3
    assert svg.count('class="plan"') == 3


def test_month_chart_tooltip_has_plan_and_fact():
    svg = month_chart(sample_minfin()["monthly"])
    assert "январь 2026: собрано 1 541 из 1 305 млрд" in svg


def test_minfin_section_reports_growth_and_execution():
    html = minfin_section(sample_minfin())
    assert "96,1%" in html
    assert "+16,9%" in html  # 14112 против 12073.5
    assert "январь-июль 2026" in html


def test_minfin_section_empty_without_data():
    assert minfin_section(None) == ""
    assert minfin_section({"latest": None}) == ""


# --- Сравнение регионов --------------------------------------------------------


def sample_dynamics() -> dict:
    return {
        "year": 2024,
        "months": ["Январь", "Февраль", "Март"],
        "total": [3.0, 4.0, 5.0],
        "regions": [
            {"name": "г.Алматы", "values": [2.0, 2.5, 3.0]},
            {"name": "Акмолинская", "values": [1.0, 1.5, 2.0]},
        ],
        "previous": {
            "year": 2023,
            "months": ["январь", "февраль"],
            "total": [2.0, 3.0, None],
            "regions": [
                {"name": "г. Алматы", "values": [1.5, 2.0, None]},
                {"name": "Акмолинская область", "values": [2.5, 3.0, None]},
            ],
        },
    }


def test_region_stats_counts_growth_on_common_months():
    from budget_block import build_series

    stats = {s["name"]: s for s in region_stats(build_series(sample_dynamics()))}
    almaty = stats["г.Алматы"]
    assert almaty["months"] == 2
    assert almaty["growth"] == pytest.approx((4.5 / 3.5 - 1) * 100)
    assert almaty["delta"] == pytest.approx(1.0)


def test_region_stats_marks_decline():
    from budget_block import build_series

    stats = {s["name"]: s for s in region_stats(build_series(sample_dynamics()))}
    assert stats["Акмолинская"]["delta"] < 0


def test_compare_block_has_three_modes():
    html, rules = compare_block(sample_dynamics())
    assert html.count('type="radio"') == 3
    assert "#md2:checked ~ .cmp-stage .cm2" in rules


def test_compare_block_orders_by_metric():
    html, _ = compare_block(sample_dynamics())
    modes = re.findall(r'class="cmp-mode cm\d">(.*?)</ol>', html, re.DOTALL)
    first_names = [re.search(r'rank-name">([^<]+)', m).group(1) for m in modes]
    assert first_names[0] == "г.Алматы"  # по объёму
    assert first_names[1] == "г.Алматы"  # по росту, у второго региона падение


def test_compare_block_notes_are_computed():
    html, _ = compare_block(sample_dynamics())
    assert "всех поступлений страны" in html
    assert "Быстрее всех" in html


def test_compare_rules_avoid_leaking_extra_indexes():
    rules = compare_rules(3)
    assert "#md3" not in rules


def test_spark_survives_short_series():
    assert spark([None, None]).startswith("<svg")
    assert "<polyline" in spark([1.0, 2.0, 1.5])


# --- Страница целиком ----------------------------------------------------------


def build_page() -> str:
    import build_tax

    here = Path(__file__).parent
    data = json.loads((here / "out" / "tax.json").read_text(encoding="utf-8"))
    budget = json.loads((here / "out" / "budget.json").read_text(encoding="utf-8"))
    return build_tax.build(data, budget, sample_minfin())


def test_page_carries_both_sources():
    page = build_page()
    assert "Сколько собирают на самом деле" in page
    assert "Кто платит: регионы" in page
    assert "Все регионы сразу" in page


def test_page_styles_rendered():
    page = build_page()
    assert ".plan-table th" in page and ".rank-bar.split::before" in page
    assert "#md1:checked" in page and "#rg1:checked" in page


def test_page_stays_script_free():
    page = build_page()
    assert "<script" not in page.replace('<script type="application/ld+json"', "")


def test_page_dataset_names_both_sources():
    page = build_page()
    assert "Министерство финансов РК" in page
    assert "Комитет государственных доходов МФ РК" in page


# --- Уровни бюджета ------------------------------------------------------------


def income_rows() -> list[list[str]]:
    """Категории доходов, а следом функциональные группы затрат."""
    def row(code, level, name, plan, fact):
        return (
            [code]
            + ["" if i != level else name for i in range(1, 7)]
            + ["", "", ""]
            + [money(plan), money(fact), "", "", "", "95", ""]
        )

    return [
        ["Коды бюджетной классификации", "Наименование"] + [""] * 15,
        ["1", "2"] + [""] * 15,
        row("1", 1, "Налоговые поступления", 100, 96),
        row("01", 2, "Подоходный налог", 60, 54),
        row("2", 1, "Неналоговые поступления", 10, 12),
        row("5", 1, "Поступления трансфертов", 80, 80),
        row("01", 1, "Государственные услуги общего характера", 30, 40),
        row("04", 1, "Образование", 50, 70),
    ]


def test_parse_income_stops_before_expenses():
    """Ниже доходов идут функциональные группы затрат с двузначным кодом."""
    from minfin import parse_income

    income = parse_income(income_rows())
    assert [i["name"] for i in income] == [
        "Налоговые поступления",
        "Неналоговые поступления",
        "Поступления трансфертов",
    ]


def test_parse_income_skips_header_rows():
    from minfin import parse_income

    income = parse_income(income_rows())
    assert all(i["code"].isdigit() and len(i["code"]) == 1 for i in income)


def test_income_split_separates_transfers():
    from minfin_block import income_split

    split = income_split(
        [
            {"name": "Налоговые поступления", "fact": 50.0},
            {"name": "Неналоговые поступления", "fact": 10.0},
            {"name": "Поступления трансфертов", "fact": 40.0},
        ]
    )
    assert split["taxes"] == 50.0
    assert split["transfers"] == 40.0
    assert split["other"] == pytest.approx(10.0)


def sample_with_local() -> dict:
    data = sample_minfin()
    data["latest"]["income"] = [
        {"code": "1", "name": "Налоговые поступления", "fact": 14112.0, "plan": 14690.0},
        {"code": "5", "name": "Поступления трансфертов", "fact": 1400.0, "plan": 1400.0},
    ]
    data["local"] = {
        "year": 2026,
        "months": 7,
        "period": "2026-07",
        "url": "https://www.gov.kz/y",
        "total": {"plan": 5170.0, "fact": 4764.0, "pct": 92.1},
        "items": [],
        "income": [
            {"code": "1", "name": "Налоговые поступления", "fact": 4764.0, "plan": 5170.0},
            {"code": "2", "name": "Неналоговые поступления", "fact": 479.0, "plan": 430.0},
            {"code": "5", "name": "Поступления трансфертов", "fact": 3620.0, "plan": 3617.0},
        ],
    }
    return data


def test_levels_section_shows_share_and_transfers():
    from minfin_block import levels_section

    html = levels_section(sample_with_local())
    assert "33,8%" in html  # 4764 из 14112 остаётся местным
    assert "40,8%" in html  # доля трансфертов в доходах местных бюджетов
    assert "Местные бюджеты" in html


def test_levels_section_empty_without_local():
    from minfin_block import levels_section

    assert levels_section(sample_minfin()) == ""


def test_minfin_section_includes_levels():
    html = minfin_section(sample_with_local())
    assert "Республика и места" in html
