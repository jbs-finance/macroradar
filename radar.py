"""Радар экономики Казахстана: то, чего нет в машинных источниках.

Три вещи, ради которых страницу открывают повторно, живут только в HTML госсайтов:
базовая ставка НБРК (таблица решений по годам), месячная инфляция с точностью до
десятых (текст публикации БНС) и календарь релизов (что выходит на этой неделе).
Плюс два производных слоя: лента событий, собранная из рядов детерминированно, и
интерпретация каждого показателя для бизнеса по порогам, а не по настроению.

Запуск: .venv/bin/python radar.py out/radar.json out/pulse.json out/trade.json
"""

from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from etl import NBK_HOST, Obs, Series, SourceError, _now, fetch, validate

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / "out" / "radar.json"

STAT_HOST = "https://stat.gov.kz"

# Таблица решений по ставке разбита по годам на отдельные рубрики. Семь лет дают
# диапазон, в котором есть и 9%, и 18%: этого достаточно, чтобы текущее значение
# читалось на фоне истории. Список известных рубрик это запасной вариант: id новой
# рубрики из года не выводится, поэтому годы берутся с самой страницы, иначе новый
# год просто не запрашивался бы, а обрыв заметил бы только гейт свежести.
RATE_YEARS = 7
RATE_RUBRICS = {
    2026: 2365,
    2025: 2237,
    2024: 2098,
    2023: 1843,
    2022: 1698,
    2021: 1581,
    2020: 1543,
}
RATE_PAGE = f"{NBK_HOST}/ru/news/grafik-prinyatiya-resheniy-po-bazovoy-stavke"
RUBRIC_LINK = re.compile(r'rubrics/(\d+)"[^>]*>\s*(20\d\d)\s*<')

# Цель НБРК по инфляции, от неё считается «выше цели» в интерпретации.
INFLATION_TARGET = 5.0
INFLATION_MONTHS = 24
EVENT_WINDOW_DAYS = 45
# Между плановыми решениями по ставке не больше двух месяцев, поэтому ряд старше
# полугода означает не паузу регулятора, а недокачанные страницы источника.
RATE_MAX_AGE_DAYS = 180

# Индекс деловой активности НБРК. Файл рядов весит 24 МБ и разбирается минутами, а
# то же число лежит текстом в информационном сообщении, поэтому берётся оттуда.
# Значение выше 50 означает расширение активности, ниже 50 сжатие.
BAI_NEWS = f"{NBK_HOST}/ru/news/informacionnye-soobshcheniya"
BAI_NEUTRAL = 50.0
BAI_MAX_AGE_DAYS = 100
# Секторы опроса ИДА. Ключ это основа слова: в тексте встречаются разные падежи.
BAI_SECTORS = {
    "строительств": "Строительство",
    "производств": "Производство",
    "услуг": "Услуги",
    "торговл": "Торговля",
    "горнодобыва": "Горнодобыча",
}

# Сравнение с соседями: страны, с которыми Казахстан реально конкурирует за
# инвестиции и рабочую силу, плюс два крупнейших торговых партнёра.
NEIGHBOURS = ["KAZ", "UZB", "RUS", "TUR", "CHN", "KGZ", "AZE", "GEO"]
NEIGHBOUR_RU = {
    "Kazakhstan": "Казахстан",
    "Uzbekistan": "Узбекистан",
    "Russian Federation": "Россия",
    "Turkiye": "Турция",
    "China": "Китай",
    "Kyrgyz Republic": "Киргизия",
    "Azerbaijan": "Азербайджан",
    "Georgia": "Грузия",
}
NEIGHBOUR_INDICATORS = [
    {
        "id": "inflation",
        "indicator": "FP.CPI.TOTL.ZG",
        "name_ru": "Инфляция",
        "unit": "% за год",
        "digits": 1,
        "lower_is_better": True,
    },
    {
        "id": "growth",
        "indicator": "NY.GDP.MKTP.KD.ZG",
        "name_ru": "Рост ВВП",
        "unit": "% за год",
        "digits": 1,
        "lower_is_better": False,
    },
    {
        "id": "gdp.pc",
        "indicator": "NY.GDP.PCAP.CD",
        "name_ru": "ВВП на душу населения",
        "unit": "USD",
        "digits": 0,
        "lower_is_better": False,
    },
]

MONTHS_GEN = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
MONTHS_PREP = {
    "январе": 1,
    "феврале": 2,
    "марте": 3,
    "апреле": 4,
    "мае": 5,
    "июне": 6,
    "июле": 7,
    "августе": 8,
    "сентябре": 9,
    "октябре": 10,
    "ноябре": 11,
    "декабре": 12,
}
MONTHS_RU = [
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
]


def _text(markup: str) -> str:
    plain = re.sub(r"(?s)<(script|style).*?</\1>", "", markup)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", plain))
    return re.sub(r"\s+", " ", plain)


def _num(raw: str) -> float:
    return float(raw.replace(",", ".").replace(" ", ""))


# --- Базовая ставка -----------------------------------------------------------


