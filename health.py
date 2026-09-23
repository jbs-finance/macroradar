"""Сборщик рядов здравоохранения по областям: койки и врачи на 10 000 населения.

Discovery gate 23.09.2026. Оба показателя это административные данные Минздрава,
которые БНС выкладывает в Talдау (классификатор регионов 67, без районов). Последний
год в источнике 2023: лаг публикации около двух лет, отдельного бюллетеня БНС по
койкам и врачам нет. Поэтому у рядов свой предел свежести `max_age_days`, а страница
показывает год наблюдения и бейдж устаревания.

Объём оказанных медуслуг (показатель 704347) отброшен: годовой ряд за 2023 год
(941 млрд) меньше одного I квартала 2023 года (756 млрд), квартальный в Talдау
обрывается на IV квартале 2024 при выпущенных бюллетенях по II квартал 2026.

Данные берутся полным дампом `GetIndexData` одним запросом на показатель: он
отдаёт значения с десятыми, а `GetDynamics` округляет их до целых по формату разреза.

Запуск: .venv/bin/python health.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from etl import (
    TALDAU_HEADERS,
    TALDAU_HOST,
    Obs,
    Series,
    SourceError,
    _now,
    fetch_json,
    load_previous,
    validate,
)
from industry import REGIONS

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "health.json"
SOURCE = "Бюро национальной статистики (данные Минздрава РК)"

# 2023-12-31 плюс 1200 дней это 14.04.2027. На 23.09.2026 возраст последней точки
# 997 дней. Если БНС не выложит 2024 год до середины апреля 2027, сбор упадёт на
# гейте и потребует решения, а не продолжит молча показывать 2023 год.
HEALTH_MAX_AGE_DAYS = 1200

HEALTH_SERIES = [
    {
        "series_key": "beds_per_10k",
        "index_id": 704311,
        "name_ru": "Больничные койки на 10 000 населения",
        "unit": "коек на 10 000 человек",
        "min": 0,
        "max": 500,
        "max_age_days": HEALTH_MAX_AGE_DAYS,
    },
    {
        "series_key": "doctors_per_10k",
        "index_id": 704316,
        "name_ru": "Врачи на 10 000 населения",
        "unit": "врачей на 10 000 человек",
        "min": 0,
        "max": 500,
        "max_age_days": HEALTH_MAX_AGE_DAYS,
    },
]


def dump_url(index_id: int) -> str:
    return f"{TALDAU_HOST}/ru/Api/GetIndexData/{index_id}?period=7&dics=67"


def page_url(index_id: int) -> str:
    return f"{TALDAU_HOST}/ru/NewIndex/GetIndex/{index_id}"


def region_rows(payload: Any, index_id: int) -> dict[str, list[dict]]:
    """Ряды по term id региона. Строка с одним термом это чистый разрез по региону."""
    if not isinstance(payload, list) or not payload:
        raise SourceError(f"{index_id}: пустой или неожиданный ответ")
    rows: dict[str, list[dict]] = {}
    for row in payload:
        terms = row.get("terms") if isinstance(row, dict) else None
        if not isinstance(terms, list) or len(terms) != 1:
            continue
        periods = row.get("periods")
        if isinstance(periods, list):
            rows[str(terms[0])] = periods
    return rows


def parse_periods(periods: list[dict], index_id: int) -> list[Obs]:
    obs: list[Obs] = []
    for period in periods:
        raw_date, raw = period.get("date"), period.get("value")
        if raw in (None, "", "-", "x"):
            continue
        if not isinstance(raw_date, str) or not raw_date.endswith(
            "12." + raw_date[-4:]
        ):
            raise SourceError(f"{index_id}: неожиданная дата {raw_date!r}")
        try:
            obs.append(Obs(date=raw_date[-4:], value=float(str(raw).replace(",", "."))))
        except ValueError as exc:
            raise SourceError(f"{index_id}: некорректное значение {raw!r}") from exc
    obs.sort(key=lambda item: item.date)
    return obs


def build(
    dataset: Path = DATASET,
    today: date | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    """20 областей на 2 показателя. Сбой одного показателя или одной области
    оставляет прошлый валидный срез только для неё, остальные собираются."""
    previous = load_previous(dataset)
    result: list[dict[str, Any]] = []
    issues: list[str] = []

    def fallback(series_id: str, reason: str) -> None:
        issues.append(f"{series_id}: {reason}")
        old = previous.get(series_id)
        if old:
            stale = dict(old)
            stale["stale"] = True
            stale["note"] = reason
            result.append(stale)

    for spec in HEALTH_SERIES:
        try:
            payload = fetcher(
                dump_url(spec["index_id"]),
                raw_name=f"health_{spec['series_key']}.json",
                headers=TALDAU_HEADERS,
            )
            rows = region_rows(payload, spec["index_id"])
        except SourceError as exc:
            for _term, _name, slug in REGIONS:
                fallback(f"kz.health.{spec['series_key']}.{slug}", str(exc))
            continue
        for term, _name, slug in REGIONS:
            series_id = f"kz.health.{spec['series_key']}.{slug}"
            try:
                if term not in rows:
                    raise SourceError("регион не найден в ответе")
                series = Series(
                    series_id=series_id,
                    name_ru=f"{spec['name_ru']}: {slug}",
                    unit=spec["unit"],
                    freq="A",
                    source=SOURCE,
                    source_url=page_url(spec["index_id"]),
                    fetched_at=_now(),
                    obs=parse_periods(rows[term], spec["index_id"]),
                    note="область, разрез Talдау",
                )
                problems = validate(series, spec, today)
                if problems:
                    raise SourceError("; ".join(problems))
            except SourceError as exc:
                fallback(series_id, str(exc))
                continue
            result.append(asdict(series))
    result.sort(key=lambda item: item["series_id"])
    return {"generated_at": _now(), "series": result, "issues": issues}


def missing_series(data: dict[str, Any]) -> list[str]:
    expected = {
        f"kz.health.{spec['series_key']}.{slug}"
        for spec in HEALTH_SERIES
        for _, _, slug in REGIONS
    }
    return sorted(expected - {item["series_id"] for item in data["series"]})


def main() -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DATASET
    data = build(dataset)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = missing_series(data)
    if missing:
        raise SystemExit(f"потеряны ряды целиком: {', '.join(missing)}")


if __name__ == "__main__":
    main()
