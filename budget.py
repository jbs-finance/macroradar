"""Поступления налогов в бюджет Казахстана по данным Комитета госдоходов.

Два среза: помесячная динамика в разрезе областей и структура по видам налогов.
Оба лежат в таблицах на сайте КГД, свежесть у них разная и отстаёт от текущего
месяца, поэтому период каждого среза подписывается на странице явно.

Две особенности источника, из-за которых код выглядит именно так:

1. У kgd.gov.kz в цепочке самоподписанный сертификат. Стандартный клиент Python
   его отвергает, поэтому файлы качаются через curl, который берёт системное
   хранилище корней. Отключать проверку сертификата нельзя: данные идут на
   публичную страницу, и подмена по дороге не должна быть возможной.
2. Таблицы приходят в xlsx, то есть zip с XML. Разбирается стандартной
   библиотекой, сторонние пакеты не нужны.

Запуск: .venv/bin/python budget.py out/budget.json
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DEFAULT_DATASET = HERE / "out" / "budget.json"

KGD = "https://kgd.gov.kz"
DYNAMICS_PAGE = f"{KGD}/ru/content/dinamika-postupleniy-nalogov-i-platezhey-v-gosudarstvennyy-byudzhet-1"
FACT_PAGE = (
    f"{KGD}/ru/content/fakticheskie-postupleniya-po-nalogam-i-platezham-"
    "v-gosudarstvennyy-byudzhet-za-2002-2025-gg"
)

MONTHS = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

# Коды бюджетной классификации верхнего уровня. Берём только их: подстатьи дают
# сотни строк, а на странице нужен читаемый разрез из десятка позиций.
TAX_CODES = {
    "101": "Подоходный налог",
    "103": "Социальный налог",
    "104": "Налоги на собственность",
    "105": "НДС, акцизы и прочие внутренние налоги",
    "106": "Налоги на международную торговлю",
    "107": "Прочие налоги",
    "108": "Обязательные платежи и госпошлина",
}


class SourceError(RuntimeError):
    pass


def fetch_file(url: str, name: str, max_age_days: int = 7) -> bytes:
    """Скачивание через curl: сертификат сайта не проходит проверку у Python."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    if path.exists() and path.stat().st_size > 1000:
        age = (datetime.now().timestamp() - path.stat().st_mtime) / 86400
        if age < max_age_days:
            return path.read_bytes()
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "180", url, "-o", str(path)],
        capture_output=True,
    )
    if result.returncode != 0 or not path.exists() or path.stat().st_size < 1000:
        raise SourceError(f"{url}: curl вернул {result.returncode}")
    return path.read_bytes()


# --- Разбор xlsx стандартной библиотекой -------------------------------------