def parse_rate_table(markup: str) -> tuple[list[tuple[date, float, str]], list[date]]:
    """Строки таблицы решений: (дата, ставка, коридор). Даты со звёздочкой и без
    значения это будущие решения, они возвращаются отдельно."""
    decisions: list[tuple[date, float, str]] = []
    planned: list[date] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", markup, re.DOTALL):
        cells = [
            re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        ]
        if len(cells) < 2:
            continue
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})(\*?)", cells[0])
        if not m:
            continue
        day = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        value = cells[1].replace(",", ".").strip()
        if not value:
            planned.append(day)
            continue
        try:
            decisions.append((day, float(value), cells[2] if len(cells) > 2 else ""))
        except ValueError:
            continue
    return decisions, planned


def rate_rubrics(today: date) -> dict[int, int]:
    """Год -> рубрика таблицы решений, по последним RATE_YEARS годам.

    Список тянется с самой страницы: там годы подписаны ссылками на рубрики, и
    новый год подхватывается сам. Захардкоженный список остаётся запасным, чтобы
    недоступность страницы-оглавления не стоила всей истории."""
    known = dict(RATE_RUBRICS)
    try:
        body = fetch(RATE_PAGE, "rate_index.html").decode("utf-8", "ignore")
    except SourceError:
        body = ""
    for rubric, year in RUBRIC_LINK.findall(body):
        known[int(year)] = int(rubric)
    return {
        y: known[y]
        for y in range(today.year, today.year - RATE_YEARS, -1)
        if y in known
    }


def fetch_base_rate(today: date | None = None) -> tuple[Series, list[date], list[int]]:
    """Ряд решений, будущие даты и годы, которые собрать не удалось.

    Несобранный год возвращается наверх, а не проглатывается: если не скачался
    текущий год, ряд обрывается на прошлом, и без явного сигнала страница покажет
    старую ставку как действующую."""
    today = today or date.today()
    decisions: list[tuple[date, float, str]] = []
    planned: list[date] = []
    rubrics = rate_rubrics(today)
    failed: list[int] = [
        y for y in range(today.year, today.year - RATE_YEARS, -1) if y not in rubrics
    ]
    for year, rubric in rubrics.items():
        url = f"{RATE_PAGE}/rubrics/{rubric}"
        try:
            body = fetch(url, f"rate_{year}.html").decode("utf-8", "ignore")
        except SourceError:
            failed.append(year)
            continue
        got, future = parse_rate_table(body)
        if not got and not future:
            failed.append(year)
            continue
        decisions.extend(got)
        planned.extend(future)
    if not decisions:
        raise SourceError("таблица решений по ставке не разобрана ни за один год")
    decisions.sort()
    last_corridor = decisions[-1][2]
    return (
        Series(
            series_id="kz.rate.base",
            name_ru="Базовая ставка НБРК",
            unit="% годовых",
            freq="D",
            source="Национальный Банк РК",
            source_url=RATE_PAGE,
            fetched_at=_now(),
            obs=[Obs(date=d.isoformat(), value=v) for d, v, _ in decisions],
            note=f"коридор {last_corridor}" if last_corridor else "",
        ),
        sorted(planned),
        sorted(failed),
    )


# --- Месячная инфляция БНС ------------------------------------------------------


def calendar_events(markup: str) -> list[dict]:
    """События календаря релизов БНС: дата, название, тип, ссылка.

    У большинства событий название это голый текст между датой и типом, ссылка
    есть только у публикаций с файлом. Поэтому блок режется по частям, а ссылка
    берётся, если она нашлась, иначе событие ведёт на сам календарь."""
    events = []
    blocks = re.split(r'<div class="calendar-event(?:\s[^"]*)?"[^>]*>', markup)[1:]
    for block in blocks:
        day = re.search(
            r'calendar-event-day">\s*(\d{2})\.(\d{2})\.(\d{4})\s*</div>(.*?)<div class="calendar-event-type">\s*(.*?)\s*</div>',
            block,
            re.DOTALL,
        )
        if not day:
            continue
        middle = day.group(4)
        href_m = re.search(r'<a\b[^>]*href="([^"]+)"', middle)
        title = re.sub(
            r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", middle))
        ).strip()
        if not title:
            continue
        href = href_m.group(1) if href_m else "/ru/release-calendar/"
        events.append(
            {
                "date": f"{day.group(3)}-{day.group(2)}-{day.group(1)}",
                "title": title,
                "type": re.sub(r"\s+", " ", day.group(5)).strip(),
                "url": href if href.startswith("http") else STAT_HOST + href,
            }
        )
    return events


def fetch_calendar_day(day: date) -> list[dict]:
    stamp = f"{day.day}.{day.month}.{day.year}"
    body = fetch(
        f"{STAT_HOST}/ru/release-calendar/?date={stamp}",
        f"relcal_{day.isoformat()}.html",
    )
    return calendar_events(body.decode("utf-8", "ignore"))


