"""Тесты сборки страницы: формат чисел, дельты, SVG, целостность документа."""

import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from build_pulse import build, fmt_date, fmt_num, fx_row, pct_change, spark

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def fx_series(values, sid="kz.fx.usd", freq="D"):
    today = date.today()
    obs = [
        {
            "date": (today - timedelta(days=30 * (len(values) - 1 - i))).isoformat(),
            "value": v,
        }
        for i, v in enumerate(values)
    ]
    return {
        "series_id": sid,
        "name_ru": "Курс USD",
        "unit": "тенге за 1 единицу",
        "freq": freq,
        "source": "Национальный Банк РК",
        "source_url": "https://example.org",
        "fetched_at": "2026-09-02T06:00:00+00:00",
        "obs": obs,
        "stale": False,
        "note": "",
    }


class TestFormat:
    def test_thousands_and_decimal_are_russian(self):
        assert fmt_num(306238.5, 2) == "306\u00a0238,50"
        assert fmt_num(4.77, 2) == "4,77"

    def test_zero_digits(self):
        assert fmt_num(14692.13, 0) == "14\u00a0692"

    def test_year_stays_year_but_iso_becomes_russian(self):
        assert fmt_date("2025") == "2025"
        assert fmt_date("2026-09-02") == "2 сентября 2026"


class TestPctChange:
    def test_daily_compares_with_point_nearest_to_year_ago(self):
        s = fx_series([400.0] * 12 + [460.0])
        assert pct_change(s, 365) == pytest.approx(15.0, abs=0.1)

    def test_annual_compares_with_previous_point(self):
        s = {
            "freq": "A",
            "obs": [{"date": "2024", "value": 100.0}, {"date": "2025", "value": 110.0}],
        }
        assert pct_change(s, 365) == pytest.approx(10.0)

    def test_single_point_gives_none(self):
        s = {"freq": "A", "obs": [{"date": "2025", "value": 1.0}]}
        assert pct_change(s, 365) is None

    def test_zero_base_does_not_divide(self):
        s = {
            "freq": "A",
            "obs": [{"date": "2024", "value": 0.0}, {"date": "2025", "value": 5.0}],
        }
        assert pct_change(s, 365) is None


class TestSpark:
    def test_flat_series_does_not_divide_by_zero(self):
        svg = spark([{"value": 5.0}, {"value": 5.0}, {"value": 5.0}])
        assert "polyline" in svg
        assert "nan" not in svg.lower()

    def test_point_count_matches_observations(self):
        svg = spark([{"value": float(i)} for i in range(10)])
        poly = re.search(r'class="spark-line" points="([^"]+)"', svg).group(1)
        assert len(poly.split()) == 10

    def test_higher_value_sits_higher_on_canvas(self):
        svg = spark([{"value": 1.0}, {"value": 100.0}])
        poly = re.search(r'class="spark-line" points="([^"]+)"', svg).group(1)
        first_y = float(poly.split()[0].split(",")[1])
        last_y = float(poly.split()[1].split(",")[1])
        assert last_y < first_y


class TestBuildDocument:
    def dataset(self, **over):
        data = {
            "generated_at": "2026-09-02T06:00:00+00:00",
            "series": [fx_series([400.0, 430.0, 458.45])],
            "issues": [],
        }
        data.update(over)
        return data

    def test_document_is_self_contained(self):
        page = build(self.dataset())
        assert "<!doctype html>" in page
        assert page.count("<html") == 1 and page.count("</html>") == 1
        assert not re.search(r'(src|href)="https?://', page)
        assert "<script" not in page

    def test_noindex_is_present(self):
        assert 'name="robots" content="noindex' in build(self.dataset())

    def test_css_actually_rendered(self):
        """Страница без стилей проходит все прочие проверки и выглядит сломанной."""
        page = build(self.dataset())
        assert "{{" not in page
        assert ":root {" in page

    def test_value_and_source_shown_together(self):
        page = build(self.dataset())
        assert "458,45" in page
        assert "Национальный Банк РК" in page

    def test_issues_render_warning_block(self):
        page = build(self.dataset(issues=["kz.cpi.yoy: источник недоступен"]))
        assert "не обновилась" in page
        assert "kz.cpi.yoy" in page

    def test_no_issues_no_warning_block(self):
        assert "не обновилась" not in build(self.dataset())

    def test_stale_series_marked_on_card(self):
        stale = fx_series([400.0, 430.0])
        stale["stale"] = True
        page = build(self.dataset(series=[stale]))
        assert "данные устарели" in page

    def test_no_dashes_in_visible_text(self):
        """Тире в интерфейсных текстах запрещено правилами оформления."""
        page = build(self.dataset())
        visible = re.sub(r"<style.*?</style>", "", page, flags=re.DOTALL)
        visible = re.sub(r"<[^>]+>", " ", visible)
        assert EM_DASH not in visible and EN_DASH not in visible

    def test_real_dataset_builds(self):
        """Гейт на настоящей выгрузке: свежая из out, иначе снимок из fixtures."""
        from build_pulse import DATASET

        dataset = DATASET if DATASET.exists() else Path(__file__).parent / "fixtures" / "pulse.json"
        page = build(json.loads(dataset.read_text(encoding="utf-8")))
        assert len(page) > 5000


