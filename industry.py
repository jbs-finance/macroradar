"""Сборщик отраслевых рядов БНС по областям: металлургия и водозабор.

Discovery gate (21-22.09.2026, см. Пред-Корзину и handover) нашёл два ряда Talдау,
пригодных как первичный источник для будущего отраслевого радара, но не готовых без
доработки:

1. Индекс производства чёрной металлургии (показатель 701625, отрасль «Черная
   металлургия, кроме литья металлов», код 3079125) не показывает второй найденный
   разрез («Ковка, прессование... порошковая металлургия»): его код отрасли задвоен
   на два разных `terms` с одинаковым именем в ответе Talдау, различить их без
   очной ставки с БНС нельзя.
2. Число водозаборных сооружений (показатель 20385164) берётся только по категории
   «Всего»: «городская местность» и «сельская местность» это компоненты того же
   агрегата, а не отдельные ряды, брать их отдельно значит задвоить.

По решению владельца (22.09.2026): только уровень области, без районов и
городов районного значения. У Talдау название региона не является стабильным
ключом: одно и то же имя встречается с несколькими разными числовыми `terms` (см.
discovery gate), поэтому регионы здесь заданы явным списком term id, снятым живьём
с API и сверенным построчно с REGION_NAMES в oblast.py (имена/слаги переиспользованы
оттуда, написание Talдау местами отличается: «ВОСТОЧНО-КАЗАХСТАНСКАЯ» вместо «ВОСТ»,
кириллица «У» вместо казахской «Ұ» в Улытау и так далее).

Запуск: .venv/bin/python industry.py
"""

from __future__ import annotations

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from etl import (
    BNS_DATE_RANGE,
    MAX_BODY,
    RETRIES,
    RETRY_PAUSE,
    TALDAU_HEADERS,
    TALDAU_HOST,
    TIMEOUT,
    Obs,
    Series,
    SourceError,
    _now,
    load_previous,
    parse_bns_date,
    validate,
)

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "industry.json"
BNS_SOURCE = "Бюро национальной статистики"

# ponytail: период «Год» имел id=7 у обоих показателей на момент discovery gate
# (22.09.2026), проверено живым вызовом NewIndex/GetPeriodList. Захардкожено вместо
# запроса на каждый прогон, чтобы не удваивать число обращений к Talдау; если id
# когда-нибудь сменится, gate уронит все ряды разом (SourceError на первом же
# запросе), это будет видно сразу, не молча.
ANNUAL_PERIOD_ID = 7

# region_key: (Talдау term id, имя как на странице oblast.py, slug как в oblast.py)
# Снято живьём 21-22.09.2026 из ответов GetIndexData для показателей 701625 и
# 20385164. Все 20 регионов подтверждены в обоих показателях.
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

# Известные структурные дыры источника, не сбой сбора: подтверждено живым прогоном
# 22.09.2026, Talдау не публикует данные после 2009 года по этому региону и отрасли,
# гейт свежести (800 дней) отбрасывает точку как устаревшую на каждом прогоне. Список
# должен пустеть, если БНС когда-нибудь возобновит публикацию, а не расти: новый
# пропавший ряд обязан по-прежнему ронять прогон.
KNOWN_GAPS = frozenset({"kz.industry.metallurgy.aqmola"})

INDUSTRY_SERIES = [
    {
        "series_key": "metallurgy",
        "index_id": 701625,
        "dic_ids": "68,4303,848",
        # Черная металлургия, кроме литья металлов, плюс «отчетный период к предыдущему»
        "extra_terms": "3079125,2695730",
        "name_ru": "Индекс производства чёрной металлургии",
        "unit": "% к предыдущему периоду",
        # Малая отраслевая база в отдельных областях даёт всплески год к году, а не
        # ошибку данных: живой прогон 22.09.2026 по всем 20 регионам дал разброс
        # 5..1700 (Акмолинская, 2009 год, 1700 при базе почти с нуля). Порог взят с
        # запасом от этого диапазона, не выдуман.
        "min": 0,
        "max": 2000,
    },
    {
        "series_key": "water_intake",
        "index_id": 20385164,
        "dic_ids": "68,776",
        "extra_terms": "741917",  # категория «Всего»
        "name_ru": "Число водозаборных сооружений",
        "unit": "ед.",
        "min": 0,
        "max": 5000,
    },
]


def parse_dynamics(payload: Any, index_id: int) -> list[Obs]:
    """Как etl.parse_bns_dynamics, но дополнительно пропускает "x" (подавленная
    БНС ячейка малой выборки, см. discovery gate 21.09.2026: 198 из 2992 значений
    водозабора были именно "x", а не "-"/пусто)."""
    if not isinstance(payload, dict):
        raise SourceError(f"{index_id}: неожиданная структура ответа")
    dates, values = payload.get("dateList") or [], payload.get("valueList") or []
    if not dates or len(dates) != len(values):
        raise SourceError(f"{index_id}: пустой или несогласованный ответ")
    obs: list[Obs] = []
    for code, raw in zip(dates, values):
        if raw in (None, "", "-", "x"):
            continue
        try:
            obs.append(
                Obs(
                    date=parse_bns_date(code, "A"),
                    value=float(str(raw).replace(",", ".")),
                )
            )
        except ValueError as exc:
            raise SourceError(f"{index_id}: некорректное значение {raw!r}") from exc
    obs.sort(key=lambda item: item.date)
    return obs


