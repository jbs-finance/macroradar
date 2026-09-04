"""Тесты разбора файлов КГД и блока поступлений на странице налогов."""

import json
from pathlib import Path

import pytest

import budget
import budget_block
from budget import (
    SourceError,
    fact_links,
    parse_dynamics,
    parse_fact,
    period_matches,
    summary_sheet,
)
from budget_block import (
    budget_section,
    build_series,
    chart_svg,
    drill_rules,
    nice_step,
    normalize,
)


class FakeBook:
    """Книга без zip: тестам нужны только листы и строки."""

    def __init__(
        self, sheets: dict[str, list[list[str]]], modified: str = "2025-05-26"
    ):
        self.sheets = [(name, f"path/{name}") for name in sheets]
        self._rows = {f"path/{name}": rows for name, rows in sheets.items()}
        self.modified = modified

    def rows(self, path):
        return self._rows[path]


def org_sheet(kpn: float, nds: float) -> list[list[str]]:
    return [
        ["ДГД по области"],
        ["тыс.тенге"],
        ["Код КБК", "Наименование КБК", "ГБ", "РБ"],
        ["1", "Налоговые поступления", str(kpn + nds), "0"],
        ["101110", "КПН", str(kpn), "0"],
        ["105101", "НДС", str(nds), "0"],
    ]


def book_with_summary() -> FakeBook:
    return FakeBook(
        {
            "РК": org_sheet(3_000_000, 1_000_000),
            "01": org_sheet(2_000_000, 600_000),
            "02": org_sheet(1_000_000, 400_000),
        }
    )


# --- Сводный лист --------------------------------------------------------------


def test_summary_sheet_found_by_structure():
    """Свод опознаётся по равенству сумме остальных листов, не по подписи."""
    assert summary_sheet(book_with_summary()) == "path/РК"


def test_summary_absent_when_sheets_do_not_double():
    book = FakeBook(
        {"01": org_sheet(2_000_000, 600_000), "02": org_sheet(1_000_000, 400_000)}
    )
    assert summary_sheet(book) is None


def test_parse_fact_does_not_double_country():
    """Главный риск источника: свод плюс органы дают удвоенный бюджет страны."""
    items = parse_fact(book_with_summary())
    assert sum(i["value"] for i in items) == pytest.approx(4.0)


def test_parse_fact_sums_sheets_without_summary():
    book = FakeBook(
        {"01": org_sheet(2_000_000, 600_000), "02": org_sheet(1_000_000, 400_000)}
    )
    assert sum(i["value"] for i in parse_fact(book)) == pytest.approx(4.0)


def test_parse_fact_ignores_top_level_rows():
    """Строка 101 повторяет свои подстатьи: если взять обе, налог удвоится."""
    sheet = [
        ["Код", "Наименование", "ГБ"],
        ["101", "Подоходный налог", "3000000"],
        ["101110", "КПН", "2000000"],
        ["101201", "ИПН", "1000000"],
    ]
    items = parse_fact(FakeBook({"01": sheet}))
    assert items[0]["value"] == pytest.approx(3.0)


def test_parse_fact_rejects_empty_book():
    with pytest.raises(SourceError):
        parse_fact(FakeBook({"01": [["текст"], ["без", "кодов"]]}))


# --- Отбор файла по периоду ----------------------------------------------------


def test_period_matches_rejects_last_year_file():
    """У КГД ссылка на апрель 2025 ведёт на файл, правленный в мае 2024."""
    assert period_matches("2024-05-15", 2025, 4) is False


def test_period_matches_accepts_publication_after_period():
    assert period_matches("2025-05-26", 2025, 3) is True


def test_period_matches_rejects_stale_publication():
    assert period_matches("2027-01-10", 2025, 3) is False


def test_period_matches_without_date():
    assert period_matches("", 2025, 3) is False


def test_fact_links_sorted_fresh_first():
    page = """
    <tr><td>2025 год</td><td><a href="/a.xlsx">январь</a><a href="/b.xlsx">март</a></td></tr>
    <tr><td>2024 год</td><td><a href="/c.xlsx">декабрь</a></td></tr>
    """
    links = fact_links(page)
    assert [(y, m) for _, y, m in links] == [(2025, 3), (2025, 1), (2024, 12)]


# --- Динамика ------------------------------------------------------------------


def dynamics_rows() -> list[list[str]]:
    # В файле КГД строка месяцев начинается прямо с «Январь», без ячейки-заголовка.
    return [
        ["Январь", "Февраль", "Март"],
        ["ДОХОДЫ, всего", "3000000", "4000000", "5000000"],
        ["г.Алматы", "2000000", "2500000", "3000000"],
        ["Акмолинская", "1000000", "1500000", "2000000"],
    ]