class Workbook:
    def __init__(self, raw: bytes):
        if raw[:2] != b"PK":
            raise SourceError("файл не является xlsx")
        self.zip = zipfile.ZipFile(io.BytesIO(raw))
        shared = (
            self.zip.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
            if "xl/sharedStrings.xml" in self.zip.namelist()
            else ""
        )
        self.strings = [
            "".join(re.findall(r"<t[^>]*>([^<]*)</t>", si))
            for si in re.findall(r"<si>(.*?)</si>", shared, re.DOTALL)
        ]
        wb = self.zip.read("xl/workbook.xml").decode("utf-8", "ignore")
        rels = dict(
            re.findall(
                r'Id="(rId\d+)"[^>]*Target="([^"]+)"',
                self.zip.read("xl/_rels/workbook.xml.rels").decode("utf-8", "ignore"),
            )
        )
        self.sheets = [
            (name, "xl/" + rels[rid].lstrip("/").replace("xl/", ""))
            for name, rid in re.findall(
                r'<sheet name="([^"]+)"[^>]*r:id="(rId\d+)"', wb
            )
            if rid in rels
        ]

    @property
    def modified(self) -> str:
        """Дата последней правки книги: по ней проверяется, тот ли это период.

        В таблице КГД встречаются ссылки на прошлогодний файл, и без этой проверки
        цифры позапрошлого апреля уехали бы на страницу как свежие."""
        if "docProps/core.xml" not in self.zip.namelist():
            return ""
        core = self.zip.read("docProps/core.xml").decode("utf-8", "ignore")
        m = re.search(r"<dcterms:modified[^>]*>([^<]+)<", core)
        return m.group(1)[:10] if m else ""

    def cell(self, chunk: str) -> str:
        m = re.search(r"<v>([^<]*)</v>", chunk)
        if not m:
            inline = re.search(r"<is>.*?<t[^>]*>([^<]*)</t>", chunk, re.DOTALL)
            return inline.group(1) if inline else ""
        value = m.group(1)
        if 't="s"' in chunk and value.isdigit() and int(value) < len(self.strings):
            return self.strings[int(value)]
        return value

    def rows(self, path: str) -> list[list[str]]:
        """Строки листа с сохранением номеров колонок.

        Пустые ячейки в файле просто отсутствуют, и если складывать найденные
        подряд, колонки съезжают влево: в отчётах, где коды классификации идут
        тремя колонками и заполнены через одну, наименование уезжает на место
        кода. Поэтому каждая ячейка кладётся по своему адресу из атрибута r."""
        sheet = self.zip.read(path).decode("utf-8", "ignore")
        out = []
        for row in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.DOTALL):
            cells: list[str] = []
            for chunk in re.findall(r"<c[^>]*>.*?</c>|<c[^>]*/>", row, re.DOTALL):
                ref = re.search(r'\sr="([A-Z]+)\d+"', chunk)
                index = column_index(ref.group(1)) if ref else len(cells)
                index = max(index, len(cells))
                cells += [""] * (index - len(cells))
                cells.append(self.cell(chunk).strip())
            out.append(cells)
        return out


def column_index(letters: str) -> int:
    """A -> 0, B -> 1, AA -> 26."""
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def as_number(raw: str) -> float | None:
    try:
        return float(raw.replace(" ", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


# --- Помесячная динамика в разрезе областей -----------------------------------


def dynamics_links(page: str) -> list[tuple[str, int]]:
    """Ссылки на годовые файлы динамики, свежие первыми."""
    found: dict[int, str] = {}
    for url, label in re.findall(
        r'<a[^>]*href="([^"]+\.xls\w?)"[^>]*>(.*?)</a>', page, re.DOTALL | re.IGNORECASE
    ):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", label))
        m = re.search(r"в (\d{4}) году", text)
        if not m:
            continue
        found.setdefault(int(m.group(1)), url)
    if not found:
        raise SourceError("на странице динамики нет ссылки с годом")
    return [(url, year) for year, url in sorted(found.items(), reverse=True)]


def parse_dynamics(rows: list[list[str]]) -> dict:
    """Строка «ДОХОДЫ, всего» и строки областей, колонки это месяцы.

    Значения в файле указаны в тысячах тенге, приводим к миллиардам: на странице
    сравниваются масштабы, а не платёжки."""
    header_idx = next(
        (
            i
            for i, r in enumerate(rows)
            if r and r[0].strip().lower().startswith("январь")
        ),
        None,
    )
    if header_idx is None:
        raise SourceError("в файле динамики нет строки с месяцами")
    months = [c for c in rows[header_idx] if c][:12]

    total: list[float] = []
    regions: list[dict] = []
    for row in rows[header_idx + 1 :]:
        if not row or not row[0]:
            continue
        name = row[0].strip()
        values = [as_number(c) for c in row[1 : 1 + len(months)]]
        values = [v / 1e6 if v is not None else None for v in values]
        if not any(v for v in values):
            continue
        if name.upper().startswith("ДОХОДЫ"):
            total = values
        elif not name.lower().startswith("в том числе"):
            regions.append({"name": name, "values": values})
    if not total:
        raise SourceError("в файле динамики нет строки «ДОХОДЫ, всего»")
    return {"months": months, "total": total, "regions": regions}


def fetch_dynamics() -> dict:
    """Свежий год помесячно плюс предыдущий: без базы сравнения график ни о чём."""
    page = fetch_file(DYNAMICS_PAGE, "kgd_dynamics_page.html", max_age_days=7).decode(
        "utf-8", "ignore"
    )
    links = dynamics_links(page)
    url, year = links[0]
    raw = fetch_file(url, f"kgd_dynamics_{year}.bin", max_age_days=7)
    data = parse_dynamics(Workbook(raw).rows("xl/worksheets/sheet1.xml"))
    data["year"] = year
    data["source_url"] = DYNAMICS_PAGE
    data["previous"] = None
    if len(links) > 1:
        prev_url, prev_year = links[1]
        try:
            prev_raw = fetch_file(prev_url, f"kgd_dynamics_{prev_year}.bin")
            prev = parse_dynamics(Workbook(prev_raw).rows("xl/worksheets/sheet1.xml"))
            prev["year"] = prev_year
            data["previous"] = prev
        except (SourceError, OSError):
            pass
    return data


# --- Структура по видам налогов ------------------------------------------------


def fact_links(page: str) -> list[tuple[str, int, int]]:
    """Ссылки на месячные файлы, свежие первыми: (url, год, месяц)."""
    found: dict[tuple[int, int], str] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if not cells:
            continue
        year_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cells[0])).strip()
        m = re.match(r"^(20\d\d)", year_text)
        if not m:
            continue
        year = int(m.group(1))
        for url, label in re.findall(
            r'<a[^>]*href="([^"]+\.xls\w?)"[^>]*>(.*?)</a>',
            row,
            re.DOTALL | re.IGNORECASE,
        ):
            name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", label)).strip().lower()
            if name.capitalize() not in MONTHS:
                continue
            month = MONTHS.index(name.capitalize()) + 1
            found.setdefault((year, month), url)
    if not found:
        raise SourceError("на странице фактических поступлений нет ссылок по месяцам")
    return [(url, y, m) for (y, m), url in sorted(found.items(), reverse=True)]