def parse_inflation_page(markup: str) -> dict:
    """Числа из текста публикации «Инфляция в Республике Казахстан».

    БНС меняет формулировку от месяца к месяцу: «составила 9,8%», «за год составила
    12,9%», «замедлился и составил 0,7% ..., годовой уровень составил 11,8%».
    Поэтому годовое значение ищется по цепочке всё более общих шаблонов, а
    месячное отдельно, и оба проверяются на правдоподобие: перепутать их местами
    хуже, чем не разобрать страницу."""
    text = _text(markup)
    key = text.find("Ключевые моменты")
    scope = text[key:] if key >= 0 else text
    period = re.search(r"в ([а-яё]+) (\d{4}) года", scope)
    if not period or period.group(1) not in MONTHS_PREP:
        raise SourceError("в публикации не найден месяц и год")
    month = MONTHS_PREP[period.group(1)]
    year = int(period.group(2))

    def grab(patterns: list[str]) -> float | None:
        for pattern in patterns:
            m = re.search(pattern, scope)
            if m:
                return _num(m.group(1))
        return None

    yoy = grab(
        [
            r"годов(?:ой|ая)[^%]{0,60}?составил[а]?\s*(\d+(?:[.,]\d+)?)\s*%",
            r"за год составила\s*(\d+(?:[.,]\d+)?)\s*%",
            r"Инфляция в Республике Казахстан в [а-яё]+ \d{4} года[^%]{0,40}?составила\s*(\d+(?:[.,]\d+)?)\s*%",
        ]
    )
    if yoy is None or not 0 <= yoy < 60:
        raise SourceError("в публикации нет годовой инфляции")
    mom = grab(
        [
            r"за месяц[^\d]{0,8}(\d+(?:[.,]\d+)?)\s*%",
            r"Месячный уровень[^%]{0,80}?составил\s*(\d+(?:[.,]\d+)?)\s*%",
        ]
    )
    if mom is not None and abs(mom) > 5:
        mom = None

    def cat(pattern: str) -> float | None:
        m = re.search(pattern, scope)
        return _num(m.group(1)) if m else None

    return {
        "month": f"{year}-{month:02d}",
        "yoy": yoy,
        "mom": mom,
        "food": cat(
            r"(?<!не)продовольственные товары[^%]{0,40}?на\s*(\d+(?:[.,]\d+)?)\s*%"
        ),
        "nonfood": cat(
            r"непродовольственные товары[^%]{0,40}?на\s*(\d+(?:[.,]\d+)?)\s*%"
        ),
        "services": cat(r"платные услуги[^%]{0,40}?на\s*(\d+(?:[.,]\d+)?)\s*%"),
    }


def month_iter(months: int, today: date):
    """Месяцы, за которые ищем публикацию: от текущего назад."""
    y, m = today.year, today.month
    for _ in range(months):
        yield y, m
        m -= 1
        if m == 0:
            y, m = y - 1, 12


def fetch_inflation(
    previous: dict[str, dict], today: date
) -> tuple[list[dict], list[str]]:
    """Публикация за месяц M выходит 1-3 числа месяца M+1. Уже собранные месяцы
    берутся из прошлого снапшота: заново ходить за историей незачем."""
    points: dict[str, dict] = dict(previous)
    problems: list[str] = []
    for y, m in month_iter(INFLATION_MONTHS, today):
        # публикация за (y, m) выходит в следующем месяце
        py, pm = (y, m + 1) if m < 12 else (y + 1, 1)
        key = f"{y}-{m:02d}"
        if key in points:
            continue
        if date(py, pm, 1) > today:
            continue
        found = None
        for day in (1, 2, 3, 4):
            try:
                events = fetch_calendar_day(date(py, pm, day))
            except SourceError as exc:
                problems.append(f"календарь {py}-{pm:02d}-{day:02d}: {exc}")
                continue
            hit = next(
                (
                    e
                    for e in events
                    if e["title"].startswith("Инфляция в Республике Казахстан")
                ),
                None,
            )
            if hit:
                found = hit
                break
        if not found:
            continue
        try:
            page = fetch(found["url"], f"inflation_{key}.html").decode(
                "utf-8", "ignore"
            )
            detail = parse_inflation_page(page)
        except SourceError as exc:
            problems.append(f"инфляция {key}: {exc}")
            continue
        detail["source_url"] = found["url"]
        detail["published"] = found["date"]
        points[detail["month"]] = detail
    return sorted(points.values(), key=lambda p: p["month"]), problems


# --- Календарь ближайших релизов ------------------------------------------------


