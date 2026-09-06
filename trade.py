"""Внешняя торговля Казахстана: ряды World Bank плюс структура из UN Comtrade.

Разделение источников продиктовано их поведением, а не удобством. World Bank отдаёт
весь временной ряд одним запросом и не ограничивает частоту, поэтому объёмы торговли
и прямые инвестиции берутся там. Comtrade в открытом режиме отвечает 429 уже на
третьем запросе подряд, поэтому он тратится только на то, чего нет больше нигде:
разбивку по странам-партнёрам и товарным группам. Эти срезы кэшируются на неделю.

Запуск: .venv/bin/python trade.py out/trade.json
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from etl import (
    MAX_BODY,
    RAW,
    UA,
    Obs,
    Series,
    SourceError,
    _now,
    fetch,
    fetch_worldbank,
    validate,
)

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / "out" / "trade.json"

COMTRADE_BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_PARTNERS = (
    "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
)
KAZAKHSTAN = 398
WORLD = 0
# Открытый Comtrade отдаёт 429 при частых запросах, поэтому срез живёт неделю:
# годовая статистика за это время не меняется.
BREAKDOWN_MAX_AGE_DAYS = 7
TOP_N = 10

TRADE_WB_SERIES = [
    {
        "series_id": "kz.exports.usd",
        "indicator": "NE.EXP.GNFS.CD",
        "name_ru": "Экспорт товаров и услуг",
        "unit": "млрд USD",
        "scale": 1e-9,
        "min": 1,
        "max": 500,
    },
    {
        "series_id": "kz.imports.usd",
        "indicator": "NE.IMP.GNFS.CD",
        "name_ru": "Импорт товаров и услуг",
        "unit": "млрд USD",
        "scale": 1e-9,
        "min": 1,
        "max": 500,
    },
    {
        "series_id": "kz.fdi.usd",
        "indicator": "BX.KLT.DINV.CD.WD",
        "name_ru": "Прямые иностранные инвестиции",
        "unit": "млрд USD",
        "scale": 1e-9,
        "min": -50,
        "max": 100,
    },
    {
        "series_id": "kz.trade.openness",
        "indicator": "NE.TRD.GNFS.ZS",
        "name_ru": "Открытость экономики",
        "unit": "% ВВП",
        "scale": 1,
        "min": 5,
        "max": 200,
    },
]

# Русские названия для стран, реально встречающихся в первой десятке партнёров.
# Comtrade отдаёт partnerDesc пустым, поэтому код, которого здесь нет, ищется в
# справочнике самого Comtrade и остаётся на английском: это честнее выдуманного
# перевода. Голый номер на страницу не попадает вовсе.
PARTNER_RU = {
    156: "Китай",
    643: "Россия",
    380: "Италия",
    528: "Нидерланды",
    792: "Турция",
    860: "Узбекистан",
    417: "Киргизия",
    804: "Украина",
    276: "Германия",
    724: "Испания",
    250: "Франция",
    251: "Франция",  # Comtrade кодирует Францию как 251, включая заморские регионы
    826: "Великобритания",
    840: "США",
    842: "США",  # Comtrade кодирует США как 842, включая заморские территории
    699: "Индия",
    579: "Норвегия",
    711: "ЮАР",
    410: "Республика Корея",
    392: "Япония",
    356: "Индия",
    784: "ОАЭ",
    616: "Польша",
    112: "Беларусь",
    795: "Туркменистан",
    762: "Таджикистан",
    31: "Азербайджан",
    268: "Грузия",
    51: "Армения",
    364: "Иран",
    203: "Чехия",
    246: "Финляндия",
    100: "Болгария",
    642: "Румыния",
    348: "Венгрия",
    703: "Словакия",
    40: "Австрия",
    56: "Бельгия",
    757: "Швейцария",
    752: "Швеция",
    578: "Норвегия",
    300: "Греция",
    620: "Португалия",
    191: "Хорватия",
    705: "Словения",
    233: "Эстония",
    428: "Латвия",
    440: "Литва",
    496: "Монголия",
    704: "Вьетнам",
    458: "Малайзия",
    702: "Сингапур",
    764: "Таиланд",
    360: "Индонезия",
    586: "Пакистан",
    368: "Ирак",
    682: "Саудовская Аравия",
    818: "Египет",
    710: "ЮАР",
    124: "Канада",
    484: "Мексика",
    76: "Бразилия",
    32: "Аргентина",
    36: "Австралия",
    554: "Новая Зеландия",
    792000: "Турция",
}

# Разделы товарной номенклатуры HS на уровне двух знаков, встречающиеся в экспорте
# и импорте Казахстана. Незнакомый код показывается как есть, без выдумывания.
HS2_RU = {
    "27": "Минеральное топливо, нефть",
    "26": "Руды, шлак, зола",
    "28": "Продукты неорганической химии",
    "72": "Чёрные металлы",
    "74": "Медь и изделия из неё",
    "71": "Драгоценные металлы и камни",
    "10": "Злаки",
    "12": "Масличные семена",
    "84": "Машины и оборудование",
    "85": "Электрические машины",
    "87": "Транспортные средства",
    "39": "Пластмассы",
    "31": "Удобрения",
    "76": "Алюминий",
    "79": "Цинк",
    "81": "Прочие недрагоценные металлы",
    "25": "Соль, сера, цемент",
    "15": "Жиры и масла",
    "23": "Остатки пищевой промышленности",
    "11": "Продукция мукомольной промышленности",
    "73": "Изделия из чёрных металлов",
    "30": "Фармацевтическая продукция",
    "38": "Прочие химические продукты",
    "90": "Оптические и медицинские приборы",
    "94": "Мебель",
    "48": "Бумага и картон",
    "40": "Каучук и резина",
    "22": "Алкогольные и безалкогольные напитки",
    "04": "Молочная продукция",
    "02": "Мясо",
}


def comtrade(params: dict, raw_name: str, tries: int = 4) -> list[dict]:
    """Запрос к открытому Comtrade с бэкоффом на 429.

    Лимит здесь не аварийная ситуация, а штатное поведение источника, поэтому
    ожидание длинное: лучше подождать полминуты, чем остаться без среза.
    """
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{COMTRADE_BASE}?{query}"
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read(MAX_BODY)
            RAW.mkdir(parents=True, exist_ok=True)
            (RAW / raw_name).write_bytes(body)
            payload = json.loads(body)
            # Пустой список это «за год ещё не опубликовано», и он штатный. Смена
            # конверта ответа даёт такой же пустой список, поэтому отсутствие
            # ключа data и чужая форма ответа разбираются отдельно и явно.
            if not isinstance(payload, dict) or "data" not in payload:
                raise SourceError(f"{url}: в ответе нет поля data, схема источника")
            rows = payload["data"]
            if not isinstance(rows, list):
                raise SourceError(f"{url}: поле data не список, схема источника")
            return rows
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code != 429:
                raise SourceError(f"{url}: {exc}") from exc
            time.sleep(25 * (attempt + 1))
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last = exc
            time.sleep(10 * (attempt + 1))
    raise SourceError(f"{url}: {last}")


_partner_names: dict[int, str] | None = None


def partner_names() -> dict[int, str]:
    """Справочник кодов партнёров Comtrade, английские названия.

    Русского словаря на всех не напасёшься, а голый номер на странице читается как
    сбой: Франция в статистике проходит кодом 251, США кодом 842, и без справочника
    они попадали в топ-10 как «код 251». Тянется один раз за прогон, недоступность
    справочника не срывает срез."""
    global _partner_names
    if _partner_names is not None:
        return _partner_names
    _partner_names = {}
    try:
        payload = json.loads(fetch(COMTRADE_PARTNERS, "comtrade_partners.json"))
    except (SourceError, json.JSONDecodeError):
        return _partner_names
    rows = payload.get("results") if isinstance(payload, dict) else payload
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            code = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        name = (row.get("text") or "").strip()
        if name:
            _partner_names[code] = name
    return _partner_names


def top_partners(
    rows: list[dict],
    top_n: int = TOP_N,
    names: dict[int, str] | None = None,
    dropped: list[str] | None = None,
) -> list[dict]:
    """Первые партнёры по стоимости. Строка «весь мир» из рейтинга исключается,
    иначе она займёт первое место и раздавит масштаб остальных.

    Позиция, для которой имя страны так и не нашлось, не публикуется: «код 251» в
    первой десятке партнёров это не данные, а видимость данных."""
    names = names or {}
    items = []
    for row in rows:
        code = row.get("partnerCode")
        value = row.get("primaryValue")
        if code in (None, WORLD) or not value:
            continue
        label = PARTNER_RU.get(code) or names.get(code) or row.get("partnerDesc")
        if not label:
            if dropped is not None:
                dropped.append(f"{code} ({value / 1e9:.2f} млрд USD)")
            continue
        items.append({"label": label, "value": value / 1e9})
    items.sort(key=lambda i: -i["value"])
    return items[:top_n]


def shape_partners(rows: list[dict], dropped: list[str] | None = None) -> list[dict]:
    """Топ партнёров со справочником кодов: справочник тянется лениво, только когда
    срез действительно качается, а не берётся из кэша."""
    return top_partners(rows, names=partner_names(), dropped=dropped)


def top_commodities(
    rows: list[dict], top_n: int = TOP_N, dropped: list[str] | None = None
) -> list[dict]:
    items = []
    for row in rows:
        code = str(row.get("cmdCode") or "")
        value = row.get("primaryValue")
        if not code or code == "TOTAL" or not value:
            continue
        items.append(
            {
                "label": HS2_RU.get(code)
                or (row.get("cmdDesc") or f"группа HS {code}"),
                "value": value / 1e9,
            }
        )
    items.sort(key=lambda i: -i["value"])
    return items[:top_n]


def trade_balance(exports: Series, imports: Series) -> Series:
    """Сальдо считается только по годам, где есть обе стороны."""
    by_year = {o.date: o.value for o in imports.obs}
    obs = [
        Obs(date=o.date, value=o.value - by_year[o.date])
        for o in exports.obs
        if o.date in by_year
    ]
    return Series(
        series_id="kz.trade.balance",
        name_ru="Сальдо торгового баланса",
        unit="млрд USD",
        freq="A",
        source="World Bank",
        source_url=exports.source_url,
        fetched_at=_now(),
        obs=obs,
        note="расчёт: экспорт минус импорт товаров и услуг",
    )


def cached_breakdown(previous: dict, key: str) -> dict | None:
    """Свежий срез из прошлого снапшота, если он ещё не протух."""
    old = previous.get(key)
    if not old:
        return None
    try:
        fetched = datetime.fromisoformat(old["fetched_at"])
    except (KeyError, ValueError):
        return None
    age = datetime.now(timezone.utc) - fetched
    if age >= timedelta(days=BREAKDOWN_MAX_AGE_DAYS):
        return None
    # Срез с неопознанным кодом партнёра однажды уже уехал на страницу и жил там
    # месяцами: год не менялся, кэш считался годным, и «код 251» переписывался из
    # снапшота в снапшот. Такой срез берём заново, справочник кодов мог появиться.
    items = old.get("items") or []
    if any(
        isinstance(i, dict) and str(i.get("label", "")).startswith("код ")
        for i in items
    ):
        return None
    return old


def latest_year(series: list[Series], today: date | None = None) -> int:
    years = [int(s.obs[-1].date) for s in series if s.obs]
    return max(years) if years else (today or date.today()).year - 1


def build(dataset: Path, today: date | None = None) -> dict:
    # Дата фиксируется один раз на прогон: иначе сборка, пересекающая полночь,
    # сверяет свежесть разных рядов с разными «сегодня».
    today = today or date.today()
    previous_series: dict[str, dict] = {}
    previous_breakdowns: dict[str, dict] = {}
    if dataset.exists():
        try:
            old = json.loads(dataset.read_text(encoding="utf-8"))
            previous_series = {s["series_id"]: s for s in old.get("series", [])}
            previous_breakdowns = {b["id"]: b for b in old.get("breakdowns", [])}
        except json.JSONDecodeError:
            pass

    result: list[dict] = []
    issues: list[str] = []
    fetched: dict[str, Series] = {}

    def keep_previous(series_id: str, reason: str) -> None:
        issues.append(f"{series_id}: {reason}")
        old = previous_series.get(series_id)
        if old:
            old = dict(old)
            old["stale"] = True
            old["note"] = reason
            result.append(old)

    for spec in TRADE_WB_SERIES:
        try:
            series = fetch_worldbank(spec)
        except SourceError as exc:
            keep_previous(spec["series_id"], f"источник недоступен ({exc})")
            continue
        problems = validate(series, spec, today)
        if problems:
            keep_previous(spec["series_id"], "; ".join(problems))
            continue
        fetched[spec["series_id"]] = series
        result.append(asdict(series))

    if "kz.exports.usd" in fetched and "kz.imports.usd" in fetched:
        balance = trade_balance(fetched["kz.exports.usd"], fetched["kz.imports.usd"])
        if balance.obs:
            result.append(asdict(balance))
        else:
            issues.append("kz.trade.balance: нет лет, где известны обе стороны")

    year = latest_year(list(fetched.values()), today)
    breakdowns: list[dict] = []
    requests = [
        (
            "exports.partners",
            "Экспорт по странам",
            {"flowCode": "X", "cmdCode": "TOTAL"},
            shape_partners,
        ),
        (
            "imports.partners",
            "Импорт по странам",
            {"flowCode": "M", "cmdCode": "TOTAL"},
            shape_partners,
        ),
        (
            "exports.commodities",
            "Экспорт по товарным группам",
            {"flowCode": "X", "cmdCode": "AG2", "partnerCode": WORLD},
            top_commodities,
        ),
    ]

    for key, title, extra, shaper in requests:
        cached = cached_breakdown(previous_breakdowns, key)
        if cached and cached.get("year") == year:
            breakdowns.append(cached)
            continue
        # Год берётся по самому свежему ряду, но Comtrade может отставать на год.
        # Пустой ответ это не сбой, а «ещё не опубликовано», поэтому отходим назад.
        params = {"reporterCode": KAZAKHSTAN, "period": year, **extra}
        dropped: list[str] = []
        try:
            items, params = [], params
            for candidate in (year, year - 1):
                params = {"reporterCode": KAZAKHSTAN, "period": candidate, **extra}
                dropped = []
                items = shaper(
                    comtrade(params, f"comtrade_{key}_{candidate}.json"), dropped=dropped
                )
                if items:
                    year_used = candidate
                    break
            if not items:
                raise SourceError("пустой срез")
        except SourceError as exc:
            issues.append(f"{key}: {exc}")
            if cached or previous_breakdowns.get(key):
                stale = dict(cached or previous_breakdowns[key])
                stale["stale"] = True
                breakdowns.append(stale)
            continue
        breakdowns.append(
            {
                "id": key,
                "name_ru": title,
                "unit": "млрд USD",
                "year": year_used,
                "source": "UN Comtrade",
                "source_url": f"{COMTRADE_BASE}?{'&'.join(f'{k}={v}' for k, v in params.items())}",
                "fetched_at": _now(),
                "items": items,
                "stale": False,
            }
        )
        if dropped:
            issues.append(
                f"{key}: коды партнёров не опознаны, позиции не опубликованы: "
                + ", ".join(dropped)
            )

    result.sort(key=lambda s: s["series_id"])
    return {
        "generated_at": _now(),
        "series": result,
        "breakdowns": breakdowns,
        "issues": issues,
    }


def main() -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    data = build(dataset)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fresh = sum(1 for s in data["series"] if not s.get("stale"))
    print(f"Рядов свежих: {fresh}, всего: {len(data['series'])}")
    print(f"Срезов: {len(data['breakdowns'])}")
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")
    # Ряд, которого нет ни свежим, ни прошлым, потерян целиком; без единого среза
    # блок структуры торговли тоже пуст.
    lost = sorted(
        {s["series_id"] for s in TRADE_WB_SERIES} - {s["series_id"] for s in data["series"]}
    )
    if not data["breakdowns"]:
        lost.append("срезы Comtrade")
    if lost:
        raise SystemExit(f"потеряно целиком: {', '.join(lost)}")


if __name__ == "__main__":
    main()
