from datetime import date

from health import HEALTH_SERIES, build, missing_series
from regional import REGIONS


def dump():
    return [
        {"terms": [int(t)], "periods": [{"date": "31.12.2023", "value": "40.57"}]}
        for t, _n, _s in REGIONS
    ]


def test_2023_passes_within_own_lag_limit(tmp_path):
    data = build(tmp_path / "h.json", date(2026, 9, 23), lambda *a, **k: dump())
    assert data["issues"] == []
    assert missing_series(data) == []


def test_2023_fails_after_own_lag_limit(tmp_path):
    data = build(tmp_path / "h.json", date(2027, 6, 1), lambda *a, **k: dump())
    assert data["series"] == []
    assert len(missing_series(data)) == len(HEALTH_SERIES) * len(REGIONS)
    assert all("старше 1200 дней" in issue for issue in data["issues"])