def sheet_layout(rows: list[list[str]]) -> tuple[int, int]:
    """Индексы колонки «ГБ» и первой колонки наименования.

    Коды классификации разложены по нескольким колонкам и заполнены через одну,
    поэтому позиции берутся из шапки, а не из порядка ячеек."""
    for row in rows[:8]:
        for i, cell in enumerate(row):
            if cell.strip().upper() == "ГБ":
                name_idx = next(
                    (j for j, c in enumerate(row) if "аименование" in c), i - 1
                )
                return i, name_idx
    raise SourceError("в листе нет колонки «ГБ»")


def row_code(row: list[str], name_idx: int) -> str:
    """Код строки: первая непустая ячейка до колонки наименования."""
    for cell in row[:name_idx]:
        code = cell.strip()
        if code:
            return code
    return ""


def sheet_total(book: Workbook, path: str) -> float:
    """Строка «Налоговые поступления» листа, в тысячах тенге."""
    rows = book.rows(path)
    try:
        value_idx, name_idx = sheet_layout(rows)
    except SourceError:
        return 0.0
    for row in rows:
        if len(row) > value_idx and row_code(row, name_idx) == "1":
            if "оступлен" in row[name_idx]:
                return as_number(row[value_idx]) or 0.0
    return 0.0


def summary_sheet(book: Workbook) -> str | None:
    """Путь к сводному листу, если он в книге есть.

    Кроме свода в книге лежат листы отдельных органов, и свод повторяет их сумму:
    сложить всё вместе значит удвоить бюджет страны. Подписан свод в разные месяцы
    по-разному («Республика в целом», «по Республике Казахстан»), поэтому ищется он
    по структуре: итог свода равен сумме остальных листов."""
    totals = [(path, sheet_total(book, path)) for _, path in book.sheets]
    grand = sum(v for _, v in totals)
    for path, value in totals:
        if value > 0 and abs(grand - 2 * value) / value < 0.01:
            return path
    return None


