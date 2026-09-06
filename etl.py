"""ETL макропоказателей Казахстана: World Bank + официальные курсы НБРК.

Выход: out/pulse.json в каноническом формате ряда. Сырые ответы источников
складываются в raw/ и являются доказательной базой для любой цифры на странице.

Запуск: .venv/bin/python etl.py
"""

from __future__ import annotations

import http.cookiejar
import json
import math
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RAW = HERE / "raw"
DATASET = OUT / "pulse.json"

UA = {"User-Agent": "jbs-kz-data/1.0 (+https://jbs.finance)"}
# Taldau отвечает только на запросы, которые выглядят как из его же интерфейса.
TALDAU_HEADERS = {**UA, "X-Requested-With": "XMLHttpRequest"}
TIMEOUT = 45
RETRIES = 3
RETRY_PAUSE = 1.5  # база растущей паузы: 1.5, 3, 6 секунд
# Потолок ответа: разбор XML стандартным парсером, ограничение размера закрывает
# раздувание сущностями, если источник когда-нибудь отдаст не то, что обещает.
MAX_BODY = 8 * 1024 * 1024

WB_HOST = "https://api.worldbank.org/v2"
NBK_HOST = "https://nationalbank.kz"

# Реестр рядов. min/max это гейт правдоподобия, а не прогноз: значение за границей
# означает, что источник сменил единицу измерения или отдал мусор.
WB_SERIES = [
    {
        "series_id": "kz.gdp.usd",
        "indicator": "NY.GDP.MKTP.CD",
        "name_ru": "ВВП",
        "unit": "млрд USD",
        "scale": 1e-9,
        "min": 10,
        "max": 2000,
    },
    {
        "series_id": "kz.gdp.pc.usd",
        "indicator": "NY.GDP.PCAP.CD",
        "name_ru": "ВВП на душу населения",
        "unit": "USD",
        "scale": 1,
        "min": 500,
        "max": 100000,
    },
    {
        "series_id": "kz.cpi.yoy",
        "indicator": "FP.CPI.TOTL.ZG",
        "name_ru": "Инфляция, ИПЦ",
        "unit": "% к прошлому году",
        "scale": 1,
        "min": -10,
        "max": 60,
    },
    {
        "series_id": "kz.gdp.growth",
        "indicator": "NY.GDP.MKTP.KD.ZG",
        "name_ru": "Рост ВВП, реальный",
        "unit": "% за год",
        "scale": 1,
        "min": -20,
        "max": 20,
    },
    {
        "series_id": "kz.unemployment",
        "indicator": "SL.UEM.TOTL.ZS",
        "name_ru": "Безработица",
        "unit": "% рабочей силы",
        "scale": 1,
        "min": 0,
        "max": 40,
    },
    {
        "series_id": "kz.population",
        "indicator": "SP.POP.TOTL",
        "name_ru": "Население",
        "unit": "млн человек",
        "scale": 1e-6,
        "min": 5,
        "max": 40,
    },
]

FX_SERIES = [
    {
        "series_id": "kz.fx.usd",
        "code": "USD",
        "name_ru": "Курс USD",
        "min": 100,
        "max": 2000,
    },
    {
        "series_id": "kz.fx.eur",
        "code": "EUR",
        "name_ru": "Курс EUR",
        "min": 100,
        "max": 2000,
    },
    {
        "series_id": "kz.fx.rub",
        "code": "RUB",
        "name_ru": "Курс RUB",
        "min": 1,
        "max": 50,
    },
    {
        "series_id": "kz.fx.cny",
        "code": "CNY",
        "name_ru": "Курс CNY",
        "min": 10,
        "max": 300,
    },
]

FX_MONTHS = 36
# Доля собранных точек, ниже которой ряд подписывается как неполный, и доля, ниже
# которой он не публикуется вовсе.
FX_FULL_COVERAGE = 0.9
FX_MIN_COVERAGE = 0.5
KEEP_LAST_YEARS = 20