def test_parse_dynamics_splits_total_and_regions():
    data = parse_dynamics(dynamics_rows())
    assert data["total"] == [3.0, 4.0, 5.0]
    assert [r["name"] for r in data["regions"]] == ["г.Алматы", "Акмолинская"]


def test_regions_sum_to_total():
    """Подпись «доля в стране» врёт, если регионы не складываются в итог."""
    data = parse_dynamics(dynamics_rows())
    for i in range(3):
        assert sum(r["values"][i] for r in data["regions"]) == pytest.approx(
            data["total"][i]
        )


# --- Блок страницы -------------------------------------------------------------


def sample_budget() -> dict:
    return {
        "dynamics": {
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
                    {"name": "Акмолинская область", "values": [0.5, 1.0, None]},
                ],
            },
        },
        "structure": {
            "period": "2025-03",
            "year": 2025,
            "months": 3,
            "items": [
                {"code": "101", "name": "Подоходный налог", "value": 2089.7},
                {"code": "105", "name": "НДС", "value": 1918.8},
            ],
            "skipped": ["2025-04 (файл от 2024-05-15)"],
        },
    }


def test_normalize_matches_region_across_years():
    assert normalize("г.Алматы") == normalize("г. Алматы")
    assert normalize("Акмолинская") == normalize("Акмолинская область")


def test_build_series_country_first_then_by_size():
    series = build_series(sample_budget()["dynamics"])
    assert [s["name"] for s in series] == ["Республика", "г.Алматы", "Акмолинская"]
    assert series[1]["share"] == pytest.approx(7.5 / 12 * 100)


def test_build_series_attaches_previous_year():
    series = build_series(sample_budget()["dynamics"])
    assert series[1]["prev"][:2] == [1.5, 2.0]


def test_chart_svg_marks_year_in_tooltip():
    """Бледный столбик без года читался бы как значение текущего года."""
    svg = chart_svg([1.0, 2.0], [0.5, None], "тест", 2024, 2023)
    assert "январь 2024" in svg
    assert "январь 2023" in svg
    assert svg.count("<rect") == 3  # у февраля прошлого года данных нет


def test_chart_svg_survives_empty_series():
    svg = chart_svg([None] * 12, [None] * 12, "пусто", 2024, None)
    assert svg.startswith("<svg") and "<rect" not in svg


def test_nice_step_gives_round_grid():
    assert nice_step(2600) in (500, 1000)
    assert nice_step(8.0) in (2, 2.5)


def test_drill_rules_cover_every_series():
    rules = drill_rules(3)
    for i in range(3):
        assert f"#rg{i}:checked ~ .drill-stage .s{i}" in rules
    assert "#rg3" not in rules


def test_budget_section_empty_without_dynamics():
    assert budget_section({"dynamics": None}) == ("", "")


def test_series_count_matches_tabs():
    """Секция несёт два переключателя: регионы и метрику сравнения."""
    html, _ = budget_section(sample_budget())
    assert html.count('name="drill-region"') == html.count('<label for="rg') == 3
    assert html.count('name="cmp-metric"') == html.count('<label for="md') == 3


# --- Сборка страницы -----------------------------------------------------------


def build_page() -> str:
    import build_tax

    data = json.loads(
        (Path(__file__).parent / "out" / "tax.json").read_text(encoding="utf-8")
    )
    return build_tax.build(data, sample_budget())


def test_page_includes_budget_styles():
    """Прошлый раз стили уехали на прод пустыми: проверяем именно вывод, не константу."""
    page = build_page()
    assert "Кто платит: регионы" in page
    assert ".drill-tabs label" in page
    assert "#rg1:checked ~ .drill-stage .s1" in page
    assert "{style}" not in page and "{budget}" not in page


def test_page_has_no_scripts():
    """CSP на этой странице запрещает скрипты: интерактив обязан быть на CSS."""
    page = build_page()
    assert "<script" not in page.replace('<script type="application/ld+json"', "")
    assert "onclick" not in page


def test_page_charts_rendered():
    page = build_page()
    assert page.count('class="chart"') == 3
    assert 'class="bar-now"' in page


def test_page_declares_dataset():
    """Страница с живыми данными должна читаться поисковиком как набор данных."""
    page = build_page()
    assert '"@type": "Dataset"' in page
    assert "Поступления налогов в бюджет Казахстана" in page


def test_page_without_budget_has_no_dataset():
    import build_tax

    data = json.loads(
        (Path(__file__).parent / "out" / "tax.json").read_text(encoding="utf-8")
    )
    assert "@type" not in build_tax.build(data, None)