def parse_fact(book: Workbook) -> list[dict]:
    """Разрез по видам налогов, нарастающим итогом с начала года.

    Берутся только подстатьи (код от шести знаков) с группировкой по первым трём
    цифрам: строки верхнего уровня есть не во всех месяцах, а где есть, там они
    повторяют сумму своих подстатей."""
    summary = summary_sheet(book)
    paths = [summary] if summary else [path for _, path in book.sheets]
    totals: dict[str, float] = {}
    for path in paths:
        rows = book.rows(path)
        value_idx, name_idx = sheet_layout(rows)
        for row in rows:
            if len(row) <= value_idx:
                continue
            code = row_code(row, name_idx)
            if not code.isdigit() or len(code) < 6:
                continue
            group = code[:3]
            if group not in TAX_CODES:
                continue
            value = as_number(row[value_idx])
            if value:
                totals[group] = totals.get(group, 0.0) + value / 1e6
    if not totals:
        raise SourceError("в книге не нашлось подстатей налоговых кодов")
    items = [
        {"code": code, "name": TAX_CODES[code], "value": round(value, 2)}
        for code, value in totals.items()
    ]
    items.sort(key=lambda i: -i["value"])
    return items


def period_matches(modified: str, year: int, month: int) -> bool:
    """Правдоподобна ли дата правки файла для заявленного периода.

    Отчёт публикуется после закрытия месяца, но не позже чем через год. Файл,
    правленный до конца отчётного месяца, это чужой период: в таблице КГД такие
    ссылки встречаются."""
    if len(modified) < 7:
        return False
    stamp = modified[:7]
    start = f"{year}-{month:02d}"
    end_year, end_month = (year + 1, month) if month < 12 else (year + 1, 12)
    return start <= stamp <= f"{end_year}-{end_month:02d}"


def fetch_structure() -> dict:
    page = fetch_file(FACT_PAGE, "kgd_fact_page.html", max_age_days=7).decode(
        "utf-8", "ignore"
    )
    skipped: list[str] = []
    for url, year, month in fact_links(page)[:6]:
        book = Workbook(fetch_file(url, f"kgd_fact_{year}_{month:02d}.bin"))
        if not period_matches(book.modified, year, month):
            skipped.append(f"{year}-{month:02d} (файл от {book.modified or '?'})")
            continue
        items = parse_fact(book)
        summary = summary_sheet(book)
        declared = (
            sheet_total(book, summary) / 1e6
            if summary
            else sum(sheet_total(book, p) for _, p in book.sheets) / 2e6
        )
        collected = sum(i["value"] for i in items)
        # Коды 101-108 не покрывают все налоговые поступления, но должны давать
        # основную часть: расхождение больше пятой части значит сбой разбора.
        if declared and abs(collected - declared) / declared > 0.2:
            raise SourceError(
                f"разрез не сходится с итогом файла: {collected:.0f} против {declared:.0f}"
            )
        return {
            "period": f"{year}-{month:02d}",
            "year": year,
            "months": month,
            "items": items,
            "declared_total": round(declared, 2),
            "file_modified": book.modified,
            "skipped": skipped,
            "source_url": FACT_PAGE,
        }
    raise SourceError(f"ни один месячный файл не подтверждён датой: {skipped}")


def build() -> dict:
    issues: list[str] = []
    dynamics = None
    structure = None
    try:
        dynamics = fetch_dynamics()
    except (SourceError, OSError) as exc:
        issues.append(f"динамика поступлений: {exc}")
    try:
        structure = fetch_structure()
    except (SourceError, OSError) as exc:
        issues.append(f"структура поступлений: {exc}")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Комитет государственных доходов МФ РК",
        "dynamics": dynamics,
        "structure": structure,
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
    # Источник отвечает не всегда: прошлый срез лучше пустого блока.
    for key in ("dynamics", "structure"):
        if data[key] is None and previous.get(key):
            data[key] = {**previous[key], "stale": True}
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if data["dynamics"]:
        d = data["dynamics"]
        print(
            f"динамика: {d['year']} год, месяцев {len(d['months'])}, областей {len(d['regions'])}"
        )
    if data["structure"]:
        s = data["structure"]
        print(f"структура: {s['period']}, позиций {len(s['items'])}")
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")


if __name__ == "__main__":
    main()