# Бюро национальной статистики через Taldau. Открытого API у БНС нет, работает
# внутренняя цепочка интерфейса: страница показателя даёт сессию, GetPeriodList даёт
# периодичность, GetSegmentList даёт разрез по умолчанию, GetDynamics отдаёт ряд.
#
# Ограничение источника: GetDynamics округляет значения до целых. Для тенге и людей
# это незаметно, для процентов губительно (уровень безработицы приходит как "5",
# ИПЦ как "101"), поэтому проценты берём у World Bank, а у БНС только абсолютные
# величины. Разрез берётся тот, что Taldau предлагает по умолчанию: дерево терминов
# (getTermBranchEx) на стороне БНС отвечает ошибкой 500 даже на запрос их же
# интерфейса, выбрать другой срез программно нельзя.
BNS_SERIES = [
    {
        "series_id": "kz.gdp.kzt",
        "index_id": 2709379,
        "period": "Год",
        "name_ru": "ВВП методом производства",
        "unit": "трлн тенге",
        "scale": 1e-12,
        "min": 1,
        "max": 1000,
    },
    {
        "series_id": "kz.wage.avg",
        "index_id": 702972,
        "period": "Квартал",
        "name_ru": "Среднемесячная зарплата",
        "unit": "тенге",
        "scale": 1,
        "min": 10000,
        "max": 5000000,
    },
    {
        "series_id": "kz.population.bns",
        "index_id": 703834,
        "period": "Год",
        "name_ru": "Население, среднегодовое",
        "unit": "млн человек",
        "scale": 1e-6,
        "min": 5,
        "max": 40,
    },
]

TALDAU_HOST = "https://taldau.stat.gov.kz"
# Заведомо широкий диапазон: Taldau сам обрезает его по доступным данным, поэтому
# новые периоды подхватываются без правки кода.
BNS_DATE_RANGE = "011990,122035"


@dataclass
class Obs:
    date: str
    value: float


@dataclass
class Series:
    series_id: str
    name_ru: str
    unit: str
    freq: str  # A годовой, D дневной срез
    source: str
    source_url: str
    fetched_at: str
    obs: list[Obs] = field(default_factory=list)
    stale: bool = False
    note: str = ""


class SourceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def retriable(exc: Exception) -> bool:
    """Стоит ли повторять запрос: 404 и 400 повтором не лечатся, 429 и 5xx лечатся."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    return True


def backoff(attempt: int) -> None:
    time.sleep(RETRY_PAUSE * 2**attempt)


def fetch(url: str, raw_name: str) -> bytes:
    """GET с ретраями. Сырой ответ кладётся в raw/ до любого разбора."""
    ctx = ssl.create_default_context()
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                body = resp.read(MAX_BODY)
            RAW.mkdir(parents=True, exist_ok=True)
            (RAW / raw_name).write_bytes(body)
            return body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if not retriable(exc) or attempt == RETRIES - 1:
                break
            backoff(attempt)
    raise SourceError(f"{url}: {last}")


def fetch_json(
    url: str,
    raw_name: str | None = None,
    timeout: int = TIMEOUT,
    retries: int = RETRIES,
    headers: dict | None = None,
    max_body: int = MAX_BODY,
):
    """JSON с ретраями и растущей паузой.

    Обходы областей и списков Минфина идут сотнями одиночных запросов: без повтора
    одна сетевая икота выбрасывает из сборки целый регион или целый отчёт."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(max_body + 1)
            # Обрезанный ответ разбирается как «битый JSON», и причина теряется:
            # потолок объявляется явной ошибкой.
            if len(body) > max_body:
                raise SourceError(f"{url}: ответ больше {max_body} байт")
            if raw_name:
                RAW.mkdir(parents=True, exist_ok=True)
                (RAW / raw_name).write_bytes(body)
            return json.loads(body.decode("utf-8", "ignore"))
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last = exc
            if not retriable(exc) or attempt == retries - 1:
                break
            backoff(attempt)
    raise SourceError(f"{url}: {last}")


def parse_worldbank(payload, spec: dict) -> list[Obs]:
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise SourceError(f"{spec['indicator']}: неожиданная структура ответа")
    obs = [
        Obs(date=row["date"], value=row["value"] * spec["scale"])
        for row in payload[1]
        if row.get("value") is not None
    ]
    obs.sort(key=lambda o: o.date)
    # Окно ряда. Гиперинфляция девяностых это правда, а не мусор источника, но на
    # пульсе она сжимает свежие годы в плоскую линию, поэтому история обрезается.
    keep = spec.get("keep_last", KEEP_LAST_YEARS)
    return obs[-keep:]