def fetch_upcoming(
    today: date, planned_rate: list[date], problems: list[str] | None = None
) -> list[dict]:
    """Релизы БНС с сегодняшнего дня до конца следующего месяца плюс ближайшее
    решение по ставке. Календарь отдаёт события по одному дню, поэтому месяц
    берётся с его страницы по умолчанию, а следующий месяц по первому числу.

    Причина недоступности календаря пишется наверх: молча опустевший блок «что
    выходит на этой неделе» неотличим от недели без публикаций."""
    problems = [] if problems is None else problems
    events: list[dict] = []
    try:
        body = fetch(f"{STAT_HOST}/ru/release-calendar/", "relcal_current.html")
        events.extend(calendar_events(body.decode("utf-8", "ignore")))
    except SourceError as exc:
        problems.append(f"календарь релизов, текущий месяц: {exc}")
    ny, nm = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    try:
        events.extend(fetch_calendar_day(date(ny, nm, 1)))
    except SourceError as exc:
        problems.append(f"календарь релизов, {ny}-{nm:02d}: {exc}")

    upcoming = [
        {**e, "kind": "stat"} for e in events if date.fromisoformat(e["date"]) >= today
    ]
    for d in planned_rate:
        if d >= today:
            upcoming.append(
                {
                    "date": d.isoformat(),
                    "title": "Решение НБРК по базовой ставке, 12:00 Астаны",
                    "type": "Решение",
                    "url": RATE_PAGE,
                    "kind": "rate",
                }
            )
    seen = set()
    unique = []
    for e in sorted(
        upcoming, key=lambda e: (e["date"], -release_priority(e), e["title"])
    ):
        key = (e["date"], e["title"])
        if key in seen or release_priority(e) == 0:
            continue
        seen.add(key)
        unique.append(e)
    return unique


# Календарь БНС отдаёт до ста строк в месяц, из них бизнесу важны единицы. Вес
# выбирает то, что двигает цены, зарплаты и спрос; остальное не показывается.
RELEASE_WEIGHTS = [
    ("инфляци", 5),
    ("валовой внутренний продукт", 5),
    ("ввп", 5),
    ("заработная плата", 4),
    ("безработ", 4),
    ("рабочей силы", 3),
    ("численность населения", 3),
    ("инвестиции в основной капитал", 3),
    ("розничн", 3),
    ("промышленн", 2),
    ("цены производителей", 2),
    ("социально-значимые", 2),
    ("внешн", 2),
    ("строительств", 1),
]


def release_priority(event: dict) -> int:
    if event.get("kind") == "rate":
        return 10
    title = event.get("title", "").lower()
    score = 0
    for needle, weight in RELEASE_WEIGHTS:
        if needle in title:
            score = max(score, weight)
    if score and event.get("type", "").startswith("Публикац"):
        score += 1
    return score


# --- Лента событий -------------------------------------------------------------


def rate_events(rate: Series, since: date, today: date | None = None) -> list[dict]:
    """Лента изменений по ставке.

    У ставки дата это день вступления в силу, а решение объявляют раньше. Такое
    событие попадало в ленту прошедших изменений завтрашним числом и читалось как
    ошибка. Оно остаётся (карточка ставки уже показывает новое значение), но
    помечается как ещё не наступившее.
    """
    out = []
    obs = rate.obs
    today = today or date.today()
    for i, o in enumerate(obs):
        d = date.fromisoformat(o.date)
        if d < since:
            continue
        prev = obs[i - 1].value if i else None
        if prev is None or o.value == prev:
            verb = "сохранил"
        elif o.value < prev:
            verb = "снизил"
        else:
            verb = "повысил"
        tail = (
            f" (было {fmt_pct(prev)})" if prev is not None and o.value != prev else ""
        )
        upcoming = d > today
        if upcoming:
            verb = {"снизил": "снижает", "повысил": "повышает"}.get(verb, "сохраняет")
        out.append(
            {
                "date": o.date,
                "kind": "rate",
                "text": f"НБРК {verb} базовую ставку до {fmt_pct(o.value)}{tail}",
                "upcoming": upcoming,
            }
        )
    return out


def inflation_events(points: list[dict], since: date) -> list[dict]:
    out = []
    for i, p in enumerate(points):
        published = p.get("published")
        if not published or date.fromisoformat(published) < since:
            continue
        y, m = p["month"].split("-")
        label = f"{MONTHS_RU[int(m) - 1]} {y}"
        prev = points[i - 1]["yoy"] if i else None
        if prev is None:
            cmp = ""
        elif p["yoy"] < prev:
            cmp = f", ниже прошлого месяца ({fmt_pct(prev)})"
        elif p["yoy"] > prev:
            cmp = f", выше прошлого месяца ({fmt_pct(prev)})"
        else:
            cmp = ", как и месяцем ранее"
        # Серия снижений считается назад от текущей точки.
        streak = 0
        for j in range(i, 0, -1):
            if points[j]["yoy"] < points[j - 1]["yoy"]:
                streak += 1
            else:
                break
        streak_note = f". Снижается {streak} мес. подряд" if streak >= 3 else ""
        out.append(
            {
                "date": published,
                "kind": "inflation",
                "text": f"Инфляция за {label}: {fmt_pct(p['yoy'])}{cmp}{streak_note}",
            }
        )
    return out


