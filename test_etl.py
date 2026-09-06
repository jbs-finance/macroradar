"""Тесты разбора источников и гейтов публикации. Сеть не требуется."""

import urllib.error
from datetime import date, timedelta

import pytest

from etl import (
    Obs,
    Series,
    SourceError,
    month_points,
    coverage_gap,
    parse_nbk_xml,
    parse_worldbank,
    retriable,
    validate,
)

FX_XML = """<?xml version="1.0" encoding="utf-8"?>
<rates>
  <item><fullname>ДОЛЛАР США</fullname><title>USD</title>
    <description>462.31</description><quant>1</quant><change>-2.46</change></item>
  <item><fullname>ЮЖНО-КОРЕЙСКИХ ВОН</fullname><title>KRW</title>
    <description>33.81</description><quant>100</quant><change>0.00</change></item>
  <item><fullname>БИТЫЙ</fullname><title>XXX</title>
    <description>не число</description><quant>1</quant></item>
  <item><fullname>ПУСТОЙ</fullname><title>YYY</title>
    <description></description><quant>1</quant></item>
</rates>""".encode()


def series(obs, freq="A", sid="test"):
    return Series(
        series_id=sid,
        name_ru="Тест",
        unit="ед",
        freq=freq,
        source="Тест",
        source_url="https://example.org",
        fetched_at="2026-09-02T00:00:00+00:00",
        obs=obs,
    )


class TestNbkXml:
    def test_quant_normalizes_to_one_unit(self):
        rates = parse_nbk_xml(FX_XML)
        assert rates["USD"] == pytest.approx(462.31)
        # KRW котируется за 100 единиц, на страницу идёт курс за одну
        assert rates["KRW"] == pytest.approx(0.3381)

    def test_broken_items_are_skipped_not_fatal(self):
        rates = parse_nbk_xml(FX_XML)
        assert "XXX" not in rates
        assert "YYY" not in rates
        assert len(rates) == 2


class TestWorldBank:
    spec = {"indicator": "NY.GDP.MKTP.CD", "scale": 1e-9}

    def test_nulls_dropped_and_sorted_ascending(self):
        payload = [
            {"page": 1},
            [
                {"date": "2025", "value": 3.06e11},
                {"date": "2024", "value": None},
                {"date": "2023", "value": 2.6e11},
            ],
        ]
        obs = parse_worldbank(payload, self.spec)
        assert [o.date for o in obs] == ["2023", "2025"]
        assert obs[-1].value == pytest.approx(306.0, abs=1.0)

    def test_empty_payload_raises(self):
        with pytest.raises(SourceError):
            parse_worldbank([{"page": 1}, []], self.spec)

    def test_error_shape_raises(self):
        with pytest.raises(SourceError):
            parse_worldbank({"message": "invalid"}, self.spec)


class TestValidate:
    bounds = {"min": 0, "max": 1000}

    def test_fresh_series_passes(self):
        today = date.today()
        obs = [Obs(date=(today - timedelta(days=1)).isoformat(), value=460.0)]
        assert validate(series(obs, freq="D"), self.bounds) == []

    def test_empty_series_rejected(self):
        assert "ряд пустой" in validate(series([]), self.bounds)

    def test_duplicate_dates_rejected(self):
        obs = [Obs(date="2024", value=1.0), Obs(date="2024", value=2.0)]
        assert any("повтор" in p for p in validate(series(obs), self.bounds))

    def test_unsorted_dates_rejected(self):
        obs = [Obs(date="2025", value=1.0), Obs(date="2024", value=2.0)]
        assert any("не отсортированы" in p for p in validate(series(obs), self.bounds))

    def test_out_of_range_rejected(self):
        """Смена единицы измерения на стороне источника ловится диапазоном."""
        obs = [Obs(date=str(date.today().year - 1), value=3.06e11)]
        assert any("вне диапазона" in p for p in validate(series(obs), self.bounds))

    def test_stale_daily_series_rejected(self):
        obs = [Obs(date=(date.today() - timedelta(days=60)).isoformat(), value=460.0)]
        assert any("старше" in p for p in validate(series(obs, freq="D"), self.bounds))

    def test_stale_annual_series_rejected(self):
        obs = [Obs(date=str(date.today().year - 5), value=100.0)]
        assert any("старше" in p for p in validate(series(obs), self.bounds))


class TestMonthPoints:
    def test_count_order_and_today_included(self):
        today = date(2026, 9, 2)
        points = month_points(36, today)
        assert points == sorted(points)
        assert points[-1] == today
        assert points[0] == date(2023, 10, 1)
        assert len(points) == 37

    def test_year_boundary_crossed_correctly(self):
        points = month_points(3, date(2026, 2, 15))
        assert points[:3] == [date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


class TestRetryPolicy:
    def test_not_found_is_not_retried(self):
        """404 повтором не лечится, а лишние попытки стоят минут на обходе."""
        exc = urllib.error.HTTPError("u", 404, "no", {}, None)
        assert retriable(exc) is False

    def test_rate_limit_and_server_error_are_retried(self):
        assert retriable(urllib.error.HTTPError("u", 429, "slow", {}, None)) is True
        assert retriable(urllib.error.HTTPError("u", 503, "down", {}, None)) is True

    def test_network_error_is_retried(self):
        assert retriable(ConnectionResetError("сброс")) is True


class TestCoverageGap:
    def test_full_series_has_no_note(self):
        assert coverage_gap(37, 37) is None

    def test_short_series_is_marked(self):
        note = coverage_gap(3, 37)
        assert note and "3" in note and "37" in note

    def test_no_expectation_no_claim(self):
        assert coverage_gap(0, 0) is None


class TestFixedToday:
    def test_validate_uses_given_date_not_clock(self):
        """Дата приходит снаружи: прогон через полночь не должен менять вердикт."""
        obs = [Obs(date="2026-09-01", value=460.0)]
        fresh = validate(series(obs, freq="D"), {"min": 1, "max": 2000}, date(2026, 9, 5))
        stale = validate(series(obs, freq="D"), {"min": 1, "max": 2000}, date(2026, 12, 5))
        assert fresh == []
        assert any("старше" in p for p in stale)
