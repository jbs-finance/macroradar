"""Транспорт: грузооборот и пассажирооборот по данным БНС.

Общий сбор и правила Talдау в regional.py. Discovery 25.09.2026:

1. Индексы физического объёма к тому же месяцу прошлого года: грузооборот (702192,
   вид деятельности «Транспорт» 741335) и пассажирооборот (702190, все виды транспорта
   17901749), форма собственности «Всего» 741907. Проценты берутся у БНС.
2. Грузооборот только по стране. С января 2026 года областные индексы грузооборота в
   разы расходятся с прошлыми годами (август 2026: Кызылординская 2 356%, Абай 1 577%,
   страна 89,9%), у показателя появился парный ряд «нераспределённые по областям».
   Сопоставимость с прошлыми годами нарушена, по областям ряд не публикуется.
3. Абсолютный грузооборот по месяцам в Talдау обрывается на 2017 годе. Годовой
   (702179, разрез «Виды транспортных сообщений» 4309) идёт до 2025 года: экспорт,
   импорт и транзит в сумме дают международное сообщение без остатка. Разбивка по видам
   транспорта в годовом ряду противоречива (железная дорога 332 млрд т·км в 2024 году
   и 14,9 млрд в 2025), поэтому берётся только итог «Транспорт».

Запуск: .venv/bin/python transport.py
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import regional
from etl import fetch_json

DATASET = Path(__file__).resolve().parent / "out" / "transport.json"
PREFIX = "kz.transport"
SOURCE = "Бюро национальной статистики"

COUNTRY = ("741880", "Казахстан", "kz")
TRANSPORT, ALL_OWNERSHIP, TO_YEAR_AGO = 741335, 741907, 2695732

# (ключ, term вида сообщения, подпись) в порядке показа на странице.
DIRECTIONS = [
    ("total", 19805998, "Всего"),
    ("international", 19805973, "Международное сообщение"),
    ("export", 19805898, "Экспорт"),
    ("import", 19805899, "Импорт"),
    ("transit", 19806003, "Транзит"),
    ("domestic", 19805661, "Внутри страны"),
]

TRANSPORT_SERIES: list[dict[str, Any]] = [
    {
        "series_key": "cargo_yoy",
        "index_id": 702192,
        "dics": "68,1214,59,848",
        "period": 4,
        "freq": "M",
        "places": [COUNTRY],
        "extra_terms": (TRANSPORT, ALL_OWNERSHIP, TO_YEAR_AGO),
        "max_body": 32 * 1024 * 1024,  # 14,7 МБ на 25.09.2026
        "name_ru": "Грузооборот: к тому же месяцу прошлого года",
        "unit": "%",
        "min": 30,
        "max": 300,  # живой 89,9..131,2
    },
    {
        "series_key": "passenger_yoy",
        "index_id": 702190,
        "dics": "68,59,848,2984",
        "period": 4,
        "freq": "M",
        "places": [COUNTRY, *regional.REGIONS],
        "extra_terms": (ALL_OWNERSHIP, TO_YEAR_AGO, 17901749),
        "max_body": 32 * 1024 * 1024,  # 10,6 МБ
        "name_ru": "Пассажирооборот: к тому же месяцу прошлого года",
        "unit": "%",
        "min": 0,
        "max": 3000,  # живой 1,8..1 246,8, провал и отскок 2020-2021 годов
    },
]
for key, term, label in DIRECTIONS:
    TRANSPORT_SERIES.append(
        {
            "series_key": f"cargo_{key}",
            "index_id": 702179,
            "dics": "68,1214,59,4309",
            "places": [COUNTRY],
            "extra_terms": (TRANSPORT, ALL_OWNERSHIP, term),
            "max_body": 32 * 1024 * 1024,  # 11,2 МБ
            "name_ru": f"Грузооборот, {label.lower()}",
            "unit": "т·км",
            "min": 0,
            "max": 2_000_000_000_000,  # живой итог 503..610 млрд
        }
    )


def build(
    dataset: Path = DATASET,
    today: date | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    return regional.build(TRANSPORT_SERIES, PREFIX, SOURCE, dataset, today, fetcher)


def missing_series(data: dict[str, Any]) -> list[str]:
    return regional.missing_series(data, TRANSPORT_SERIES, PREFIX)


if __name__ == "__main__":
    regional.main(TRANSPORT_SERIES, PREFIX, SOURCE, DATASET)