def fx_events(fx: dict | None, today: date) -> list[dict]:
    if not fx or len(fx.get("obs", [])) < 2:
        return []
    obs = fx["obs"]
    last = obs[-1]
    target = date.fromisoformat(last["date"]) - timedelta(days=30)
    base = min(obs[:-1], key=lambda o: abs(date.fromisoformat(o["date"]) - target))
    change = (last["value"] - base["value"]) / base["value"] * 100
    if abs(change) < 2:
        return []
    verb = "ослаб к доллару" if change > 0 else "укрепился к доллару"
    return [
        {
            "date": last["date"],
            "kind": "fx",
            "text": f"Тенге {verb} на {dec(abs(change))}% за месяц: {dec(last['value'], 2)} за USD",
        }
    ]


# --- Казахстан среди соседей ------------------------------------------------------


def fetch_neighbours() -> tuple[list[dict], list[str]]:
    """Последнее известное значение по каждой стране. Международная база отдаёт все
    страны одним запросом, поэтому сравнение стоит три обращения, а не двадцать четыре."""
    from etl import WB_HOST

    out: list[dict] = []
    problems: list[str] = []
    countries = ";".join(NEIGHBOURS)
    for spec in NEIGHBOUR_INDICATORS:
        url = (
            f"{WB_HOST}/country/{countries}/indicator/{spec['indicator']}"
            "?format=json&per_page=200&mrnev=1"
        )
        try:
            payload = json.loads(fetch(url, f"wb_neighbours_{spec['id']}.json"))
        except SourceError as exc:
            problems.append(f"соседи, {spec['name_ru']}: {exc}")
            continue
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else None
        if not rows:
            problems.append(f"соседи, {spec['name_ru']}: пустой ответ")
            continue
        items = []
        for row in rows:
            value = row.get("value")
            if value is None:
                continue
            name = row["country"]["value"]
            items.append(
                {
                    "country": NEIGHBOUR_RU.get(name, name),
                    "value": value,
                    "year": row["date"],
                    "is_kz": row.get("countryiso3code") == "KAZ",
                }
            )
        if not items:
            problems.append(f"соседи, {spec['name_ru']}: ни одного значения")
            continue
        items.sort(key=lambda i: i["value"], reverse=not spec["lower_is_better"])
        out.append(
            {
                "id": spec["id"],
                "name_ru": spec["name_ru"],
                "unit": spec["unit"],
                "digits": spec["digits"],
                "lower_is_better": spec["lower_is_better"],
                "source": "World Bank",
                "fetched_at": _now(),
                "items": items,
            }
        )
    return out, problems


# --- Деловая активность -----------------------------------------------------------


def parse_business_activity(markup: str) -> dict:
    """Числа ИДА из текста информационного сообщения.

    Набор секторов у опроса фиксирован, поэтому они ищутся по словарю, а не по
    шаблону «в чём-то»: иначе в названия попадают обороты вроде «в зоне роста».
    Значения прошлого месяца стоят в скобках и вырезаются до разбора чисел, иначе
    они сдвигают сопоставление секторов со значениями."""
    text = _text(markup)
    period = re.search(r"о деловой активности в ([а-яё]+) (\d{4}) года", text)
    if not period:
        period = re.search(r"В ([а-яё]+) (\d{4}) года индекс деловой активности", text)
    if not period or period.group(1).lower() not in MONTHS_PREP:
        raise SourceError("в сообщении не найден месяц")
    month = MONTHS_PREP[period.group(1).lower()]
    year = int(period.group(2))

    total = re.search(
        r"индекс деловой активности[^.]{0,120}?состав\w+\s*(\d+(?:[.,]\d+)?)", text
    )
    if not total:
        raise SourceError("в сообщении нет сводного значения ИДА")

    sectors: list[dict] = []
    used: set[str] = set()
    for sentence in text.split("."):
        if "состав" not in sentence:
            continue
        clean = re.sub(r"\([^)]*\)", " ", sentence)
        numbers = [_num(n) for n in re.findall(r"\b(\d{2},\d)\b", clean)]
        if not numbers:
            continue
        found = []
        for stem, label in BAI_SECTORS.items():
            pos = clean.lower().find(stem)
            if pos >= 0 and label not in used:
                found.append((pos, label))
        found.sort()
        for (_, label), value in zip(found, numbers):
            if 20 <= value <= 80:
                sectors.append({"name": label, "value": value})
                used.add(label)

    climate = re.search(r"бизнес-климата[^.]{0,80}?состав\w+\s*(\d+(?:[.,]\d+)?)", text)
    return {
        "month": f"{year}-{month:02d}",
        "value": _num(total.group(1)),
        "sectors": sectors,
        "climate": _num(climate.group(1)) if climate else None,
    }


