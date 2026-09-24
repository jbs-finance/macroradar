"""Число сделок купли-продажи жилья: ежемесячные пресс-релизы БНС на stat.gov.kz.

Таблицы и показателя Talдау у этого ряда нет (проверено 24.09.2026: разделы цен,
жилищного фонда, строительства, поиск каталога). Есть только текст релиза с адресом
/ru/news/kolichestvo-sdelok-kupli-prodazhi-zhilya-*/ примерно раз в месяц. Лента новостей
без фильтра по теме, около 30 новостей в месяц, поэтому листается постранично.

Разбор детерминированный и узкий: месяц, всего сделок, сделки с квартирами, Алматы и
Астана. Формулировки меняются от релиза к релизу, а числа в HTML бывают порезаны тегами
(«3</span>7 158»), поэтому теги срезаются без разделителя. Контроль: доля квартир из
текста («что составляет 77,4%») должна совпасть с расчётной. Не прошёл контроль или не
разобрался релиз: месяц пропускается и пишется в issues, публикация не останавливается.

Запуск: .venv/bin/python deals.py [out/deals.json]
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from etl import SourceError, fetch

DATASET = Path(__file__).resolve().parent / "out" / "deals.json"
NEWS = "https://stat.gov.kz/ru/news/"
SLUG = re.compile(
    r'href="(/ru/news/kolichestvo-sdelok-kupli-prodazhi-zhilya[a-z0-9-]*/)"'
)
PAUSE = 3.0
MAX_PAGES = 30
MONTHS = 13
MONTH_RU = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
NUM = r"(\d{1,3}(?: \d{3})+|\d+)"
# Дефис и два вида типографских тире, которыми БНС отделяет город от числа.
DASHES = "-" + chr(0x2013) + chr(0x2014)


def plain(page: str) -> str:
    """Текст релиза: блочные теги в пробел, строчные теги срезаются, чтобы склеить числа."""
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.DOTALL)
    page = re.sub(
        r"</?(?:p|div|br|li|ul|h\d|tr|td)\b[^>]*>", " ", page, flags=re.IGNORECASE
    )
    text = html.unescape(re.sub(r"<[^>]+>", "", page)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text)


def _int(s: str) -> int:
    return int(s.replace(" ", ""))


def _month(word: str) -> int:
    for stem, number in MONTH_RU.items():
        if word.lower().startswith(stem):
            return number
    raise ValueError(word)


def parse_release(page: str) -> dict[str, Any]:
    text = plain(page)
    head = re.search(
        r"В ([а-я]+) (\d{4}) года (?:количество зарегистрированных сделок купли-продажи жилья "
        rf"составило|зарегистрировано(?: [^.\d]*?[{DASHES}])?) {NUM}",
        text,
    )
    if not head:
        raise ValueError("не найдена фраза с общим числом сделок")
    month, year, total = _month(head[1]), int(head[2]), _int(head[3])
    flats = re.search(
        rf"по квартирам (?:было )?совершено {NUM}|зарегистрирован[аоы]? {NUM} сдел[а-я]* с квартирами"
        rf"|{NUM} по квартирам",
        text,
    )
    share = re.search(rf"(?:что составляет|[{DASHES}] это) (\d+(?:,\d+)?)% от общего", text)
    if not flats or not share:
        raise ValueError("не найдены сделки с квартирами или их доля")
    flats_n = _int(next(g for g in flats.groups() if g))
    if abs(flats_n / total * 100 - float(share[1].replace(",", "."))) > 0.2:
        raise ValueError(
            f"доля квартир не сходится: {flats_n} из {total} против {share[1]}%"
        )
    cities = {}
    for key, pattern in (("almaty", r"Алмат[ыау]"), ("astana", r"Астан[аеуы]")):
        m = re.search(rf"{pattern}\s*(?:\(|[{DASHES}])\s*{NUM}", text)
        if m:
            cities[key] = _int(m[1])
    return {
        "date": f"{year}-{month:02d}",
        "total": total,
        "flats": flats_n,
        "houses": total - flats_n,
        **cities,
    }


def release_urls(get: Callable[[str, str], str], issues: list[str]) -> list[str]:
    found: dict[str, None] = {}
    for page in range(1, MAX_PAGES + 1):
        try:
            body = get(f"{NEWS}?PAGEN_1={page}", f"news_{page}.html")
        except SourceError as exc:
            issues.append(f"лента новостей БНС, страница {page}: {exc}")
            break
        found.update(dict.fromkeys(SLUG.findall(body)))
        if len(found) >= MONTHS:
            break
    return ["https://stat.gov.kz" + u for u in found]


def polite_fetch() -> Callable[[str, str], str]:
    last = [0.0]

    def get(url: str, raw_name: str) -> str:
        wait = PAUSE - (time.monotonic() - last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return fetch(url, "deals_" + raw_name).decode("utf-8", "replace")
        finally:
            last[0] = time.monotonic()

    return get


def build(
    get: Callable[[str, str], str] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    get = get or polite_fetch()
    issues: list[str] = []
    months: dict[str, dict] = {}
    for url in release_urls(get, issues):
        try:
            row = parse_release(get(url, url.rstrip("/").rsplit("/", 1)[-1] + ".html"))
        except (SourceError, ValueError) as exc:
            issues.append(f"{url}: {exc}")
            continue
        months.setdefault(row["date"], {**row, "url": url})
    return {
        "generated_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "source": "Бюро национальной статистики, пресс-релизы о сделках купли-продажи жилья",
        "obs": sorted(months.values(), key=lambda r: r["date"]),
        "issues": issues,
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"deals: месяцев {len(data['obs'])}, проблем {len(data['issues'])}")


if __name__ == "__main__":
    main()
