"""Исполнение бюджетов областей по отчётам областных управлений финансов.

Минфин публикует местные бюджеты только сводно по стране, а разбивку по областям
каждое управление выкладывает у себя на gov.kz. Поэтому здесь обход разделов
областей: у каждого свой адрес, своя формулировка заголовка и свой ритм публикации.

Три особенности источника, из-за которых код выглядит именно так:

1. Файлы приходят в zip, а внутри старый формат Excel (BIFF), который читается
   модулем xls. Встречается и xlsx, поэтому формат определяется по сигнатуре.
2. В архиве обычно два отчёта: бюджет области целиком и отдельно областной
   бюджет без районов. Нужен первый, он опознаётся по большим доходам.
3. Регионы отчитываются вразнобой: часть публикует помесячно, часть отстала на
   год. Период каждого региона подписывается отдельно, общий рейтинг из таких
   цифр не строится.

Запуск: .venv/bin/python oblast.py out/oblast.json
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from budget import SourceError, as_number
from budget import Workbook as XlsxBook
from minfin import MONTHS_RU, parse_income, report_layout
from struct import error as struct_error

from xls import Workbook as XlsBook
from xls import XlsError

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DEFAULT_DATASET = HERE / "out" / "oblast.json"

SITE = "https://www.gov.kz"
API = f"{SITE}/api/v1/public/content-manager/documents"
DOC_PAGE = f"{SITE}/memleket/entities"

# Адреса разделов управлений финансов. Единого правила в них нет, поэтому список
# собран перебором: у кого-то «-karzhy», у кого-то «-finance».
REGIONS = [
    ("aqmola-karzhy", "Акмолинская"),
    ("aktobe-karzhy", "Актюбинская"),
    ("atyrau-karzhy", "Атырауская"),
    ("bko-karzhy", "Западно-Казахстанская"),
    ("vko-karzhy", "Восточно-Казахстанская"),
    ("zhambyl-karzhy", "Жамбылская"),
    ("karaganda-finance", "Карагандинская"),
    ("kostanai-karzhy", "Костанайская"),
    ("mangystau-fin", "Мангистауская"),
    ("pavlodar-karzhy", "Павлодарская"),
    ("sko-karzhy", "Северо-Казахстанская"),
    ("turkestan-karzhy", "Туркестанская"),
    ("abay-finance", "Абай"),
    ("ulytau-finance", "Улытау"),
    ("zhetysu-finance", "Жетысу"),
    ("astana-karzhy", "Астана"),
    ("almaty-finance-econom", "Алматы"),
    ("shymkent-karzhy", "Шымкент"),
    ("almobl-karzhy", "Алматинская"),
    # Раздел есть, но документов управление пока не публикует: пусть подхватится
    # само, когда появятся.
    ("kyzylorda-karzhy", "Кызылординская"),
]

# «на 1 августа 2026 года» и «на 01.08.2026г.» встречаются одинаково часто.
DATE_WORDS = re.compile(r"на\s+1\s+(\w+)\s+(\d{4})", re.IGNORECASE)
DATE_DIGITS = re.compile(r"на\s+0?1[.\-/](\d{1,2})[.\-/](\d{4})")
IS_REPORT = re.compile(r"(отчет|отчёт|исполнени)", re.IGNORECASE)
NOT_REPORT = re.compile(
    r"(гражданск|паспорт|аналитическ|антикоррупц|протокол|кассовом исполнении)",
    re.IGNORECASE,
)
PRESENTATION_TITLE = re.compile(r"гражданский\s+бюджет", re.IGNORECASE)

MAX_PAGES = 8
MIN_INCOME = 5.0  # млрд тенге: меньше бывает только у отчёта одного учреждения
MIN_CATEGORIES = 3  # разобрана хотя бы половина категорий доходов
MAX_AGE_MONTHS = 18  # отчёт старше полутора лет уже не «свежая картина»
MAX_CANDIDATES = 6  # сколько документов региона пробовать, прежде чем сдаться


def api_json(url: str, timeout: int = 45):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        raise SourceError(f"{url}: {exc}") from exc


def parse_period(title: str) -> tuple[int, int] | None:
    """Отчётная дата из заголовка: «на 1 августа 2026» -> покрытый период."""
    if NOT_REPORT.search(title) or not IS_REPORT.search(title):
        return None
    return date_period(title)


def presentation_period(title: str) -> tuple[int, int] | None:
    """Период презентации «Гражданский бюджет» Алматы."""
    if not PRESENTATION_TITLE.search(title):
        return None
    return date_period(title)


def date_period(title: str) -> tuple[int, int] | None:
    """Период отчёта из даты в заголовке."""
    m = DATE_WORDS.search(title)
    if m:
        month = MONTHS_RU.get(m.group(1).lower())
        year = int(m.group(2))
    else:
        m = DATE_DIGITS.search(title)
        if not m:
            return None
        month, year = int(m.group(1)), int(m.group(2))
    if not month or not 1 <= month <= 12:
        return None
    # Отчёт «на 1 августа» покрывает январь-июль.
    return (year - 1, 12) if month == 1 else (year, month - 1)


def region_reports(slug: str) -> list[dict]:
    """Отчёты региона со свежих, по одному на период.

    Перебор нужен потому, что в один месяц управление выкладывает и таблицу, и
    текстовую справку, и презентацию: разобрать удаётся не первое попавшееся."""
    found: list[dict] = []
    for page in range(MAX_PAGES):
        chunk = api_json(f"{API}?projects={slug}&size=100&page={page}")
        if not chunk:
            break
        for row in chunk:
            title = row.get("title") or ""
            period = parse_period(title)
            if slug == "almaty-finance-econom" and not period:
                period = presentation_period(title)
            if not period:
                continue
            files = [f for f in (row.get("full_text") or []) if f.get("document")]
            if not files:
                continue
            candidate = {
                "id": row.get("id"),
                "year": period[0],
                "months": period[1],
                "title": title.strip(),
                "published": (row.get("created_date") or "")[:10],
                # Ссылка на файл берётся из списка: карточка документа у областей
                # приходит пустой, в отличие от документов Минфина.
                "document": files[0]["document"],
            }
            found.append(candidate)
        if len(chunk) < 100:
            break
    if not found:
        raise SourceError("нет отчётов об исполнении бюджета")
    found.sort(key=lambda c: (c["year"], c["months"], c["published"]), reverse=True)
    return found[:MAX_CANDIDATES]


def download(slug: str, report: dict) -> bytes:
    RAW.mkdir(parents=True, exist_ok=True)
    # В имени нужен идентификатор документа: за один месяц управление выкладывает
    # и таблицу, и справку, и презентацию, а кэш по месяцу оставлял только первую.
    path = RAW / f"oblast_{slug}_{report['year']}_{report['months']:02d}_{report['id']}.bin"
    if path.exists() and path.stat().st_size > 3000:
        return path.read_bytes()
    result = subprocess.run(
        [
            "curl",
            "-sL",
            "--max-time",
            "180",
            SITE + report["document"],
            "-o",
            str(path),
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not path.exists() or path.stat().st_size < 3000:
        raise SourceError(f"curl вернул {result.returncode}")
    return path.read_bytes()


def books(raw: bytes):
    """Книги внутри вложения: файл может быть архивом, xls или xlsx."""
    if raw[:2] == b"PK":
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
            names = archive.namelist()
        except zipfile.BadZipFile:
            return
        # Книгу от простого архива отличает содержимое, а не первые байты: у части
        # файлов запись xl/workbook.xml лежит дальше начала, и они уходили в разбор
        # как архив, теряясь целиком.
        if "xl/workbook.xml" in names:
            try:
                yield XlsxBook(raw)
            except (SourceError, KeyError, ValueError, zipfile.BadZipFile):
                pass
            return
        for info in archive.infolist():
            if info.file_size:
                yield from books(archive.read(info.filename))
        return
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        try:
            yield XlsBook(raw)
        except (XlsError, KeyError, ValueError, struct_error):
            return


# --- Текстовые отчёты в Word ---------------------------------------------------

WORD_TEXT = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")
PPTX_TEXT = re.compile(r"<a:t[^>]*>([^<]*)</a:t>")
# Форматирование рвёт числа пробелами: «7 25 , 6» это 725,6, а «202 6» это 2026.
GLUED = re.compile(r"(?<=\d)\s+(?=[\d,])|(?<=,)\s+(?=\d)")

BILLIONS = r"([\d]+(?:[.,]\d+)?)\s*млрд"
TOTAL_PATTERN = re.compile(
    r"плане на отчетный период по поступлениям\s*"
    + BILLIONS
    + r".{0,80}?исполнение составило\s*"
    + BILLIONS,
    re.IGNORECASE | re.DOTALL,
)
OWN_PATTERN = re.compile(
    r"собственные доходы при плане на отчетный период\s*"
    + BILLIONS
    + r".{0,80}?исполнены на\s*"
    + BILLIONS,
    re.IGNORECASE | re.DOTALL,
)
PRESENTATION_NUMBER = r"([\d\s]+(?:[.,]\s*\d+)?)"
PRESENTATION_INCOME = re.compile(PRESENTATION_NUMBER + r"\s+ДОХОДЫ\b", re.IGNORECASE)
PRESENTATION_TAXES = re.compile(
    r"Налоговые\s+поступления\s+" + PRESENTATION_NUMBER, re.IGNORECASE
)
PRESENTATION_TRANSFERS = re.compile(r"Трансферты\s+" + PRESENTATION_NUMBER, re.IGNORECASE)
PRESENTATION_MILLIONS = re.compile(r"МЛН\.?\s*ТЕНГЕ", re.IGNORECASE)


def word_text(raw: bytes) -> str:
    """Плоский текст документа Word с починенными числами."""
    try:
        document = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        return ""
    plain = " ".join(WORD_TEXT.findall(document.decode("utf-8", "ignore")))
    return GLUED.sub("", " ".join(plain.split()))


def parse_word_report(raw: bytes) -> dict | None:
    """Часть управлений публикует исполнение бюджета прозой, без таблиц.

    Берутся всего две величины, зато проверяемые: поступления всего и собственные
    доходы, каждая со своим планом. Если формулировка поменяется, разбор просто
    ничего не найдёт, и регион выпадет из списка вместо того, чтобы показать чушь."""
    text = word_text(raw)
    if not text:
        return None
    total = TOTAL_PATTERN.search(text)
    if not total:
        return None
    plan = as_number(total.group(1))
    fact = as_number(total.group(2))
    if not plan or not fact or not 0.3 < fact / plan < 3:
        return None
    own = OWN_PATTERN.search(text)
    own_fact = as_number(own.group(2)) if own else None
    return {
        "kind": "brief",
        "total": round(fact, 2),
        "plan": round(plan, 2),
        "taxes": round(own_fact, 2) if own_fact and own_fact <= fact else None,
    }


def parse_pptx_report(raw: bytes) -> dict | None:
    """Доходы Алматы из презентации «Гражданский бюджет».

    Управление публикует таблицу доходов только в PPTX. Берутся три явно
    подписанные величины, без попытки читать диаграммы или расходы.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        slides = [name for name in archive.namelist() if name.startswith("ppt/slides/")]
    except zipfile.BadZipFile:
        return None
    for name in slides:
        text = " ".join(PPTX_TEXT.findall(archive.read(name).decode("utf-8", "ignore")))
        if (
            "СТРУКТУРА ПОСТУПЛЕНИЙ" not in text.upper()
            or not PRESENTATION_MILLIONS.search(text)
        ):
            continue
        income = PRESENTATION_INCOME.search(text)
        taxes = PRESENTATION_TAXES.search(text)
        transfers = PRESENTATION_TRANSFERS.search(text)
        if not income or not taxes or not transfers:
            continue
        total = as_number(GLUED.sub("", income.group(1)))
        tax_total = as_number(GLUED.sub("", taxes.group(1)))
        transfer_total = as_number(GLUED.sub("", transfers.group(1)))
        if (
            not total
            or not tax_total
            or transfer_total is None
            or total < MIN_INCOME
            or tax_total + transfer_total > total * 1.001
        ):
            continue
        return {
            "kind": "full",
            "total": round(total / 1000, 2),
            "plan": None,
            "taxes": round(tax_total / 1000, 2),
            "transfers": round(transfer_total / 1000, 2),
            "pct": None,
        }
    return None