def fetch_business_activity() -> tuple[dict | None, list[str]]:
    """Свежее сообщение об ИДА из ленты информационных сообщений НБРК."""
    problems: list[str] = []
    try:
        listing = fetch(BAI_NEWS, "bai_listing.html").decode("utf-8", "ignore")
    except SourceError as exc:
        return None, [f"ИДА: лента недоступна ({exc})"]

    seen: set[str] = set()
    for href, num, raw_title in re.findall(
        r'href="(/ru/news/informacionnye-soobshcheniya/(\d+))"[^>]*>(.*?)</a>',
        listing,
        re.DOTALL,
    ):
        if num in seen:
            continue
        seen.add(num)
        title = re.sub(
            r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw_title))
        ).strip()
        if "ИДА" not in title and "еловая активность" not in title:
            continue
        url = NBK_HOST + href
        try:
            page = fetch(url, f"bai_{num}.html").decode("utf-8", "ignore")
            data = parse_business_activity(page)
        except SourceError as exc:
            problems.append(f"ИДА: {exc}")
            continue
        if not (20 <= data["value"] <= 80):
            problems.append(
                f"ИДА: значение {data['value']} вне правдоподобного диапазона"
            )
            continue
        data["source"] = "Национальный Банк РК"
        data["source_url"] = url
        data["title"] = title
        data["fetched_at"] = _now()
        return data, problems
    problems.append("ИДА: свежего сообщения в ленте нет")
    return None, problems


def signal_business_activity(bai: dict | None) -> str:
    if not bai:
        return ""
    value = bai["value"]
    weak = [
        s["name"].lower() for s in bai.get("sectors", []) if s["value"] < BAI_NEUTRAL
    ]
    if value > BAI_NEUTRAL + 2:
        head = f"Активность заметно расширяется ({fmt_pct(value).rstrip('%')} против нейтральных 50): спрос растёт, конкуренция за подрядчиков и кадры усиливается."
    elif value > BAI_NEUTRAL:
        head = f"Активность выше нейтральной отметки ({fmt_pct(value).rstrip('%')} против 50), но запас невелик."
    elif value > BAI_NEUTRAL - 2:
        head = f"Активность около нейтральной отметки ({fmt_pct(value).rstrip('%')} против 50): рынок ни растёт, ни падает."
    else:
        head = f"Активность сжимается ({fmt_pct(value).rstrip('%')} против нейтральных 50): планируйте выручку консервативно."
    if weak:
        head += " Ниже нейтральной отметки: " + ", ".join(weak[:3]) + "."
    return head


# --- Интерпретация для бизнеса ---------------------------------------------------


def dec(v: float, digits: int = 1) -> str:
    """Число с запятой в дробной части для текста на странице."""
    return f"{v:.{digits}f}".replace(".", ",")


