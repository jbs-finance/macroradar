"""Здравоохранение по областям: койки и врачи на 10 000 населения.

Общий сбор и правила Talдау в regional.py. Оба ряда это административные данные
Минздрава (классификатор регионов 67, без районов), последний год в источнике
2023, отдельного бюллетеня БНС по ним нет. Объём медуслуг (704347) не берётся:
годовой ряд за 2023 год (941 млрд) меньше одного I квартала (756 млрд), квартальный
в Talдау обрывается на IV квартале 2024 (discovery 23.09.2026).

Запуск: .venv/bin/python health.py
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import regional
from etl import fetch_json

DATASET = Path(__file__).resolve().parent / "out" / "health.json"
PREFIX = "kz.health"
SOURCE = "Бюро национальной статистики (данные Минздрава РК)"

# 31.12.2023 плюс 1200 дней это 14.04.2027; на 23.09.2026 возраст 997 дней. Если БНС
# не выложит 2024 год к середине апреля 2027, сбор упадёт и потребует решения.
HEALTH_MAX_AGE_DAYS = 1200

HEALTH_SERIES = [
    {
        "series_key": "beds_per_10k",
        "index_id": 704311,
        "dics": "67",
        "extra_terms": (),
        "name_ru": "Больничные койки на 10 000 населения",
        "unit": "коек на 10 000 человек",
        "min": 0,
        "max": 500,
        "max_age_days": HEALTH_MAX_AGE_DAYS,
    },
    {
        "series_key": "doctors_per_10k",
        "index_id": 704316,
        "dics": "67",
        "extra_terms": (),
        "name_ru": "Врачи на 10 000 населения",
        "unit": "врачей на 10 000 человек",
        "min": 0,
        "max": 500,
        "max_age_days": HEALTH_MAX_AGE_DAYS,
    },
]


def build(
    dataset: Path = DATASET,
    today: date | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    return regional.build(HEALTH_SERIES, PREFIX, SOURCE, dataset, today, fetcher)


def missing_series(data: dict[str, Any]) -> list[str]:
    return regional.missing_series(data, HEALTH_SERIES, PREFIX)


if __name__ == "__main__":
    regional.main(HEALTH_SERIES, PREFIX, SOURCE, DATASET)
