"""Исполнение бюджетов областей из статистического бюллетеня Минфина РК.

Раньше здесь был обход двадцати сайтов областных управлений финансов: у каждого
свой адрес на gov.kz, своя форма и свой ритм публикации. Собиралось 13 регионов из
20, периоды у них расходились на годы, и общий порядок из таких цифр не строился.

Минфин публикует то же самое централизованно: в статистическом бюллетене листы
«табл 12.1» ... «табл 12.20», по одному на регион, плюс сводный «табл 12». Один
файл в месяц, одинаковый период у всех, план и факт рядом, млн тенге.

Три особенности источника, из-за которых код выглядит именно так:

1. Заголовок документа врёт: три разных выпуска подписаны «April 1, 2026», а
   свежие приходят с английским названием. Период читается из самого файла.
2. Подпись внутри листа не совпадает с его именем: на листе «табл 12.15» написано
   «Таблица 12», на «табл 12.16» написано «Таблица 12.15». Регион определяется по
   русскому названию в шапке, а не по номеру.
3. В наименованиях строк встречается мусор «_x000D_» и переносы.

Запуск: .venv/bin/python oblast.py out/oblast.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from budget import SourceError, as_number, download
from budget import Workbook as XlsxBook
from etl import fetch_json

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DEFAULT_DATASET = HERE / "out" / "oblast.json"

SITE = "https://www.gov.kz"
API = f"{SITE}/api/v1/public/content-manager/documents"
# Раздел «Бюджетный процесс» Минфина. Поиск по заголовку не годится: свежие выпуски
# приходят с английским названием и в русскую выдачу не попадают вовсе.
BULLETIN_ACTIVITY = 7294
DOC_PAGE = f"{SITE}/memleket/entities/minfin/documents/details"

# Лист региона: «табл 12.1» ... «табл 12.20». Свод по местным бюджетам это «табл 12»
# без номера, он используется как контрольная сумма.
SHEET_RE = re.compile(r"^\s*табл\s*12(?:\.(\d+))?\s*$", re.IGNORECASE)

COL_PLAN = 4
COL_FACT = 5
COL_NAME_RU = 6

MONTHS_RU = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}

# Категории доходов верхнего уровня. Код нужен рендеру: «1» это налоговая часть.
INCOME_ROWS = [
    ("1", "Налоговые поступления"),
    ("2", "Неналоговые поступления"),
    ("3", "Поступления от продажи основного капитала"),
    ("4", "Специальные поступления"),
    ("5", "Поступления трансфертов"),
]

TOTAL_ROW = "I. ДОХОДЫ"
SUMMARY_TITLE = "ИСПОЛНЕНИЕ МЕСТНЫХ БЮДЖЕТОВ"

# Бюллетень пишет названия сокращённо и капсом. На странице они должны выглядеть
# так же, как в остальных блоках радара.
REGION_NAMES = {
    "АКМОЛИНСКАЯ ОБЛАСТЬ": ("Акмолинская", "aqmola"),
    "АКТЮБИНСКАЯ ОБЛАСТЬ": ("Актюбинская", "aktobe"),
    "АЛМАТИНСКАЯ ОБЛАСТЬ": ("Алматинская", "almaty-obl"),
    "АТЫРАУСКАЯ ОБЛАСТЬ": ("Атырауская", "atyrau"),
    "ВОСТ-КАЗАХСТАНСКАЯ ОБЛАСТЬ": ("Восточно-Казахстанская", "vko"),
    "ЖАМБЫЛСКАЯ ОБЛАСТЬ": ("Жамбылская", "zhambyl"),
    "ЗАП-КАЗАХСТАНСКАЯ ОБЛАСТЬ": ("Западно-Казахстанская", "zko"),
    "КАРАГАНДИНСКАЯ ОБЛАСТЬ": ("Карагандинская", "karaganda"),
    "КЫЗЫЛОРДИНСКАЯ ОБЛАСТЬ": ("Кызылординская", "kyzylorda"),
    "КОСТАНАЙСКАЯ ОБЛАСТЬ": ("Костанайская", "kostanay"),
    "МАНГИСТАУСКАЯ ОБЛАСТЬ": ("Мангистауская", "mangystau"),
    "ПАВЛОДАРСКАЯ ОБЛАСТЬ": ("Павлодарская", "pavlodar"),
    "СЕВ-КАЗАХСТАНСКАЯ ОБЛАСТЬ": ("Северо-Казахстанская", "sko"),
    "ТУРКЕСТАНСКАЯ ОБЛАСТЬ": ("Туркестанская", "turkestan"),
    "Г.ШЫМКЕНТ": ("Шымкент", "shymkent"),
    "Г.АЛМАТЫ": ("Алматы", "almaty"),
    "Г.АСТАНА": ("Астана", "astana"),
    "ОБЛАСТЬ ЖЕТІСУ": ("Жетысу", "zhetysu"),
    "ОБЛАСТЬ АБАЙ": ("Абай", "abai"),
    "ОБЛАСТЬ УЛЫТАУ": ("Улытау", "ulytau"),
}

# Расхождение суммы регионов со сводом больше этого означает, что лист прочитан
# неверно: публиковать такое нельзя.
SUMMARY_TOLERANCE = 0.02


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(text: str) -> str:
    """Наименование строки: источник кладёт в ячейку «_x000D_» и переносы."""
    return re.sub(r"\s+", " ", re.sub(r"_x000D_|\r|\n", " ", str(text))).strip()


def bulletins() -> list[dict]:
    """Выпуски бюллетеня, свежие первыми."""
    rows = fetch_json(
        f"{API}?activities={BULLETIN_ACTIVITY}&size=2000", "minfin_bulletins.json"
    )
    if not isinstance(rows, list):
        raise SourceError("список бюллетеней вернулся не списком")
    found = [
        row
        for row in rows
        if re.search(r"бюллетень|bulletin", str(row.get("title") or ""), re.IGNORECASE)
        and (row.get("full_text") or [])
    ]
    if not found:
        raise SourceError("в разделе бюджетного процесса нет бюллетеней")
    found.sort(key=lambda row: row.get("id") or 0, reverse=True)
    return found


def fetch_bulletin(report: dict) -> XlsxBook:
    link = report["full_text"][0].get("document")
    if not link:
        raise SourceError(f"у выпуска {report.get('id')} нет файла")
    path = RAW / f"minfin_bulletin_{report['id']}.bin"
    return XlsxBook(download(SITE + link, path, min_size=100_000, expect="xlsx"))


def parse_period(rows: list[list[str]]) -> tuple[int, int]:
    """Год и число закрытых месяцев из шапки колонки отчёта.

    Подпись выглядит как «2026 ж. қантар-шілде есеп/январь-июль отчет 2026 г.»,
    у январского выпуска второго месяца в диапазоне нет.
    """
    for row in rows[:8]:
        line = clean(" ".join(str(c) for c in row))
        match = re.search(
            r"/\s*([а-яё]+)(?:\s*-\s*([а-яё]+))?\s*отчет\s*(\d{4})", line, re.IGNORECASE
        )
        if not match:
            continue
        last = (match.group(2) or match.group(1)).lower()
        if last not in MONTHS_RU:
            continue
        return int(match.group(3)), MONTHS_RU[last]
    raise SourceError("в листе нет подписи периода")


def sheet_title(rows: list[list[str]]) -> str:
    """Название региона из шапки листа. Номер таблицы внутри листа не совпадает
    с его именем, поэтому опора только на название."""
    for row in rows[:6]:
        value = clean(row[1]) if len(row) > 1 else ""
        if not value or value.upper().startswith("ТАБЛИЦА") or value.startswith("("):
            continue
        if value.upper().startswith("ИСПОЛНЕНИЕ БЮДЖЕТА"):
            continue
        return value
    return ""


def read_income(rows: list[list[str]]) -> tuple[list[dict], float, float]:
    """Категории доходов, итог факта и итог плана. Числа приходят в млн тенге."""
    wanted = dict(INCOME_ROWS)
    by_name = {name.lower(): code for code, name in INCOME_ROWS}
    income: list[dict] = []
    total = plan_total = None
    for row in rows:
        if len(row) <= COL_NAME_RU:
            continue
        label = clean(row[COL_NAME_RU])
        if not label:
            continue
        plan = as_number(row[COL_PLAN])
        fact = as_number(row[COL_FACT])
        if label.upper().startswith(TOTAL_ROW):
            total, plan_total = fact, plan
            continue
        # «Налоговые поступления, в том числе:» и подобные хвосты у части листов.
        head = label.split(",")[0].strip().lower()
        code = by_name.get(head)
        if code is None or fact is None:
            continue
        if any(item["code"] == code for item in income):
            continue
        income.append(
            {
                "code": code,
                "name": wanted[code],
                "plan": round((plan or 0) / 1000, 3),
                "fact": round(fact / 1000, 3),
            }
        )
        if len(income) == len(INCOME_ROWS):
            break
    if total is None:
        raise SourceError("в листе нет строки доходов")
    return income, total / 1000, (plan_total or 0) / 1000


def parse_sheet(book: XlsxBook, path: str, report: dict) -> dict | None:
    rows = list(book.rows(path))
    title = sheet_title(rows)
    if not title:
        return None
    key = title.upper().replace("Ё", "Е")
    if key.startswith(SUMMARY_TITLE):
        income, total, plan = read_income(rows)
        year, months = parse_period(rows)
        return {
            "summary": True,
            "total": total,
            "plan": plan,
            "year": year,
            "months": months,
        }
    named = REGION_NAMES.get(key)
    if named is None:
        raise SourceError(f"незнакомый регион в бюллетене: {title!r}")
    name, slug = named
    income, total, plan = read_income(rows)
    year, months = parse_period(rows)
    taxes = sum(i["fact"] for i in income if i["code"] == "1")
    transfers = sum(i["fact"] for i in income if i["code"] == "5")
    return {
        "kind": "full",
        "name": name,
        "slug": slug,
        "period": f"{year}-{months:02d}",
        "year": year,
        "months": months,
        "published": str(report.get("created_date") or "")[:10],
        "url": f"{DOC_PAGE}/{report['id']}?lang=ru",
        "income": income,
        "total": round(total, 2),
        "plan": round(plan, 2),
        "taxes": round(taxes, 2),
        "transfers": round(transfers, 2),
        "pct": round(total / plan * 100, 1) if plan else None,
    }


def build() -> dict:
    issues: list[str] = []
    last: Exception | None = None
    for report in bulletins()[:4]:
        try:
            book = fetch_bulletin(report)
            regions: list[dict] = []
            summary: dict | None = None
            for name, path in book.sheets:
                if not SHEET_RE.match(name):
                    continue
                parsed = parse_sheet(book, path, report)
                if parsed is None:
                    continue
                if parsed.get("summary"):
                    summary = parsed
                else:
                    regions.append(parsed)
            if len(regions) < len(REGION_NAMES):
                missing = set(n for n, _ in REGION_NAMES.values()) - {
                    r["name"] for r in regions
                }
                raise SourceError(f"в выпуске нет листов: {', '.join(sorted(missing))}")
            if summary:
                collected = sum(r["total"] for r in regions)
                if (
                    abs(collected - summary["total"]) / summary["total"]
                    > SUMMARY_TOLERANCE
                ):
                    raise SourceError(
                        f"сумма регионов {collected:.0f} не сходится со сводом "
                        f"{summary['total']:.0f} млрд"
                    )
            regions.sort(key=lambda r: -r["total"])
            return {
                "generated_at": _now(),
                "source": "Министерство финансов РК, статистический бюллетень",
                "source_url": f"{DOC_PAGE}/{report['id']}?lang=ru",
                "period": regions[0]["period"],
                "year": regions[0]["year"],
                "months": regions[0]["months"],
                "regions": regions,
                "issues": issues,
            }
        except (SourceError, OSError, KeyError, ValueError) as exc:
            last = exc
            issues.append(f"выпуск {report.get('id')}: {exc}")
            continue
    raise SourceError(f"ни один выпуск бюллетеня не разобрался: {last}")


def main() -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    data = build()
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"регионов собрано: {len(data['regions'])} из {len(REGION_NAMES)}, период {data['period']}"
    )
    for region in data["regions"]:
        print(
            f"   {region['name'][:26]:28} доходы {region['total']:8.1f} млрд, "
            f"налоги {region['taxes']:7.1f}, трансферты {region['transfers']:7.1f}, "
            f"план {region['pct']}%"
        )
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")


if __name__ == "__main__":
    main()
