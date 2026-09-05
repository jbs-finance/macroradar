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
    ("shymkent-karzhy", "Шымкент"),
]

# «на 1 августа 2026 года» и «на 01.08.2026г.» встречаются одинаково часто.
DATE_WORDS = re.compile(r"на\s+1\s+(\w+)\s+(\d{4})", re.IGNORECASE)
DATE_DIGITS = re.compile(r"на\s+0?1[.\-/](\d{1,2})[.\-/](\d{4})")
IS_REPORT = re.compile(r"(отчет|отчёт|исполнени)", re.IGNORECASE)
NOT_REPORT = re.compile(
    r"(гражданск|паспорт|аналитическ|антикоррупц|протокол|кассовом исполнении)",
    re.IGNORECASE,
)

MAX_PAGES = 8
MIN_INCOME = 5.0  # млрд тенге: меньше бывает только у отчёта одного учреждения
MIN_CATEGORIES = 3  # разобрана хотя бы половина категорий доходов
MAX_AGE_MONTHS = 18  # отчёт старше полутора лет уже не «свежая картина»


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


def latest_report(slug: str) -> dict:
    """Свежий отчёт региона: карточка документа с периодом."""
    best: dict | None = None
    for page in range(MAX_PAGES):
        chunk = api_json(f"{API}?projects={slug}&size=100&page={page}")
        if not chunk:
            break
        for row in chunk:
            period = parse_period(row.get("title") or "")
            if not period:
                continue
            files = [f for f in (row.get("full_text") or []) if f.get("document")]
            if not files:
                continue
            candidate = {
                "id": row.get("id"),
                "year": period[0],
                "months": period[1],
                "title": (row.get("title") or "").strip(),
                "published": (row.get("created_date") or "")[:10],
                # Ссылка на файл берётся из списка: карточка документа у областей
                # приходит пустой, в отличие от документов Минфина.
                "document": files[0]["document"],
            }
            if best is None or (candidate["year"], candidate["months"]) > (
                best["year"],
                best["months"],
            ):
                best = candidate
        if len(chunk) < 100:
            break
    if best is None:
        raise SourceError("нет отчётов об исполнении бюджета")
    return best


def download(slug: str, report: dict) -> bytes:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"oblast_{slug}_{report['year']}_{report['months']:02d}.bin"
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
    if raw[:2] == b"PK" and b"xl/workbook.xml" not in raw[:4000]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            return
        for info in archive.infolist():
            if not info.file_size:
                continue
            inner = archive.read(info.filename)
            yield from books(inner)
        return
    try:
        if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            yield XlsBook(raw)
        elif raw[:2] == b"PK":
            yield XlsxBook(raw)
    except (XlsError, SourceError, KeyError, ValueError, zipfile.BadZipFile):
        return


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
    taxes = sum(i["fact"] for i in income if i["code"] == "1")
    transfers = sum(i["fact"] for i in income if "рансферт" in i["name"])
    plan = sum(i["plan"] for i in income)
    return {
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
        "own_share": round((total - transfers) / total * 100, 1) if total else None,
        "pct": round(total / plan * 100, 1) if plan else None,
    }


def too_old(year: int, months: int) -> bool:
    today = datetime.now(timezone.utc)
    age = (today.year - year) * 12 + today.month - months
    return age > MAX_AGE_MONTHS


def fetch_region(slug: str, name: str) -> dict:
    report = latest_report(slug)
    if too_old(report["year"], report["months"]):
        raise SourceError(
            f"свежих отчётов нет, последний за {report['year']}-{report['months']:02d}"
        )
    raw = download(slug, report)
    best: dict | None = None
    for book in books(raw):
        income = read_income(book)
        if not income:
            continue
        summary = summarize(income, name, report, slug)
        # Форма могла разобраться наполовину: без налогов или с одной категорией
        # цифры выглядят правдоподобно, но врут.
        if len(income) < MIN_CATEGORIES or summary["total"] < MIN_INCOME:
            continue
        if not summary["taxes"] or summary["taxes"] > summary["total"]:
            continue
        # В архиве лежит и бюджет области целиком, и отдельно областной без районов.
        # Нужен первый: он больше.
        if best is None or summary["total"] > best["total"]:
            best = summary
    if best is None:
        raise SourceError("в файле нет разбираемого отчёта об исполнении")
    return best


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