def _open_session() -> tuple[http.cookiejar.CookieJar, Any]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return jar, opener


def fetch_region_dynamics(
    opener: Any, index_id: int, dic_ids: str, terms: str, raw_name: str
) -> dict:
    """Один разрез Talдау: сессия уже открыта вызывающим, здесь только запрос ряда."""
    params = {
        "dicIds": dic_ids,
        "indexId": index_id,
        "periodId": ANNUAL_PERIOD_ID,
        "terms": terms,
        "filters_dates": BNS_DATE_RANGE,
    }
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        f"{TALDAU_HOST}/ru/NewIndex/GetDynamics", data=body, headers=TALDAU_HEADERS
    )
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            return json.loads(
                opener.open(req, timeout=TIMEOUT)
                .read(MAX_BODY)
                .decode("utf-8", "ignore")
            )
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last = exc
            time.sleep(RETRY_PAUSE * (attempt + 1))
    raise SourceError(f"{raw_name}: {last}")


def default_fetcher(index_id: int, dic_ids: str, terms: str, raw_name: str) -> dict:
    """Полный цикл на один запрос. Сессия переоткрывается на каждый вызов вместо
    того, чтобы жить снаружи build(): 40 рядов в сутки, не тот объём, где разница
    заметна; если станет важно, вынести открытие сессии в build()."""
    jar, opener = _open_session()
    page_url = f"{TALDAU_HOST}/ru/NewIndex/GetIndex/{index_id}"
    try:
        opener.open(
            urllib.request.Request(page_url, headers=TALDAU_HEADERS), timeout=TIMEOUT
        ).read(MAX_BODY)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"страница показателя {index_id}: {exc}") from exc
    return fetch_region_dynamics(opener, index_id, dic_ids, terms, raw_name)


def fetch_industry(
    spec: dict[str, Any],
    region_term: str,
    region_slug: str,
    fetcher: Callable[..., Any] = default_fetcher,
) -> Series:
    terms = f"{region_term},{spec['extra_terms']}"
    raw_name = f"industry_{spec['series_key']}_{region_slug}.json"
    payload = fetcher(spec["index_id"], spec["dic_ids"], terms, raw_name)
    return Series(
        series_id=f"kz.industry.{spec['series_key']}.{region_slug}",
        name_ru=f"{spec['name_ru']}: {region_slug}",
        unit=spec["unit"],
        freq="A",
        source=BNS_SOURCE,
        source_url=f"{TALDAU_HOST}/ru/NewIndex/GetIndex/{spec['index_id']}",
        fetched_at=_now(),
        obs=parse_dynamics(payload, spec["index_id"]),
        note="область, разрез Talдау",
    )


def build(
    dataset: Path = DATASET,
    today: date | None = None,
    fetcher: Callable[..., Any] = default_fetcher,
) -> dict[str, Any]:
    """Собирает 20 областей на 2 показателя, сохраняя прошлый валидный срез при
    сбое отдельного ряда (не всего прогона: одна недоступная область не должна
    ронять остальные девятнадцать)."""
    previous = load_previous(dataset)
    result: list[dict[str, Any]] = []
    issues: list[str] = []
    for spec in INDUSTRY_SERIES:
        for region_term, _name_ru, region_slug in REGIONS:
            series_id = f"kz.industry.{spec['series_key']}.{region_slug}"
            try:
                series = fetch_industry(spec, region_term, region_slug, fetcher)
                problems = validate(series, spec, today)
                if problems:
                    raise SourceError("; ".join(problems))
            except SourceError as exc:
                reason = str(exc)
                issues.append(f"{series_id}: {reason}")
                old = previous.get(series_id)
                if old:
                    stale = dict(old)
                    stale["stale"] = True
                    stale["note"] = reason
                    result.append(stale)
                continue
            result.append(asdict(series))
    result.sort(key=lambda item: item["series_id"])
    return {"generated_at": _now(), "series": result, "issues": issues}


def missing_series(data: dict[str, Any]) -> list[str]:
    """Ряды, пропавшие сверх известных структурных дыр источника (KNOWN_GAPS)."""
    expected = {
        f"kz.industry.{spec['series_key']}.{slug}"
        for spec in INDUSTRY_SERIES
        for _, _, slug in REGIONS
    }
    got = {item["series_id"] for item in data["series"]}
    return sorted(expected - got - KNOWN_GAPS)


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
