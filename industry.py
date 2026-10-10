"""Отраслевые ряды БНС по областям: горно-металлургический комплекс и водозабор.

Общий сбор и правила Talдау в regional.py. Здесь только выбор разрезов:

1. Индекс чёрной металлургии (701625, отрасль 3079125, «к предыдущему периоду»
   2695730). Разрез «Ковка, прессование, порошковая металлургия» не берётся: у него
   два разных term с одинаковым именем, различить их без БНС нельзя.
2. ГМК (добавлен 25.09.2026) из того же дампа 701625: горнодобывающая промышленность
   (3078703), добыча металлических руд (3078714), металлургическое производство целиком
   (3078917), благородные и цветные металлы (3078927). У каждого ряда свой список
   областей: только те, где БНС публикует его после 2023 года. Руды не добываются или
   не публикуются в восьми регионах, цветная металлургия в четырёх, горнодобыча
   Алматы обрывается на 2014 году.
3. Водозаборные сооружения (20385164) только по категории «Всего» (741917):
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


def _without(*slugs: str) -> list[tuple[str, str, str]]:
    return [place for place in regional.REGIONS if place[2] not in slugs]


# Полный дамп показателя 26 МБ на 34 011 строк (22.09.2026), общий потолок 8 МБ.
# Все ряды ГМК читают один дамп: regional.build качает его один раз.
PRODUCTION = {
    "index_id": 701625,
    "dics": "68,4303,848",
    "max_body": 40 * 1024 * 1024,
    "unit": "% к предыдущему периоду",
    "min": 0,
}
TO_PREVIOUS = 2695730

# Порядок это порядок секций на странице: от добычи к металлургии.
# Пределы max сняты с живого разброса 25.09.2026 с запасом: малая база даёт всплески.
INDUSTRY_SERIES = [
    {
        **PRODUCTION,
        "series_key": "mining",
        "extra_terms": (3078703, TO_PREVIOUS),
        "places": _without("almaty"),
        "name_ru": "Индекс производства горнодобывающей промышленности",
        "max": 1000,  # живой 9,6..344,4
    },
    {
        **PRODUCTION,
        "series_key": "metal_ores",
        "extra_terms": (3078714, TO_PREVIOUS),
        "places": _without(
            "almaty-obl", "atyrau", "zko", "mangystau", "shymkent", "almaty", "astana", "zhetysu"
        ),
        "name_ru": "Индекс добычи металлических руд",
        "max": 20000,  # живой 1,1..9 772,4
    },
    {
        **PRODUCTION,
        "series_key": "metallurgy_all",
        "extra_terms": (3078917, TO_PREVIOUS),
        "name_ru": "Индекс металлургического производства",
        "max": 5000,  # живой 8,7..3 220,9
    },
    {
        **PRODUCTION,
        "series_key": "metallurgy",
        "extra_terms": (3079125, TO_PREVIOUS),
        "name_ru": "Индекс производства чёрной металлургии",
        "max": 2000,  # живой 5..1 700 (22.09.2026)
    },
    {
        **PRODUCTION,
        "series_key": "nonferrous",
        "extra_terms": (3078927, TO_PREVIOUS),
        "places": _without("aktobe", "atyrau", "zko", "mangystau"),
        "name_ru": "Индекс производства благородных и цветных металлов",
        "max": 2000,  # живой 33,9..775
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