def fetch_worldbank(spec: dict) -> Series:
    url = (
        f"{WB_HOST}/country/KAZ/indicator/{spec['indicator']}?format=json&per_page=100"
    )
    obs = parse_worldbank(json.loads(fetch(url, f"wb_{spec['indicator']}.json")), spec)
    return Series(
        series_id=spec["series_id"],
        name_ru=spec["name_ru"],
        unit=spec["unit"],
        freq="A",
        source="World Bank",
        source_url=url,
        fetched_at=_now(),
        obs=obs,
    )


def month_points(months: int, today: date) -> list[date]:
    """Первые числа последних N месяцев плюс текущая дата."""
    points: list[date] = []
    year, month = today.year, today.month
    for _ in range(months):
        points.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    points.reverse()
    if points[-1] != today:
        points.append(today)
    return points


def parse_nbk_xml(body: bytes) -> dict[str, float]:
    """Курсы за одну дату. quant это база котировки: KRW котируется за 100 единиц."""
    root = ET.fromstring(body)
    rates: dict[str, float] = {}
    for item in root.findall(".//item"):
        code = (item.findtext("title") or "").strip()
        raw_value = (item.findtext("description") or "").strip()
        quant = (item.findtext("quant") or "1").strip()
        if not code or not raw_value:
            continue
        try:
            value = float(raw_value) / float(quant or 1)
        except (ValueError, ZeroDivisionError):
            continue
        rates[code] = value
    return rates


def fetch_fx(
    codes: list[str], months: int, today: date
) -> tuple[dict[str, list[Obs]], int]:
    """Курсы на набор дат. Пустая дата (выходной) сдвигается вперёд до трёх дней.

    Вторым значением возвращается число запрошенных дат: без него недобор ряда
    неотличим от полного ряда, и три точки вместо тридцати семи уедут как свежие."""
    collected: dict[str, list[Obs]] = {code: [] for code in codes}
    points = month_points(months, today)
    for point in points:
        for shift in range(3):
            day = point + timedelta(days=shift)
            if day > today:
                break
            stamp = day.strftime("%d.%m.%Y")
            url = f"{NBK_HOST}/rss/get_rates.cfm?fdate={stamp}"
            try:
                rates = parse_nbk_xml(fetch(url, f"fx_{day.isoformat()}.xml"))
            except (SourceError, ET.ParseError):
                continue
            if not rates:
                continue
            for code in codes:
                if code in rates:
                    collected[code].append(Obs(date=day.isoformat(), value=rates[code]))
            break
    return collected, len(points)


FREQ_BY_PERIOD = {"Год": "A", "Квартал": "Q", "Месяц": "M"}


def parse_bns_date(code: str, freq: str) -> str:
    """Код периода Taldau это ММГГГГ, где ММ это последний месяц периода.

    Год отдаётся как "122025", квартал как "032026" (первый квартал заканчивается
    мартом), месяц как "072026". Приводим к сортируемому виду, иначе гейт на
    возрастание дат отвергнет корректный ряд.
    """
    if len(code) != 6 or not code.isdigit():
        raise SourceError(f"неожиданный код периода: {code!r}")
    month, year = int(code[:2]), code[2:]
    if freq == "A":
        return year
    if freq == "Q":
        if month % 3:
            raise SourceError(f"квартальный код не кратен кварталу: {code!r}")
        return f"{year}-Q{month // 3}"
    return f"{year}-{month:02d}"


def parse_bns_dynamics(payload: dict, spec: dict, freq: str) -> list[Obs]:
    dates, values = payload.get("dateList") or [], payload.get("valueList") or []
    if not dates or len(dates) != len(values):
        raise SourceError(f"{spec['index_id']}: пустой или несогласованный ответ")
    obs = []
    for code, raw in zip(dates, values):
        if raw in (None, "", "-"):
            continue
        obs.append(
            Obs(date=parse_bns_date(code, freq), value=float(raw) * spec["scale"])
        )
    obs.sort(key=lambda o: o.date)
    return obs


