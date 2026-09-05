"""Тесты внешней торговли: разбор Comtrade, расчёт сальдо, кэш срезов, страница."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from build_trade import build, ranking
from etl import Obs, Series
from trade import cached_breakdown, top_commodities, top_partners, trade_balance

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def series(sid, name, values, unit="млрд USD"):
    return Series(
        series_id=sid,
        name_ru=name,
        unit=unit,
        freq="A",
        source="World Bank",
        source_url="https://example.org",
        fetched_at="2026-09-03T06:00:00+00:00",
        obs=[Obs(date=str(2020 + i), value=v) for i, v in enumerate(values)],
    )


class TestTopPartners:
    def test_world_row_excluded_from_ranking(self):
        """Строка «весь мир» больше любой страны и раздавила бы масштаб."""
        rows = [
            {"partnerCode": 0, "primaryValue": 8e10},
            {"partnerCode": 156, "primaryValue": 1.5e10},
            {"partnerCode": 643, "primaryValue": 8e9},
        ]
        items = top_partners(rows)
        assert [i["label"] for i in items] == ["Китай", "Россия"]

    def test_values_converted_to_billions_and_sorted(self):
        rows = [
            {"partnerCode": 643, "primaryValue": 8.25e9},
            {"partnerCode": 156, "primaryValue": 1.52e10},
        ]
        items = top_partners(rows)
        assert items[0]["label"] == "Китай"
        assert items[0]["value"] == pytest.approx(15.2, abs=0.01)

    def test_unknown_code_shown_as_code_not_invented(self):
        items = top_partners([{"partnerCode": 999999, "primaryValue": 1e9}])
        assert items[0]["label"] == "код 999999"

    def test_zero_and_missing_values_skipped(self):
        rows = [
            {"partnerCode": 156, "primaryValue": 0},
            {"partnerCode": 643, "primaryValue": None},
            {"partnerCode": 380, "primaryValue": 1e9},
        ]
        assert len(top_partners(rows)) == 1

    def test_limit_applied(self):
        rows = [
            {"partnerCode": 100 + i, "primaryValue": (50 - i) * 1e9} for i in range(30)
        ]
        assert len(top_partners(rows, top_n=10)) == 10


class TestTopCommodities:
    def test_total_row_excluded_and_names_translated(self):
        rows = [
            {"cmdCode": "TOTAL", "primaryValue": 7.9e10},
            {"cmdCode": "27", "primaryValue": 4.3e10},
            {"cmdCode": "26", "primaryValue": 4.4e9},
        ]
        items = top_commodities(rows)
        assert [i["label"] for i in items] == [
            "Минеральное топливо, нефть",
            "Руды, шлак, зола",
        ]

    def test_unknown_hs_code_kept_visible(self):
        items = top_commodities([{"cmdCode": "99", "primaryValue": 1e9}])
        assert "99" in items[0]["label"]


class TestTradeBalance:
    def test_balance_is_export_minus_import(self):
        exports = series("kz.exports.usd", "Экспорт", [80.0, 92.0])
        imports = series("kz.imports.usd", "Импорт", [60.0, 74.5])
        balance = trade_balance(exports, imports)
        assert [o.value for o in balance.obs] == pytest.approx([20.0, 17.5])

    def test_years_without_both_sides_are_dropped(self):
        """Год с одной известной стороной дал бы сальдо, равное экспорту."""
        exports = series("kz.exports.usd", "Экспорт", [80.0, 92.0, 95.0])
        imports = series("kz.imports.usd", "Импорт", [60.0, 74.5])
        balance = trade_balance(exports, imports)
        assert [o.date for o in balance.obs] == ["2020", "2021"]

    def test_calculation_is_marked_as_derived(self):
        balance = trade_balance(
            series("kz.exports.usd", "Экспорт", [80.0]),
            series("kz.imports.usd", "Импорт", [60.0]),
        )
        assert "расчёт" in balance.note


class TestBreakdownCache:
    def fresh(self, days):
        stamp = datetime.now(timezone.utc) - timedelta(days=days)
        return {"exports.partners": {"fetched_at": stamp.isoformat(), "items": [1]}}

    def test_recent_breakdown_reused(self):
        assert cached_breakdown(self.fresh(2), "exports.partners") is not None

    def test_old_breakdown_not_reused(self):
        assert cached_breakdown(self.fresh(30), "exports.partners") is None

    def test_missing_key_returns_none(self):
        assert cached_breakdown({}, "exports.partners") is None

    def test_broken_timestamp_returns_none(self):
        bad = {"exports.partners": {"fetched_at": "не дата"}}
        assert cached_breakdown(bad, "exports.partners") is None


class TestRanking:
    def breakdown(self, **over):
        data = {
            "id": "exports.partners",
            "name_ru": "Экспорт по странам",
            "unit": "млрд USD",
            "year": 2025,
            "source": "UN Comtrade",
            "fetched_at": "2026-09-03T06:00:00+00:00",
            "items": [
                {"label": "Италия", "value": 15.64},
                {"label": "Китай", "value": 15.2},
                {"label": "Россия", "value": 8.25},
            ],
            "stale": False,
        }
        data.update(over)
        return data

    def test_longest_bar_is_full_width(self):
        markup = ranking(self.breakdown())
        widths = [float(w) for w in re.findall(r"width: ([\d.]+)%", markup)]
        assert widths[0] == pytest.approx(100.0)
        assert widths[-1] < widths[0]

    def test_stale_marked(self):
        assert "данные устарели" in ranking(self.breakdown(stale=True))

    def test_empty_items_do_not_crash(self):
        markup = ranking(self.breakdown(items=[]))
        assert "<ol>" in markup

    def test_labels_escaped(self):
        markup = ranking(self.breakdown(items=[{"label": "<script>x", "value": 1.0}]))
        assert "<script>" not in markup


class TestPage:
    def dataset(self, **over):
        data = {
            "generated_at": "2026-09-03T06:00:00+00:00",
            "series": [
                {
                    "series_id": "kz.exports.usd",
                    "name_ru": "Экспорт товаров и услуг",
                    "unit": "млрд USD",
                    "freq": "A",
                    "source": "World Bank",
                    "source_url": "https://example.org",
                    "fetched_at": "2026-09-03T06:00:00+00:00",
                    "obs": [
                        {"date": "2023", "value": 80.0},
                        {"date": "2024", "value": 92.07},
                    ],
                    "stale": False,
                    "note": "",
                }
            ],
            "breakdowns": [
                {
                    "id": "exports.partners",
                    "name_ru": "Экспорт по странам",
                    "unit": "млрд USD",
                    "year": 2025,
                    "source": "UN Comtrade",
                    "fetched_at": "2026-09-03T06:00:00+00:00",
                    "items": [{"label": "Италия", "value": 15.64}],
                    "stale": False,
                }
            ],
            "issues": [],
        }
        data.update(over)
        return data

    def test_page_is_self_contained(self):
        page = build(self.dataset())
        assert not re.search(r'<(img|link|script)[^>]+(src|href)="https?://(?!jbs\.finance)', page)
        assert "<script" not in page

    def test_noindex_present(self):
        assert 'rel="canonical" href="https://jbs.finance/macroradar/trade/"' in build(self.dataset())
        assert "noindex" not in build(self.dataset())

    def test_css_actually_rendered(self):
        """Незакрытая подстановка оставляет в CSS двойные скобки, и страница
        выходит без единого стиля. Ловится только проверкой готовой разметки."""
        page = build(self.dataset())
        assert "{{" not in page
        assert ":root {" in page and ".rank {" in page

    def test_shares_styles_with_pulse(self):
        """Две страницы одного сайта не должны разъезжаться в оформлении."""
        from build_pulse import STYLE

        assert "--accent: #C0603D;" in STYLE
        assert STYLE.split("\n")[1] in build(self.dataset())

    def test_no_dashes_in_visible_text(self):
        page = build(self.dataset())
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<style.*?</style>", "", page))
        assert EM_DASH not in visible and EN_DASH not in visible

    def test_issues_rendered(self):
        page = build(self.dataset(issues=["exports.partners: лимит источника"]))
        assert "не обновилась" in page
        assert "лимит источника" in page