def read_income(book) -> list[dict] | None:
    """Категории доходов из первого листа книги, если это отчёт об исполнении."""
    for _, path in book.sheets:
        try:
            rows = book.rows(path)
            income = parse_income(rows, report_layout(rows))
        except (SourceError, StopIteration, ValueError, IndexError):
            continue
        if income:
            return income
    return None


def summarize(income: list[dict], name: str, report: dict, slug: str) -> dict:
    total = sum(i["fact"] for i in income)
    income = income or []
    taxes = sum(i["fact"] for i in income if i["code"] == "1")
    transfers = sum(i["fact"] for i in income if "рансферт" in i["name"])
    plan = sum(i["plan"] for i in income)
    # Часть управлений публикует только налоговую часть доходов: тогда это не
    # «доходы региона», и подавать их как доходы нельзя.
    kind = "full" if len(income) >= MIN_CATEGORIES else "taxes"
    if kind == "taxes":
        # Показывается налоговая часть, значит и процент должен быть по ней, а не
        # по случайному набору разобравшихся категорий.
        plan = sum(i["plan"] for i in income if i["code"] == "1")
        total = taxes
    return {
        "kind": kind,
        "name": name,
        "slug": slug,
        "period": f"{report['year']}-{report['months']:02d}",
        "year": report["year"],
        "months": report["months"],
        "published": report["published"],
        "url": f"{DOC_PAGE}/{slug}/documents/details/{report['id']}?lang=ru",
        "income": income,
        "total": round(total, 2),
        "plan": round(plan, 2),
        "taxes": round(taxes, 2),
        "transfers": round(transfers, 2),
        "own_share": (
            round((total - transfers) / total * 100, 1)
            if total and kind == "full"
            else None
        ),
        "pct": round(total / plan * 100, 1) if plan else None,
    }


