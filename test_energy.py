import json
from pathlib import Path

import pytest

from energy import ENERGY_SERIES, build, parse_national_series
from etl import SourceError


SPEC = ENERGY_SERIES[1]


def payload(periods=None, terms=None):
    return [{"termNames": terms or SPEC["terms"], "periods": periods or [
        {"date": "31.12.2025", "value": "80050.5"},
        {"date": "31.12.2023", "value": "74216.029"},
    ]}]


def test_parse_exact_national_series_and_sorts_dates():
    obs = parse_national_series(payload(), SPEC)
    assert [(item.date, item.value) for item in obs] == [
        ("2023", 74216.029),
        ("2025", 80050.5),
    ]


@pytest.mark.parametrize("bad", [[], {}, [{"termNames": SPEC["terms"], "periods": []}]])
def test_empty_or_malformed_payload_is_rejected(bad):
    with pytest.raises(SourceError):
        parse_national_series(bad, SPEC)


def test_stale_fallback_on_source_error(tmp_path: Path):
    old = {
        "series_id": SPEC["series_id"], "name_ru": SPEC["name_ru"], "unit": SPEC["unit"],
        "freq": "A", "source": "Бюро национальной статистики", "source_url": SPEC["url"],
        "fetched_at": "2026-01-01T00:00:00+00:00", "obs": [{"date": "2025", "value": 80050.5}],
        "stale": False, "note": "национальный разрез БНС",
    }
    dataset = tmp_path / "energy.json"
    dataset.write_text(json.dumps({"series": [old]}), encoding="utf-8")

    def fail(*args, **kwargs):
        raise SourceError("источник недоступен")

    data = build(dataset, fetcher=fail)
    fallback = next(item for item in data["series"] if item["series_id"] == SPEC["series_id"])
    assert fallback["stale"] is True
    assert fallback["note"] == "источник недоступен"
    assert any(SPEC["series_id"] in issue for issue in data["issues"])