def fmt_pct(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def signal_rate(rate: Series, inflation_yoy: float | None) -> str:
    obs = rate.obs
    if len(obs) < 2:
        return ""
    last, prev = obs[-1].value, obs[-2].value
    cuts = 0
    for i in range(len(obs) - 1, 0, -1):
        if obs[i].value < obs[i - 1].value:
            cuts += 1
        else:
            break
    hikes = 0
    for i in range(len(obs) - 1, 0, -1):
        if obs[i].value > obs[i - 1].value:
            hikes += 1
        else:
            break
    if cuts >= 2:
        head = f"Цикл смягчения: {cuts} снижения подряд. Ставки по кредитам и лизингу пойдут вниз с лагом в один-два квартала."
    elif hikes >= 2:
        head = f"Цикл ужесточения: {hikes} повышения подряд. Заёмные деньги дорожают, пересмотрите планы на кредит."
    elif last < prev:
        head = "Первое снижение после паузы. Рано перекладывать в планы, дождитесь следующего решения."
    elif last > prev:
        head = "Повышение после паузы: сигнал, что инфляция беспокоит регулятора."
    else:
        head = "Пауза: регулятор ждёт данных. Условия по кредитам в ближайший квартал не изменятся."
    if inflation_yoy is not None:
        real = last - inflation_yoy
        head += f" Реальная ставка около {dec(real)} п.п.: деньги дорогие, а депозиты обгоняют инфляцию."
    return head


def signal_inflation(points: list[dict]) -> str:
    if not points:
        return ""
    p = points[-1]
    yoy = p["yoy"]
    parts = []
    if yoy > INFLATION_TARGET * 1.5:
        parts.append(
            f"Почти вдвое выше цели НБРК в {INFLATION_TARGET:.0f}%: закладывайте индексацию цен и зарплат в бюджет."
        )
    elif yoy > INFLATION_TARGET:
        parts.append(
            f"Выше цели НБРК в {INFLATION_TARGET:.0f}%, но в пределах управляемого."
        )
    else:
        parts.append("В пределах цели НБРК: ценовое давление слабое.")
    if p.get("food") is not None and p.get("services") is not None:
        if p["food"] > yoy:
            parts.append(
                f"Продукты дорожают быстрее среднего ({fmt_pct(p['food'])}), это бьёт по общепиту и рознице."
            )
        if p["services"] < yoy:
            parts.append(f"Услуги дорожают медленнее ({fmt_pct(p['services'])}).")
    return " ".join(parts)


def signal_fx(fx: dict | None) -> str:
    if not fx or len(fx.get("obs", [])) < 13:
        return ""
    obs = fx["obs"]
    last = obs[-1]
    year_ago = obs[-13]
    change = (last["value"] - year_ago["value"]) / year_ago["value"] * 100
    if change < -3:
        return f"Тенге укрепился на {dec(abs(change), 0)}% за год: импортные закупки дешевле, экспортная выручка в тенге меньше. Хороший момент для закупки оборудования."
    if change > 3:
        return f"Тенге ослаб на {dec(change, 0)}% за год: импорт и валютные обязательства дороже, экспортёрам выгодно."
    return "Курс за год почти не изменился: валютный фактор в планировании можно считать нейтральным."


def signal_growth(growth: dict | None) -> str:
    if not growth or not growth.get("obs"):
        return ""
    obs = growth["obs"]
    last = obs[-1]["value"]
    avg = sum(o["value"] for o in obs[-10:]) / min(len(obs), 10)
    if last > avg + 1:
        return f"Рост {fmt_pct(last)} заметно выше среднего за десять лет ({dec(avg)}%): спрос расширяется, конкуренция за кадры растёт."
    if last < avg - 1:
        return f"Рост {fmt_pct(last)} ниже среднего за десять лет ({dec(avg)}%): планируйте консервативно."
    return f"Рост {fmt_pct(last)} около среднего за десять лет ({dec(avg)}%)."


def signal_wage(wage: dict | None, inflation_yoy: float | None) -> str:
    if not wage or len(wage.get("obs", [])) < 5:
        return ""
    obs = wage["obs"]
    change = (obs[-1]["value"] - obs[-5]["value"]) / obs[-5]["value"] * 100
    if inflation_yoy is None:
        return f"Номинальная зарплата выросла на {dec(change)}% за год."
    real = change - inflation_yoy
    if real > 1:
        return f"Зарплаты растут быстрее инфляции: плюс {dec(change)}% номинально, около {dec(real)}% реально. Удержание людей дорожает."
    if real < -1:
        return f"Зарплаты отстают от инфляции: плюс {dec(change)}% номинально, минус {dec(abs(real))}% реально. Давление на пересмотр окладов накапливается."
    return f"Зарплаты растут вровень с инфляцией (плюс {dec(change)}% номинально)."


def signal_exports(exports: dict | None, commodities: dict | None) -> str:
    if not exports or not exports.get("obs"):
        return ""
    parts = []
    obs = exports["obs"]
    if len(obs) >= 2:
        change = (obs[-1]["value"] - obs[-2]["value"]) / obs[-2]["value"] * 100
        parts.append(
            f"Экспорт {'вырос' if change >= 0 else 'снизился'} на {dec(abs(change))}% за год."
        )
    if commodities and commodities.get("items"):
        top = commodities["items"][0]
        total = sum(i["value"] for i in commodities["items"])
        share = top["value"] / total * 100 if total else 0
        if share > 40:
            parts.append(
                f"Первая товарная группа ({top['label'].lower()}) даёт {dec(share, 0)}% из первой десятки: курс тенге по-прежнему зависит от нефти."
            )
    return " ".join(parts)


def signal_unemployment(unemp: dict | None) -> str:
    if not unemp or not unemp.get("obs"):
        return ""
    last = unemp["obs"][-1]["value"]
    if last < 5:
        return f"Безработица {fmt_pct(last)}: рынок труда тесный, найм и удержание дорожают."
    if last > 7:
        return f"Безработица {fmt_pct(last)}: предложение рабочей силы растёт, нанимать проще."
    return f"Безработица {fmt_pct(last)}: рынок труда в норме."


# --- Сборка --------------------------------------------------------------------


def load_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build(
    dataset: Path,
    pulse_path: Path | None,
    trade_path: Path | None,
    today: date | None = None,
) -> dict:
    # Дата фиксируется один раз на прогон: прогон, пересекающий полночь, иначе
    # мерит возраст ставки одним днём, а возраст ИДА другим.
    today = today or date.today()
    previous = load_json(dataset)
    pulse = load_json(pulse_path)
    trade = load_json(trade_path)
    by_id = {s["series_id"]: s for s in pulse.get("series", [])}
    trade_by_id = {s["series_id"]: s for s in trade.get("series", [])}
    breakdowns = {b["id"]: b for b in trade.get("breakdowns", [])}

    issues: list[str] = []
    series_out: list[dict] = []
    planned_rate: list[date] = []

    rate: Series | None = None
    try:
        rate, planned_rate, failed_years = fetch_base_rate(today)
        if failed_years:
            issues.append(
                "kz.rate.base: не собраны решения за "
                + ", ".join(str(y) for y in failed_years)
            )
        problems = validate(rate, {"min": 1, "max": 40}, today)
        # Дневная мера свежести к ставке неприменима: решений восемь в год. Но и
        # снимать проверку нельзя, иначе обрыв ряда на прошлом годе пройдёт молча.
        age = (today - date.fromisoformat(rate.obs[-1].date)).days
        problems = [p for p in problems if "старше" not in p]
        if age > RATE_MAX_AGE_DAYS:
            problems.append(
                f"последнее решение {rate.obs[-1].date} старше {RATE_MAX_AGE_DAYS} дней"
            )
        if problems:
            raise SourceError("; ".join(problems))
        series_out.append(asdict(rate))
    except SourceError as exc:
        issues.append(f"kz.rate.base: {exc}")
        old = next(
            (s for s in previous.get("series", []) if s["series_id"] == "kz.rate.base"),
            None,
        )
        if old:
            old = {**old, "stale": True, "note": str(exc)}
            series_out.append(old)
            rate = Series(**{**old, "obs": [Obs(**o) for o in old["obs"]]})

    prev_points = {p["month"]: p for p in previous.get("inflation", [])}
    points, problems = fetch_inflation(prev_points, today)
    issues.extend(problems)
    if points:
        series_out.append(
            asdict(
                Series(
                    series_id="kz.cpi.monthly",
                    name_ru="Инфляция, год к году",
                    unit="% к тому же месяцу прошлого года",
                    freq="M",
                    source="Бюро национальной статистики",
                    source_url=points[-1].get("source_url", STAT_HOST),
                    fetched_at=_now(),
                    obs=[Obs(date=p["month"], value=p["yoy"]) for p in points],
                )
            )
        )
    else:
        issues.append("kz.cpi.monthly: ни одной публикации об инфляции не найдено")

    calendar_problems: list[str] = []
    calendar = fetch_upcoming(today, planned_rate, calendar_problems)
    issues.extend(calendar_problems)
    next_rate = next((e for e in calendar if e["kind"] == "rate"), None)
    if not next_rate:
        issues.append(
            "следующее решение по ставке неизвестно: в таблице нет будущих дат"
        )

    since = today - timedelta(days=EVENT_WINDOW_DAYS)
    events: list[dict] = []
    if rate:
        events.extend(rate_events(rate, since, today))
    events.extend(inflation_events(points, since))
    events.extend(fx_events(by_id.get("kz.fx.usd"), today))
    events.sort(key=lambda e: e["date"], reverse=True)

    bai, bai_problems = fetch_business_activity()
    issues.extend(bai_problems)
    if bai is None:
        old_bai = previous.get("business_activity")
        if old_bai:
            bai = {**old_bai, "stale": True}
    elif bai:
        age = (
            date.today() - date(int(bai["month"][:4]), int(bai["month"][5:7]), 28)
        ).days
        if age > BAI_MAX_AGE_DAYS:
            issues.append(f"ИДА: последнее сообщение за {bai['month']}")

    neighbours, neighbour_problems = fetch_neighbours()
    issues.extend(neighbour_problems)
    if not neighbours:
        # Сравнение не критично для страницы, поэтому прошлый срез показывается
        # с пометкой, а не выбрасывается.
        neighbours = [{**n, "stale": True} for n in (previous.get("neighbours") or [])]

    inflation_yoy = points[-1]["yoy"] if points else None
    signals = {
        "rate": signal_rate(rate, inflation_yoy) if rate else "",
        "inflation": signal_inflation(points),
        "fx": signal_fx(by_id.get("kz.fx.usd")),
        "growth": signal_growth(by_id.get("kz.gdp.growth")),
        "wage": signal_wage(by_id.get("kz.wage.avg"), inflation_yoy),
        "exports": signal_exports(
            trade_by_id.get("kz.exports.usd"), breakdowns.get("exports.commodities")
        ),
        "unemployment": signal_unemployment(by_id.get("kz.unemployment")),
        "business_activity": signal_business_activity(bai),
    }

    return {
        "generated_at": _now(),
        "series": series_out,
        "inflation": points,
        "next_rate_decision": next_rate,
        "calendar": calendar[:14],
        "neighbours": neighbours,
        "business_activity": bai,
        "events": events[:12],
        "signals": signals,
        "issues": issues,
    }


def main() -> None:
    args = [Path(a).resolve() for a in sys.argv[1:]]
    dataset = args[0] if args else DEFAULT_DATASET
    pulse_path = args[1] if len(args) > 1 else HERE / "out" / "pulse.json"
    trade_path = args[2] if len(args) > 2 else HERE / "out" / "trade.json"
    data = build(dataset, pulse_path, trade_path)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Рядов: {len(data['series'])}, точек инфляции: {len(data['inflation'])}, "
        f"событий: {len(data['events'])}, релизов впереди: {len(data['calendar'])}, "
        f"сравнений: {len(data['neighbours'])}"
    )
    if data["next_rate_decision"]:
        print(f"Следующее решение по ставке: {data['next_rate_decision']['date']}")
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")
    # Ставка и месячная инфляция это и есть радар: без любой из них публиковать
    # нечего, и молчаливый нулевой код скрыл бы дыру.
    lost = []
    if not any(s["series_id"] == "kz.rate.base" for s in data["series"]):
        lost.append("базовая ставка")
    if not data["inflation"]:
        lost.append("месячная инфляция")
    if lost:
        raise SystemExit(f"потеряно целиком: {', '.join(lost)}")


if __name__ == "__main__":
    main()