def too_old(year: int, months: int) -> bool:
    today = datetime.now(timezone.utc)
    age = (today.year - year) * 12 + today.month - months
    return age > MAX_AGE_MONTHS


def read_report(slug: str, report: dict, name: str) -> dict | None:
    """Разбор одного документа: None, если форма не та."""
    raw = download(slug, report)
    best: dict | None = None
    for book in books(raw):
        income = read_income(book)
        if not income:
            continue
        summary = summarize(income, name, report, slug)
        if summary["total"] < MIN_INCOME or not summary["taxes"]:
            continue
        if summary["taxes"] > summary["total"] * 1.001:
            continue
        # В архиве лежит и бюджет области целиком, и отдельно областной без районов.
        # Нужен первый: он больше.
        if best is None or summary["total"] > best["total"]:
            best = summary
    return best


def fetch_region(slug: str, name: str) -> dict:
    candidates = region_reports(slug)
    fresh = [c for c in candidates if not too_old(c["year"], c["months"])]
    if not fresh:
        newest = candidates[0]
        raise SourceError(
            f"свежих отчётов нет, последний за {newest['year']}-{newest['months']:02d}"
        )
    for report in fresh:
        try:
            summary = read_report(slug, report, name)
        except (SourceError, OSError):
            continue
        if summary:
            return summary
    for report in fresh:
        try:
            brief = parse_word_report(download(slug, report))
        except (SourceError, OSError):
            continue
        if brief:
            return {**summarize([], name, report, slug), **brief, "income": []}
    for report in fresh:
        if slug != "almaty-finance-econom":
            continue
        try:
            presentation = parse_pptx_report(download(slug, report))
        except (SourceError, OSError):
            continue
        if presentation:
            return {**summarize([], name, report, slug), **presentation, "income": []}
    raise SourceError("ни один из документов не удалось разобрать")


def build() -> dict:
    regions: list[dict] = []
    issues: list[str] = []
    for slug, name in REGIONS:
        try:
            regions.append(fetch_region(slug, name))
        except (SourceError, OSError) as exc:
            issues.append(f"{name}: {exc}")
    regions.sort(key=lambda r: -r["total"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Управления финансов областей, gov.kz",
        "regions": regions,
        "issues": issues,
    }


def main() -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    data = build()
    previous = {}
    if dataset.exists():
        try:
            previous = json.loads(dataset.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
    # Регион, который сегодня не ответил, остаётся с прошлым срезом и пометкой.
    have = {r["slug"] for r in data["regions"]}
    for old in previous.get("regions", []):
        if old["slug"] in have or too_old(old["year"], old["months"]):
            continue
        data["regions"].append({**old, "stale": True})
    data["regions"].sort(key=lambda r: -r["total"])

    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"регионов собрано: {len(data['regions'])} из {len(REGIONS)}")
    for region in data["regions"]:
        print(
            f"   {region['name'][:26]:28} {region['period']}  доходы {region['total']:8.1f} "
            f"млрд, налоги {region['taxes']:7.1f}, трансферты {region['transfers']:7.1f}"
        )
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")


if __name__ == "__main__":
    main()