class TestFxTable:
    """Курсы показываются таблицей, график раскрывается по клику на валюту."""

    def row(self, values, stale=False, sid="kz.fx.usd"):
        s = fx_series(values, sid=sid)
        s["stale"] = stale
        return fx_row(s)

    def test_row_shows_code_rate_and_direction(self):
        markup = self.row([400.0] * 12 + [460.0])
        assert ">USD<" in markup
        assert "460,00" in markup
        assert "fx-up" in markup and "\u25b2" in markup

    def test_falling_rate_marked_down(self):
        markup = self.row([500.0] * 12 + [455.0])
        assert "fx-down" in markup and "\u25bc" in markup

    def test_chart_is_inside_collapsed_details(self):
        """График не должен занимать место, пока его не попросили."""
        markup = self.row([400.0, 430.0, 460.0])
        assert markup.strip().startswith("<details")
        assert "open" not in markup.split(">")[0]
        assert "spark-line" in markup

    def test_no_javascript_used_for_disclosure(self):
        markup = self.row([400.0, 430.0])
        assert "onclick" not in markup and "<script" not in markup

    def test_stale_row_marked(self):
        assert "устарело" in self.row([400.0, 430.0], stale=True)

    def test_missing_base_does_not_crash(self):
        markup = self.row([460.0])
        assert "нет базы" in markup

    def test_page_uses_table_not_cards_for_rates(self):
        page = build(
            {
                "generated_at": "2026-09-03T06:00:00+00:00",
                "series": [fx_series([400.0, 430.0, 458.45])],
                "issues": [],
            }
        )
        assert 'class="fx"' in page
        assert "Нажмите на валюту" in page


class TestNoDataIsVisible:
    """Отсутствие данных обязано быть видно на странице.

    Регресс, который эти тесты ловят: секция возвращает пустую строку, её заголовок
    остаётся в шаблоне, и читатель видит заголовок над пустотой. Либо на месте
    отсутствующих данных печатается ноль, неотличимый от настоящего нуля.
    """

    def test_no_data_names_the_reason(self):
        from layout import no_data

        markup = no_data("отчёт не собрался")
        assert "Данные не собрались" in markup
        assert "отчёт не собрался" in markup

    def test_no_data_escapes_reason(self):
        from layout import no_data

        assert "<script>" not in no_data("<script>x")

    def test_issues_notice_lists_every_issue(self):
        from layout import issues_notice

        markup = issues_notice(["первое", "второе"])
        assert markup.count("<li>") == 2
        assert 'class="notice"' in markup

    def test_issues_notice_empty_without_issues(self):
        from layout import issues_notice

        assert issues_notice([]) == ""
        assert issues_notice(None) == ""

    def test_budget_page_without_data_explains_itself(self):
        from build_budget import build as build_budget

        page = build_budget(None, None, None)
        body = re.search(r"(?s)<main\b[^>]*>(.*)</main>", page).group(1)
        assert body.count("Данные не собрались") == 3
        assert len(body) > 900

    def test_budget_page_shows_issues_of_every_source(self):
        from build_budget import build as build_budget

        page = build_budget(
            {"issues": ["отчёт за май не найден"]},
            {"issues": ["файл КГД пуст"]},
            {"issues": ["Акмолинская: свежих отчётов нет"]},
        )
        assert "Минфин: отчёт за май не найден" in page
        assert "Комитет госдоходов: файл КГД пуст" in page
        assert "Области: Акмолинская: свежих отчётов нет" in page

    def test_oblast_survives_without_minfin(self):
        """Свои данные области целы: они не должны исчезать вместе с Минфином."""
        from build_budget import build as build_budget

        oblast = {
            "regions": [
                {
                    "name": "Костанайская",
                    "kind": "full",
                    "year": 2026,
                    "months": 7,
                    "total": 100.0,
                    "taxes": 60.0,
                    "transfers": 20.0,
                    "pct": None,
                }
            ]
        }
        page = build_budget(None, None, oblast)
        assert "Костанайская" in page
        assert "Доходы регионов" in page


