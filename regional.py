"""Ряды БНС из Talдау по областям и городам: общий сбор для industry, health, housing.

Правила, найденные discovery-прогонами 21-23.09.2026:

1. Ключ региона это числовой term КАТО. Имя в Talдау не уникально: один текст
   встречается под разными term, написание расходится с oblast.py («ВОСТОЧНО-» и
   «ВОСТ-», казахская «Ұ» в Улытау). Список REGIONS снят живьём и одинаков для
   классификаторов регионов 67 и 68.
2. Данные берутся полным дампом GetIndexData, один запрос на показатель.
   GetDynamics округляет значения до целых по формату разреза, параметра против
   этого нет; дамп отдаёт десятые. Сузить дамп нельзя: без полного набора разрезов
   `dics` ответ пустой.
3. "x" в значении это подавленная ячейка малой выборки, пропуск, как "-" и пусто.
4. Только уровень области (решение владельца 22.09.2026): строка берётся, если её
   terms равны [регион, *extra_terms] спецификации. Районы и компоненты агрегата
   («городская», «сельская местность») отсекаются этим же сравнением.
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
    MAX_BODY,
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

# (term id, имя как в oblast.py, slug как в oblast.py)
REGIONS: list[tuple[str, str, str]] = [
    ("247783", "Акмолинская", "aqmola"),
    ("248875", "Актюбинская", "aktobe"),
    ("250502", "Алматинская", "almaty-obl"),
    ("252311", "Атырауская", "atyrau"),
    ("264990", "Восточно-Казахстанская", "vko"),
    ("255577", "Жамбылская", "zhambyl"),
    ("253160", "Западно-Казахстанская", "zko"),
    ("256619", "Карагандинская", "karaganda"),
    ("260099", "Кызылординская", "kyzylorda"),
    ("258742", "Костанайская", "kostanay"),
    ("260907", "Мангистауская", "mangystau"),
    ("263009", "Павлодарская", "pavlodar"),
    ("264023", "Северо-Казахстанская", "sko"),
    ("20243032", "Туркестанская", "turkestan"),
    ("20242100", "Шымкент", "shymkent"),
    ("268020", "Алматы", "almaty"),
    ("268012", "Астана", "astana"),
    ("77208139", "Жетысу", "zhetysu"),
    ("77208141", "Абай", "abai"),
    ("77208140", "Улытау", "ulytau"),
]

GAP_VALUES = (None, "", "-", "x")


def dump_url(spec: dict) -> str:
    period = spec.get("period", 7)  # 7 год, 4 месяц, 8 месяц с накоплением
    return f"{TALDAU_HOST}/ru/Api/GetIndexData/{spec['index_id']}?period={period}&dics={spec['dics']}"


def page_url(spec: dict) -> str:
    return f"{TALDAU_HOST}/ru/NewIndex/GetIndex/{spec['index_id']}"


def pick_rows(payload: Any, spec: dict) -> tuple[dict[str, list[dict]], set[str]]:
    """Периоды по term региона и множество регионов с неоднозначным разрезом."""
    if not isinstance(payload, list) or not payload:
        raise SourceError(f"{spec['index_id']}: пустой или неожиданный ответ")
    tail = [int(t) for t in spec["extra_terms"]]
    rows: dict[str, list[dict]] = {}
    ambiguous: set[str] = set()
    for row in payload:
        terms = row.get("terms") if isinstance(row, dict) else None
        if not isinstance(terms, list) or terms[1:] != tail:
            continue
        key = str(terms[0])
        if key in rows:
            ambiguous.add(key)
        periods = row.get("periods")
        rows[key] = periods if isinstance(periods, list) else []
    return rows, ambiguous


def parse_periods(periods: list[dict], index_id: int, freq: str = "A") -> list[Obs]:
    """Дата Talдау это последний день периода, «31.08.2026»: год даёт «2026», месяц «2026-08»."""
    obs: list[Obs] = []
    for period in periods:
        raw_date, raw = period.get("date"), period.get("value")
        if raw in GAP_VALUES:
            continue
        parts = raw_date.split(".") if isinstance(raw_date, str) else []
        if len(parts) != 3 or (freq == "A" and parts[:2] != ["31", "12"]):
            raise SourceError(f"{index_id}: неожиданная дата {raw_date!r}")
        stamp = parts[2] if freq == "A" else f"{parts[2]}-{parts[1]}"
        try:
            obs.append(Obs(date=stamp, value=float(str(raw).replace(",", "."))))
        except ValueError as exc:
            raise SourceError(f"{index_id}: некорректное значение {raw!r}") from exc
    obs.sort(key=lambda item: item.date)
    return obs


def places_of(spec: dict) -> list[tuple[str, str, str]]:
    return spec.get("places", REGIONS)


def build(
    specs: list[dict],
    prefix: str,
    source: str,
    dataset: Path,
    today: date | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    """Каждый показатель по своим местам (по умолчанию 20 областей). Сбой показателя
    или одного места оставляет прошлый валидный срез только для него."""
    previous = load_previous(dataset)
    result: list[dict[str, Any]] = []
    issues: list[str] = []
    # Несколько спецификаций читают один дамп (индекс цен на жильё 7 МБ): качаем один раз.
    dumps: dict[str, Any] = {}

    def fallback(series_id: str, reason: str) -> None:
        issues.append(f"{series_id}: {reason}")
        old = previous.get(series_id)
        if old:
            result.append({**old, "stale": True, "note": reason})

    for spec in specs:
        url = dump_url(spec)
        try:
            if url not in dumps:
                dumps[url] = fetcher(
                    url,
                    raw_name=f"{prefix}_{spec['series_key']}.json",
                    headers=TALDAU_HEADERS,
                    max_body=spec.get("max_body", MAX_BODY),
                )
            rows, ambiguous = pick_rows(dumps[url], spec)
        except SourceError as exc:
            for _term, _name, slug in places_of(spec):
                fallback(f"{prefix}.{spec['series_key']}.{slug}", str(exc))
            continue
        freq = spec.get("freq", "A")
        for term, _name, slug in places_of(spec):
            series_id = f"{prefix}.{spec['series_key']}.{slug}"
            try:
                if term in ambiguous:
                    raise SourceError("место встречается в ответе дважды")
                if term not in rows:
                    raise SourceError("место не найдено в ответе")
                obs = parse_periods(rows[term], spec["index_id"], freq)
                if spec.get("keep_last"):
                    obs = obs[-spec["keep_last"]:]
                series = Series(
                    series_id=series_id,
                    name_ru=f"{spec['name_ru']}: {slug}",
                    unit=spec["unit"],
                    freq=freq,
                    source=source,
                    source_url=page_url(spec),
                    fetched_at=_now(),
                    obs=obs,
                    note="разрез Talдау",
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


def missing_series(
    data: dict[str, Any],
    specs: list[dict],
    prefix: str,
    known_gaps: frozenset = frozenset(),
) -> list[str]:
    """Ряды, пропавшие сверх известных структурных дыр источника."""
    expected = {
        f"{prefix}.{s['series_key']}.{slug}" for s in specs for _, _, slug in places_of(s)
    }
    got = {item["series_id"] for item in data["series"]}
    return sorted(expected - got - known_gaps)


def main(
    specs: list[dict],
    prefix: str,
    source: str,
    default_dataset: Path,
    known_gaps: frozenset = frozenset(),
) -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_dataset
    data = build(specs, prefix, source, dataset)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = missing_series(data, specs, prefix, known_gaps)
    if missing:
        raise SystemExit(f"потеряны ряды целиком: {', '.join(missing)}")
