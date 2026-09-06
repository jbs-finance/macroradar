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
