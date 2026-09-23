"""Отраслевые ряды БНС по областям: металлургия и водозабор.

Общий сбор и правила Talдау в regional.py. Здесь только выбор разрезов:

1. Индекс чёрной металлургии (701625, отрасль 3079125, «к предыдущему периоду»
   2695730). Разрез «Ковка, прессование, порошковая металлургия» не берётся: у него
   два разных term с одинаковым именем, различить их без БНС нельзя.
2. Водозаборные сооружения (20385164) только по категории «Всего» (741917):
   городская и сельская местность это слагаемые того же агрегата.

Запуск: .venv/bin/python industry.py
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import regional
from etl import fetch_json

DATASET = Path(__file__).resolve().parent / "out" / "industry.json"
PREFIX = "kz.industry"
SOURCE = "Бюро национальной статистики"

# Структурная дыра источника: Talдау не публикует чёрную металлургию Акмолинской
# области после 2009 года (проверено 22.09.2026). Список должен пустеть, расти ему
# нельзя: любой другой пропавший ряд роняет прогон.
KNOWN_GAPS = frozenset({"kz.industry.metallurgy.aqmola"})

INDUSTRY_SERIES = [
    {
        "series_key": "metallurgy",
        "index_id": 701625,
        "dics": "68,4303,848",
        "extra_terms": (3079125, 2695730),
        # Полный дамп показателя 26 МБ на 34 011 строк (22.09.2026), общий потолок 8 МБ.
        "max_body": 40 * 1024 * 1024,
        "name_ru": "Индекс производства чёрной металлургии",
        "unit": "% к предыдущему периоду",
        # Малая база даёт всплески: разброс по 20 областям 5..1700 (22.09.2026).
        "min": 0,
        "max": 2000,
    },
    {
        "series_key": "water_intake",
        "index_id": 20385164,
        "dics": "68,776",
        "extra_terms": (741917,),
        "name_ru": "Число водозаборных сооружений",
        "unit": "ед.",
        "min": 0,
        "max": 5000,
    },
]


def build(
    dataset: Path = DATASET,
    today: date | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    return regional.build(INDUSTRY_SERIES, PREFIX, SOURCE, dataset, today, fetcher)


def missing_series(data: dict[str, Any]) -> list[str]:
    return regional.missing_series(data, INDUSTRY_SERIES, PREFIX, KNOWN_GAPS)


if __name__ == "__main__":
    regional.main(INDUSTRY_SERIES, PREFIX, SOURCE, DATASET, KNOWN_GAPS)
