from datetime import date

import pytest

from etl import SourceError
from national_fund import ASSET_FIELD, history_start, parse_assets, parse_returns


def asset(stamp: str, value: float) -> dict:
    return {"reporting_date": f"{stamp}-28 00:00:00", ASSET_FIELD: value}


class TestAssets:
    def test_keeps_a_sorted_ten_year_window_and_converts_millions(self):
        today = date(2026, 9, 5)
        payload = [asset("2016-08", 60000)] + [
            asset(f"{year}-{month:02d}", 61000 + index)
            for index, (year, month) in enumerate(
                (year, month) for year in range(2016, 2027) for month in range(1, 13)
            )
        ]
        points = parse_assets(payload, today)
        assert points[0]["date"] == history_start("2026-09")
        assert points[-1]["date"] == "2026-09"
        assert points[0]["value"] == pytest.approx(61.008)

    def test_counts_a_full_decade_from_the_last_published_point(self):
        today = date(2026, 9, 5)
        payload = [
            asset(f"{year}-{month:02d}", 61000 + index)
            for index, (year, month) in enumerate(
                (year, month) for year in range(2016, 2027) for month in range(1, 13)
            )
            if f"{year}-{month:02d}" <= "2026-07"
        ]
        points = parse_assets(payload, today)
        assert points[0]["date"] == "2016-07"
        assert points[-1]["date"] == "2026-07"
        assert len(points) == 121
        assert points == sorted(points, key=lambda item: item["date"])

    def test_rejects_short_history(self):
        with pytest.raises(SourceError, match="месячных точек"):
            parse_assets([asset("2026-08", 66000)], date(2026, 9, 5))

    def test_rejects_value_in_wrong_unit(self):
        with pytest.raises(SourceError, match="вне ожидаемого диапазона"):
            parse_assets([asset("2026-08", 660000000)], date(2026, 9, 5))


class TestReturns:
    def test_reads_only_the_annual_return_column(self):
        markup = """
        <table><tr><th>Период</th><th>Доходность</th></tr>
        <tr><td>2016</td><td>0.84%</td><td>4.00%</td></tr>
        <tr><td>2017</td><td>-2,64%</td><td>3.27%</td></tr>
        <tr><td>2018</td><td>7.61%</td><td>3.64%</td></tr>
        <tr><td>2019</td><td>7.42%</td><td>3.49%</td></tr>
        <tr><td>2020</td><td>7.57%</td><td>3.69%</td></tr>
        <tr><td>2021</td><td>4.21%</td><td>3.72%</td></tr>
        <tr><td>2022</td><td>-10.35%</td><td>3.02%</td></tr>
        <tr><td>2023</td><td>11.38%</td><td>3.38%</td></tr>
        </table>
        """
        assert parse_returns(markup, 2016) == [
            {"date": "2016", "value": 0.84},
            {"date": "2017", "value": -2.64},
            {"date": "2018", "value": 7.61},
            {"date": "2019", "value": 7.42},
            {"date": "2020", "value": 7.57},
            {"date": "2021", "value": 4.21},
            {"date": "2022", "value": -10.35},
            {"date": "2023", "value": 11.38},
        ]

    def test_rejects_table_with_too_few_years(self):
        with pytest.raises(SourceError, match="таблице доходности"):
            parse_returns("<tr><td>2025</td><td>15.09%</td></tr>", 2016)
