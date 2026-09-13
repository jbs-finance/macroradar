"""Сборщик годового баланса энергии БНС.

Запуск: .venv/bin/python energy.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Callable

from etl import Obs, Series, SourceError, _now, fetch_json, load_previous, validate

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "energy.json"
BNS_SOURCE = "Бюро национальной статистики"

ENERGY_SERIES = [
    {
        "series_id": "kz.energy.intensity",
        "name_ru": "Энергоёмкость ВВП",
        "unit": "т н. э. на 1 000 USD ППС",
        "url": "https://stat.gov.kz/api/iblock/element/45233/json/file/en/",
        "terms": ["REPUBLIC OF KAZAKHSTAN"],
        "min": 0,
        "max": 10,
    },
    {
        "series_id": "kz.energy.primary_consumption",
        "name_ru": "Потребление первичной энергии",
        "unit": "тыс. т н. э.",
        "url": "https://stat.gov.kz/api/iblock/element/168581/json/file/en/",
        "terms": ["REPUBLIC OF KAZAKHSTAN", "Total"],
        "min": 1,
        "max": 1_000_000,
    },
    {
        "series_id": "kz.energy.final_consumption",
        "name_ru": "Конечное потребление энергии",
        "unit": "тыс. т н. э.",
        "url": "https://stat.gov.kz/api/iblock/element/45240/json/file/en/",
        "terms": ["REPUBLIC OF KAZAKHSTAN", "Total"],
        "min": 1,
        "max": 1_000_000,
    },
    {
        "series_id": "kz.energy.renewable_share",
        "name_ru": "Доля возобновляемых источников энергии",
        "unit": "%",
        "url": "https://stat.gov.kz/api/iblock/element/45251/json/file/en/",
        "terms": ["REPUBLIC OF KAZAKHSTAN"],
        "min": 0,
        "max": 100,
    },
]


def parse_national_series(payload: Any, spec: dict[str, Any]) -> list[Obs]:
    """Разбирает только национальный разрез, не подменяя его другим сегментом."""
    if not isinstance(payload, list):
        raise SourceError("неожиданная структура JSON")
    rows = [
        row
        for row in payload
        if isinstance(row, dict) and row.get("termNames") == spec["terms"]
    ]
    if len(rows) != 1:
        raise SourceError("национальный разрез не найден или неоднозначен")
    periods = rows[0].get("periods")
    if not isinstance(periods, list) or not periods:
        raise SourceError("периоды не найдены")

    obs: list[Obs] = []
    for period in periods:
        if not isinstance(period, dict):
            raise SourceError("некорректный период")
        raw_date, raw_value = period.get("date"), period.get("value")
        if not isinstance(raw_date, str) or not isinstance(raw_value, str):
            raise SourceError("некорректные дата или значение")
        try:
            period_date = date.fromisoformat("-".join(reversed(raw_date.split("."))))
            value = float(raw_value.replace(",", ".").replace(" ", ""))
        except ValueError as exc:
            raise SourceError("некорректные дата или значение") from exc
        if period_date.month != 12 or period_date.day != 31:
            raise SourceError("годовой период должен оканчиваться 31 декабря")
        obs.append(Obs(date=str(period_date.year), value=value))
    obs.sort(key=lambda item: item.date)
    return obs


def fetch_energy(spec: dict[str, Any], fetcher: Callable[..., Any] = fetch_json) -> Series:
    payload = fetcher(spec["url"], raw_name=f"energy_{spec['series_id']}.json")
    return Series(
        series_id=spec["series_id"],
        name_ru=spec["name_ru"],
        unit=spec["unit"],
        freq="A",
        source=BNS_SOURCE,
        source_url=spec["url"],
        fetched_at=_now(),
        obs=parse_national_series(payload, spec),
        note="национальный разрез БНС",
    )


def build(
    dataset: Path = DATASET,
    today: date | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    """Собирает все четыре ряда, сохраняя прошлый валидный срез при сбое."""
    previous = load_previous(dataset)
    result: list[dict[str, Any]] = []
    issues: list[str] = []
    for spec in ENERGY_SERIES:
        try:
            series = fetch_energy(spec, fetcher)
            problems = validate(series, spec, today)
            if problems:
                raise SourceError("; ".join(problems))
        except SourceError as exc:
            reason = str(exc)
            issues.append(f"{spec['series_id']}: {reason}")
            old = previous.get(spec["series_id"])
            if old:
                stale = dict(old)
                stale["stale"] = True
                stale["note"] = reason
                result.append(stale)
            continue
        result.append(asdict(series))
    result.sort(key=lambda item: item["series_id"])
    return {"generated_at": _now(), "series": result, "issues": issues}


def main() -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DATASET
    data = build(dataset)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = sorted({item["series_id"] for item in ENERGY_SERIES} - {item["series_id"] for item in data["series"]})
    if missing:
        raise SystemExit(f"потеряны ряды целиком: {', '.join(missing)}")


if __name__ == "__main__":
    main()