def fetch_bns(spec: dict) -> Series:
    """Цепочка интерфейса Taldau: сессия, периодичность, разрез, ряд."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    index_id = spec["index_id"]
    page_url = f"{TALDAU_HOST}/ru/NewIndex/GetIndex/{index_id}"

    def call(path: str, params: dict, raw_name: str):
        body = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(
            f"{TALDAU_HOST}/ru/{path}", data=body, headers=TALDAU_HEADERS
        )
        for attempt in range(RETRIES):
            try:
                data = opener.open(req, timeout=TIMEOUT).read(MAX_BODY)
                RAW.mkdir(parents=True, exist_ok=True)
                (RAW / raw_name).write_bytes(data)
                return json.loads(data.decode("utf-8", "ignore"))
            except (
                urllib.error.URLError,
                TimeoutError,
                OSError,
                json.JSONDecodeError,
            ) as exc:
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise SourceError(f"{path}: {last}")

    try:
        opener.open(
            urllib.request.Request(page_url, headers=TALDAU_HEADERS), timeout=TIMEOUT
        ).read(MAX_BODY)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"страница показателя {index_id}: {exc}") from exc

    periods = call(
        "NewIndex/GetPeriodList",
        {"indexId": index_id, "keyword": ""},
        f"bns_{index_id}_periods.json",
    )
    period = next((p for p in periods if p.get("name") == spec["period"]), None)
    if period is None:
        available = ", ".join(str(p.get("name")) for p in periods)
        raise SourceError(
            f"{index_id}: периода {spec['period']!r} нет, есть: {available}"
        )

    segments = call(
        "NewIndex/GetSegmentList",
        {"indexId": index_id, "periodId": period["id"]},
        f"bns_{index_id}_segments.json",
    )
    if not segments:
        raise SourceError(f"{index_id}: разрезы не вернулись")
    segment = segments[0]

    payload = call(
        "NewIndex/GetDynamics",
        {
            "dicIds": segment["dicId"].replace(" + ", ","),
            "indexId": index_id,
            "periodId": period["id"],
            "terms": segment["termIds"],
            "filters_dates": BNS_DATE_RANGE,
        },
        f"bns_{index_id}_dynamics.json",
    )
    freq = FREQ_BY_PERIOD.get(spec["period"], "A")
    return Series(
        series_id=spec["series_id"],
        name_ru=spec["name_ru"],
        unit=spec["unit"],
        freq=freq,
        source="Бюро национальной статистики",
        source_url=page_url,
        fetched_at=_now(),
        obs=parse_bns_dynamics(payload, spec, freq),
        note=f"разрез: {segment.get('termNames', '')}",
    )


def validate(series: Series, bounds: dict, today: date | None = None) -> list[str]:
    """Гейт публикации. Непустой список означает, что ряд публиковать нельзя.

    Дата приходит снаружи: сборка, пересекающая полночь, иначе сверяет разные ряды
    с разными «сегодня»."""
    problems: list[str] = []
    if not series.obs:
        problems.append("ряд пустой")
        return problems

    dates = [o.date for o in series.obs]
    if len(set(dates)) != len(dates):
        problems.append("даты повторяются")
    if dates != sorted(dates):
        problems.append("даты не отсортированы")

    for o in series.obs:
        if o.value is None or not math.isfinite(o.value):
            problems.append(f"нечисловое значение на {o.date}")
            break
        if not (bounds["min"] <= o.value <= bounds["max"]):
            problems.append(
                f"значение {o.value:.4g} на {o.date} вне диапазона "
                f"{bounds['min']}..{bounds['max']}"
            )
            break

    age_days, limit = freshness(series.obs[-1].date, series.freq, today)
    if age_days > limit:
        problems.append(f"последняя точка {series.obs[-1].date} старше {limit} дней")

    return problems


def coverage_gap(got: int, expected: int) -> str | None:
    """Пометка о недоборе точек. None означает, что ряд собран целиком.

    Каждая неудачная дата курсов пропускается молча, а гейт публикации смотрит на
    сортировку, дубли, диапазон и возраст последней точки: недобора он не видит, и
    ряд из трёх точек вместо тридцати семи уезжает как свежий и полный."""
    if not expected or got >= expected * FX_FULL_COVERAGE:
        return None
    return f"собрано {got} точек из {expected}: источник ответил не на все даты"


def period_end(last: str, freq: str) -> date:
    """Календарный конец последнего периода ряда."""
    if freq == "A":
        return date(int(last), 12, 31)
    if freq == "Q":
        year, quarter = last.split("-Q")
        month = int(quarter) * 3
        return date(int(year), month, 1) + timedelta(days=31)
    if freq == "M":
        year, month = last.split("-")
        return date(int(year), int(month), 1) + timedelta(days=31)
    return date.fromisoformat(last)


def freshness(last: str, freq: str, today: date | None = None) -> tuple[int, int]:
    """Возраст последней точки и предел терпимости для этой периодичности.

    Пределы шире одного периода: статистика публикуется с лагом, и ряд, отставший
    на один срок публикации, это норма источника, а не поломка сборки.
    """
    limits = {"A": 800, "Q": 240, "M": 120, "D": 14}
    today = today or date.today()
    return (today - period_end(last, freq)).days, limits.get(freq, 14)


def load_previous(dataset: Path) -> dict[str, dict]:
    """Прошлый снапшот. В CI он берётся из закоммиченного файла: без него
    правило «источник упал, показываем прошлое значение» не сработает."""
    if not dataset.exists():
        return {}
    try:
        data = json.loads(dataset.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {s["series_id"]: s for s in data.get("series", [])}


def build(dataset: Path = DATASET, today: date | None = None) -> dict:
    # Дата фиксируется один раз на прогон: сборка, пересекающая полночь, иначе
    # сверяет свежесть разных рядов с разными «сегодня».
    today = today or date.today()
    previous = load_previous(dataset)
    result: list[dict] = []
    report: list[str] = []

    def keep_previous(series_id: str, reason: str) -> None:
        old = previous.get(series_id)
        report.append(f"{series_id}: {reason}")
        if old:
            old = dict(old)
            old["stale"] = True
            old["note"] = reason
            result.append(old)

    for spec in WB_SERIES:
        try:
            series = fetch_worldbank(spec)
        except SourceError as exc:
            keep_previous(spec["series_id"], f"источник недоступен ({exc})")
            continue
        problems = validate(series, spec, today)
        if problems:
            keep_previous(spec["series_id"], "; ".join(problems))
            continue
        result.append(asdict(series))

    fx_raw, fx_expected = fetch_fx([s["code"] for s in FX_SERIES], FX_MONTHS, today)
    for spec in FX_SERIES:
        obs = fx_raw.get(spec["code"], [])
        gap = coverage_gap(len(obs), fx_expected)
        series = Series(
            series_id=spec["series_id"],
            name_ru=spec["name_ru"],
            unit="тенге за 1 единицу",
            freq="D",
            source="Национальный Банк РК",
            source_url=f"{NBK_HOST}/rss/get_rates.cfm",
            fetched_at=_now(),
            obs=obs,
            note=gap or "",
        )
        problems = validate(series, spec, today)
        if len(obs) < fx_expected * FX_MIN_COVERAGE:
            # Половины ряда мало даже для пометки: такой график врёт формой.
            problems.append(gap or "ряд неполный")
        if problems:
            keep_previous(spec["series_id"], "; ".join(problems))
            continue
        if gap:
            report.append(f"{spec['series_id']}: {gap}")
        result.append(asdict(series))

    for spec in BNS_SERIES:
        try:
            series = fetch_bns(spec)
        except SourceError as exc:
            keep_previous(spec["series_id"], f"источник недоступен ({exc})")
            continue
        problems = validate(series, spec, today)
        if problems:
            keep_previous(spec["series_id"], "; ".join(problems))
            continue
        result.append(asdict(series))

    result.sort(key=lambda s: s["series_id"])
    return {
        "generated_at": _now(),
        "series": result,
        "issues": report,
    }


def main() -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DATASET
    data = build(dataset)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for s in data["series"] if not s.get("stale"))
    print(f"Рядов свежих: {ok}, всего: {len(data['series'])}")
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")
    # Ряд, который не собрался и которого нет даже в прошлом снапшоте, потерян
    # целиком: молча выйти с нулём значит выдать дыру за успешную сборку.
    expected = {s["series_id"] for s in WB_SERIES + FX_SERIES + BNS_SERIES}
    lost = sorted(expected - {s["series_id"] for s in data["series"]})
    if lost:
        raise SystemExit(f"потеряны ряды целиком: {', '.join(lost)}")


if __name__ == "__main__":
    main()