class TestFreshnessByAge:
    """Бейдж свежести смотрит и на возраст последней точки, не только на факт забора."""

    def test_thresholds_are_named_constants(self):
        from layout import MAX_AGE_DAYS

        assert MAX_AGE_DAYS == {"D": 7, "M": 60, "Q": 150, "A": 500}

    def test_annual_series_two_years_back_is_outdated(self):
        from layout import freshness_badge

        badge = freshness_badge("2024", "A", False, date(2026, 9, 6))
        assert "устарело: 2024" in badge

    def test_annual_series_last_year_stays_fresh(self):
        from layout import freshness_badge

        assert "badge-fresh" in freshness_badge("2025", "A", False, date(2026, 9, 6))

    def test_daily_series_week_old_is_outdated(self):
        from layout import freshness_badge

        badge = freshness_badge("2026-08-20", "D", False, date(2026, 9, 6))
        assert "устарело: 2026-08-20" in badge

    def test_monthly_series_last_month_stays_fresh(self):
        from layout import freshness_badge

        assert "badge-fresh" in freshness_badge(
            "2026-08", "M", False, date(2026, 9, 6)
        )

    def test_failed_fetch_still_wins(self):
        from layout import freshness_badge

        assert "данные устарели" in freshness_badge(
            "2026-09-05", "D", True, date(2026, 9, 6)
        )

    def test_unparsable_date_does_not_flag(self):
        from layout import freshness_badge

        assert "badge-fresh" in freshness_badge("не дата", "A", False, date(2026, 9, 6))

    def test_with_freshness_rewrites_card_badge(self):
        from layout import with_freshness

        markup = '<span class="badge badge-fresh">актуально</span>'
        series = {"freq": "A", "obs": [{"date": "2024", "value": 1.0}], "stale": False}
        assert "устарело: 2024" in with_freshness(markup, series, date(2026, 9, 6))


class TestZeroIsNotData:
    """Ноль не должен быть неотличим от настоящего нуля."""

    def test_empty_income_does_not_become_one(self):
        from minfin_block import income_split

        assert income_split([])["total"] == 0

    def test_level_card_says_no_data_instead_of_one(self):
        from minfin_block import level_card

        latest = {"total": {"fact": 10.0, "plan": 10.0, "pct": 100.0}, "income": []}
        markup = level_card("Тест", "подпись", latest)
        assert "нет данных" in markup
        assert "прочие доходы: 100,0%" not in markup

    def test_empty_year_shows_no_data_not_zero(self):
        from budget_block import series_stats

        markup = series_stats([None] * 12, [None] * 12, None)
        assert markup.count("нет данных") == 2
        assert ">0<" not in markup

    def test_empty_chart_is_marked(self):
        from budget_block import chart_svg

        svg = chart_svg([None] * 12, [None] * 12, "пусто", 2024, None)
        assert "нет данных за этот период" in svg


class TestRegionRanking:
    """Все регионы приходят одним периодом, поэтому это рейтинг, а не список."""

    def region(self, name, total):
        return {
            "name": name,
            "kind": "full",
            "year": 2026,
            "months": 7,
            "total": total,
            "taxes": total * 0.6,
            "transfers": total * 0.2,
            "pct": 96.0,
        }

    def test_period_named_once_not_in_every_row(self):
        from minfin_block import oblast_section

        markup = oblast_section(
            {"regions": [self.region("Первая", 300.0), self.region("Вторая", 200.0)]}
        )
        assert markup.count("январь-июль 2026") == 1
        assert markup.index("Первая") < markup.index("Вторая")
        assert "Отчитались за прошлые годы" not in markup
