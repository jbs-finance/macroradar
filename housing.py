"""Жилая недвижимость: цены 1 м², индексы цен и ввод жилья.

Общий сбор и правила Talдау в regional.py. Discovery 23.09.2026:

1. Цена 1 м² (703116, разрезы 67 и 2817): цена за квадратный метр общей площади по
   выборке базовых объектов, форма 1-ЦРЖ, публикация на 9-й день после месяца.
   Аренда в тенге за м² в месяц.
2. Индексы цен (703083, разрезы 67, 848, 2817): официальный процент к тому же месяцу
   прошлого года и к предыдущему месяцу. Проценты берутся у БНС, свои не считаются.
3. Ввод жилья (701960, разрезы 68 и 300, период 8): общая площадь с начала года по
   областям, категория «Всего» (808325).
4. Цены идут по 20 городам. «Г.ШЫМКЕНТ» в Talдау два: 261477 до мая 2018 года и
   20242100 с июня 2018 года (город республиканского значения). Берётся новый.
5. Дыра источника на 23.09.2026: индексов 703083 за июнь и июль 2026 года нет, цены за
   эти месяцы есть. Страница показывает индекс только за тот же месяц, что и цену.

Запуск: .venv/bin/python housing.py
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import regional
from etl import fetch_json

DATASET = Path(__file__).resolve().parent / "out" / "housing.json"
PREFIX = "kz.housing"
SOURCE = "Бюро национальной статистики"

COUNTRY = ("741880", "Казахстан", "kz")
# (term id, имя, slug) города в классификаторе регионов 67, снято 23.09.2026.
CITIES: list[tuple[str, str, str]] = [
    COUNTRY,
    ("268020", "Алматы", "almaty"),
    ("268012", "Астана", "astana"),
    ("20242100", "Шымкент", "shymkent"),
    ("260909", "Актау", "aktau"),
    ("248877", "Актобе", "aktobe"),
    ("252313", "Атырау", "atyrau"),
    ("256637", "Жезказган", "zhezkazgan"),
    ("256621", "Караганда", "karaganda"),
    ("247785", "Кокшетау", "kokshetau"),
    ("250518", "Конаев", "konaev"),
    ("258744", "Костанай", "kostanay"),
    ("260101", "Кызылорда", "kyzylorda"),
    ("263011", "Павлодар", "pavlodar"),
    ("264030", "Петропавловск", "petropavlovsk"),
    ("265068", "Семей", "semey"),
    ("250504", "Талдыкорган", "taldykorgan"),
    ("255579", "Тараз", "taraz"),
    ("20243034", "Туркестан", "turkestan"),
    ("253167", "Уральск", "uralsk"),
    ("264992", "Усть-Каменогорск", "ust-kamenogorsk"),
]
REGIONS_AND_COUNTRY = [COUNTRY, *regional.REGIONS]

# (ключ, term сегмента рынка, подпись, единица цены)
MARKETS = [
    ("new", 18596801, "Новые квартиры", "тенге за м²"),
    ("resale", 18844097, "Вторичные квартиры", "тенге за м²"),
    ("rent", 18120822, "Аренда квартир", "тенге за м² в месяц"),
]
YOY, MOM = 2695732, 2695730
# Дамп индекса 7,3 МБ (23.09.2026) при общем потолке 8 МБ.
INDEX_MAX_BODY = 16 * 1024 * 1024

HOUSING_SERIES: list[dict[str, Any]] = []
for key, market, label, unit in MARKETS:
    HOUSING_SERIES += [
        {
            "series_key": f"price_{key}",
            "index_id": 703116,
            "dics": "67,2817",
            "period": 4,
            "freq": "M",
            "places": CITIES,
            "extra_terms": (market,),
            "name_ru": f"{label}: цена 1 м²",
            "unit": unit,
            # Живой разброс 23.09.2026: покупка 90 000..752 302, аренда 421..6 224.
            "min": 100 if key == "rent" else 10_000,
            "max": 100_000 if key == "rent" else 5_000_000,
        },
        {
            "series_key": f"yoy_{key}",
            "index_id": 703083,
            "dics": "67,848,2817",
            "period": 4,
            "freq": "M",
            "places": CITIES,
            "extra_terms": (YOY, market),
            "max_body": INDEX_MAX_BODY,
            "keep_last": 25,
            "name_ru": f"{label}: к тому же месяцу прошлого года",
            "unit": "%",
            # Живой разброс 78,8..236,3.
            "min": 50,
            "max": 400,
        },
        {
            "series_key": f"mom_{key}",
            "index_id": 703083,
            "dics": "67,848,2817",
            "period": 4,
            "freq": "M",
            "places": CITIES,
            "extra_terms": (MOM, market),
            "max_body": INDEX_MAX_BODY,
            "keep_last": 13,
            "name_ru": f"{label}: к предыдущему месяцу",
            "unit": "%",
            # Живой разброс 83,3..156,8.
            "min": 50,
            "max": 250,
        },
    ]
HOUSING_SERIES.append(
    {
        "series_key": "built_ytd",
        "index_id": 701960,
        "dics": "68,300",
        "period": 8,
        "freq": "M",
        "places": REGIONS_AND_COUNTRY,
        "extra_terms": (808325,),
        "name_ru": "Ввод жилья с начала года",
        "unit": "м² общей площади",
        # Живой максимум 19 939 866 (страна за год).
        "min": 0,
        "max": 60_000_000,
    }
)


def build(
    dataset: Path = DATASET,
    today: date | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    return regional.build(HOUSING_SERIES, PREFIX, SOURCE, dataset, today, fetcher)


def missing_series(data: dict[str, Any]) -> list[str]:
    return regional.missing_series(data, HOUSING_SERIES, PREFIX)


if __name__ == "__main__":
    regional.main(HOUSING_SERIES, PREFIX, SOURCE, DATASET)
