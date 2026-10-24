"""Поступления налогов в бюджет Казахстана по данным Комитета госдоходов.

Два среза: помесячная динамика в разрезе областей и структура по видам налогов.
Оба лежат в таблицах КГД в каталоге gov.kz, свежесть у них разная и отстаёт от текущего
месяца, поэтому период каждого среза подписывается на странице явно.

Две особенности источника, из-за которых код выглядит именно так:

1. Список документов берётся из публичного API gov.kz: прежние страницы kgd.gov.kz
   теперь перенаправляют на главную и больше не содержат ссылок на отчёты.
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

# Ошибка источника одна на все модули: у оболочек разные импорты, и две разные
# исключения с одним именем расходились по except мимо друг друга.
from etl import SourceError, fetch_json

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DEFAULT_DATASET = HERE / "out" / "budget.json"

KGD = "https://www.gov.kz"
KGD_DOCUMENTS_API = f"{KGD}/api/v1/public/content-manager/documents"
KGD_ORG_ID = 1062
KGD_STATS_PAGE = f"{KGD}/org/kgd/activities/655?lang=ru"
KGD_LISTING_MAX_BODY = 16 * 1024 * 1024

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


XLSX_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# Часть управлений выкладывает вложения в 7z. Разобрать его нечем, но это файл
# источника, а не страница ошибки: пусть лежит в кэше, а не качается каждый раз.
SEVENZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"
HTML_START = re.compile(rb"^\s*(<!doctype|<html|<\?xml.{0,200}?<html)", re.IGNORECASE)


def payload_problem(raw: bytes, expect: str, min_size: int) -> str | None:
    """Почему скачанное нельзя считать файлом источника. None значит можно.

    Проверка нужна до записи в кэш: curl без -f возвращает ноль на 404 и 503, тело
    страницы ошибки больше порога размера ложилось в raw/ как успешная загрузка и
    ломало блок неделями после того, как источник ожил."""
    if len(raw) < min_size:
        return f"ответ {len(raw)} байт, меньше порога {min_size}"
    if expect == "page":
        return None
    if HTML_START.match(raw[:512]):
        return "вместо файла пришла HTML-страница"
    if expect == "xlsx" and not raw.startswith(XLSX_MAGIC):
        return "файл не начинается с сигнатуры xlsx"
    if expect == "document" and not raw.startswith(
        (XLSX_MAGIC, OLE_MAGIC, SEVENZIP_MAGIC)
    ):
        return "файл не похож ни на архив, ни на книгу Excel"
    return None


def download(
    url: str,
    path: Path,
    min_size: int = 1000,
    expect: str = "xlsx",
    timeout: int = 180,
) -> bytes:
    """Скачивание через curl мимо кэша: в raw/ файл попадает только после проверки.

    curl зовётся потому, что у kgd.gov.kz в цепочке самоподписанный сертификат и
    стандартный клиент Python его отвергает. Флаг -f обязателен: без него код
    возврата ноль и на 404, и на 503."""
    RAW.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        result = subprocess.run(
            [
                "curl",
                "-fsSL",
                "--retry",
                "3",
                "--retry-delay",
                "2",
                "--retry-all-errors",
                "--max-time",
                str(timeout),
                url,
                "-o",
                str(part),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "ignore").strip()[:120]
            raise SourceError(
                f"{url}: curl вернул {result.returncode} {detail}".strip()
            )
        raw = part.read_bytes() if part.exists() else b""
        problem = payload_problem(raw, expect, min_size)
        if problem:
            raise SourceError(f"{url}: {problem}")
        part.replace(path)
        return raw
    finally:
        part.unlink(missing_ok=True)


def fetch_file(
    url: str, name: str, max_age_days: int = 7, expect: str = "xlsx"
) -> bytes:
    """Скачивание с кэшем в raw/. Битый кэш не переживает проверку и перекачивается."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    if path.exists():
        raw = path.read_bytes()
        age = (datetime.now().timestamp() - path.stat().st_mtime) / 86400
        if payload_problem(raw, expect, 1000):
            path.unlink(missing_ok=True)  # кэш испорчен прошлым сбоем источника
        elif age < max_age_days:
            return raw
    return download(url, path, expect=expect)


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


# --- Каталог документов КГД на gov.kz ---------------------------------


def kgd_documents() -> list[dict]:
    """Документы управления статистики КГД, свежие первыми."""
    url = f"{KGD_DOCUMENTS_API}?gosorgan={KGD_ORG_ID}&size=2000&page=0"
    rows = fetch_json(
        url, "kgd_documents.json", timeout=90, max_body=KGD_LISTING_MAX_BODY
    )
    if not isinstance(rows, list):
        raise SourceError("список документов КГД вернулся не списком")
    rows.sort(
        key=lambda row: (row.get("created_date") or "", row.get("id") or 0),
        reverse=True,
    )
    return rows


def document_file(row: dict) -> str | None:
    """Первое xlsx-вложение из обоих полей карточки gov.kz."""
    files = [
        item.get("document")
        for key in ("full_text", "other_files")
        for item in (row.get(key) or [])
        if item.get("document")
    ]
    return next((path for path in files if path.lower().endswith(".xlsx")), None)


def kgd_reports(kind: str, rows: list[dict] | None = None) -> list[dict]:
    """Таблицы нужного среза; Нацфонд не примешивается к госбюджету."""
    rows = rows if rows is not None else kgd_documents()
    found: list[dict] = []
    for row in rows:
        low = str(row.get("title") or "").lower()
        if "national fund" in low or "национальн" in low:
            continue
        if kind == "dynamics":
            matches = (
                "dynamics of tax revenues" in low and "state budget" in low
            ) or bool(
                re.search(
                    r"динамик.*налог.*государств.*бюдж", low
                )
            )
        else:
            matches = (
                ("actual revenues" in low or "actual receipts" in low)
                and "tax" in low
                and "state budget" in low
                and "region" in low
            ) or bool(
                re.search(
                    r"фактическ.*поступлен.*налог.*(?:гб|государств.*бюдж).*регион", low
                )
            )
        path = document_file(row)
        if matches and path:
            found.append({**row, "document": path})
    if not found:
        label = "динамики" if kind == "dynamics" else "фактических поступлений"
        raise SourceError(f"в каталоге КГД нет xlsx {label}")
    return found


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


REGION_NAMES_EN = {
    "dgd in akmola region": "Акмолинская",
    "dgd in the aktobe region": "Актюбинская",
    "dgd in the almaty region": "Алматинская",
    "dgd in atyrau region": "Атырауская",
    "dgd in the east kazakhstan region": "Восточно-Казахстанская",
    "dgd in zhambyl region": "Жамбылская",
    "dgd in the west kazakhstan region": "Западно-Казахстанская",
    "dgd in the karaganda region": "Карагандинская",
    "dgd in the kyzylorda region": "Кызылординская",
    "dgd in kostanay region": "Костанайская",
    "dgd in the mangystau region": "Мангистауская",
    "dgd in the pavlodar region": "Павлодарская",
    "dgd in the north kazakhstan region": "Северо-Казахстанская",
    "dgd for the turkestan region": "Туркестанская",
    "dgd in shymkent": "Шымкент",
    "dgd in almaty": "Алматы",
    "dgd for the city of astana": "Астана",
    "dgd for the zhetysu region": "Жетысуская",
    "dgd for the abay region": "Абайская",
    "dgd for the ulytau region": "Улытауская",
    "kgd mf rk": "КГД МФ РК",
}


def region_name(name: str) -> str:
    key = re.sub(r"\s+", " ", name).strip().lower()
    return REGION_NAMES_EN.get(key, name)


def parse_dynamics(rows: list[list[str]]) -> dict:
    """Строка «ДОХОДЫ, всего» и строки областей, колонки это месяцы.

    Значения в файле указаны в тысячах тенге, приводим к миллиардам: на странице
    сравниваются масштабы, а не платёжки."""
    header_idx = next(
        (
            i
            for i, r in enumerate(rows)
            if r
            and r[0].strip().lower().startswith(("январь", "january"))
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
        if name.upper().startswith(("ДОХОДЫ", "INCOME")):
            total = values
        elif not name.lower().startswith(("в том числе", "including")):
            regions.append({"name": region_name(name), "values": values})
    if not total:
        raise SourceError("в файле динамики нет строки «ДОХОДЫ, всего»")
    populated = [index for index, value in enumerate(total) if value is not None]
    if populated:
        width = populated[-1] + 1
        months = months[:width]
        total = total[:width]
        for region in regions:
            region["values"] = region["values"][:width]
    return {"months": months, "total": total, "regions": regions}


def dynamics_year(rows: list[list[str]]) -> int:
    """Год из шапки книги: заголовок карточки gov.kz бывает неверен."""
    text = " ".join(cell for row in rows[:4] for cell in row)
    years = [int(value) for value in re.findall(r"(?<!\d)20\d{2}(?!\d)", text)]
    if not years:
        raise SourceError("в шапке файла динамики нет года")
    return max(years)


def fetch_dynamics_report(report: dict) -> dict:
    doc_id = report.get("id") or "unknown"
    url = KGD + report["document"]
    raw = fetch_file(url, f"kgd_dynamics_{doc_id}.bin", max_age_days=30)
    book = Workbook(raw)
    if not book.sheets:
        raise SourceError("в книге динамики нет листов")
    rows = book.rows(book.sheets[0][1])
    data = parse_dynamics(rows)
    data["year"] = dynamics_year(rows)
    data["period"] = f"{data['year']}-{len(data['months']):02d}"
    data["source_url"] = KGD_STATS_PAGE
    data["source_file_url"] = url
    data["published"] = (report.get("created_date") or "")[:10]
    return data


def fetch_dynamics() -> dict:
    """Свежий год помесячно; плохой свежий файл не закрывает предыдущие."""
    reports = kgd_reports("dynamics")
    skipped: list[str] = []
    data = None
    current_index = -1
    for index, report in enumerate(reports[:8]):
        try:
            data = fetch_dynamics_report(report)
            current_index = index
            break
        except (SourceError, OSError) as exc:
            skipped.append(f"{report.get('id', '?')} ({exc})")
    if data is None:
        raise SourceError(f"ни один файл динамики не разобрался: {'; '.join(skipped)}")
    data["previous"] = None
    for report in reports[current_index + 1 :]:
        title_years = [
            int(value)
            for value in re.findall(
                r"(?<!\d)20\d{2}(?!\d)", report.get("title") or ""
            )
        ]
        if title_years and max(title_years) >= data["year"]:
            continue
        try:
            previous = fetch_dynamics_report(report)
            if previous["year"] < data["year"]:
                data["previous"] = previous
                break
        except (SourceError, OSError):
            continue
    data["skipped"] = skipped
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
    """Строка «Налоговые поступления» листа, в тысячах тенге.

    Неразобранная шапка это ошибка, а не ноль: с нулём ломалась эвристика поиска
    свода, и разрез начинал складывать свод вместе с листами органов, удваивая
    суммы."""
    rows = book.rows(path)
    value_idx, name_idx = sheet_layout(rows)
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
    positive = [(path, value) for path, value in totals if value > 0]
    # В новой форме КГД на листах органов нет колонки наименования,
    # а полная раскладка есть только на одном сводном листе. Единственный
    # структурно разбираемый итог безопасно считать сводом.
    if len(positive) == 1:
        return positive[0][0]
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


FACT_MONTHS = {
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
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def fact_period(book: Workbook) -> tuple[int, int]:
    """Отчётный период из шапки книги, а не из ненадёжного заголовка gov.kz."""
    chunks: list[str] = []
    for _, path in book.sheets[:4]:
        chunks.extend(" ".join(row) for row in book.rows(path)[:3])
    text = " ".join(chunks).lower()
    years = [int(value) for value in re.findall(r"(?<!\d)20\d{2}(?!\d)", text)]
    if not years:
        raise SourceError("в шапке файла нет отчётного года")
    numeric = re.findall(r"(?:за|for)\s+(\d{1,2})\s+(?:месяц|month)", text)
    months = [FACT_MONTHS[name] for name in FACT_MONTHS if name in text]
    if numeric:
        months.extend(int(value) for value in numeric)
    if re.search(r"(?:1|перв\w*|first)\s*(?:-й|st)?\s*(?:квартал|quarter)", text):
        months.append(3)
    if "первое полугодие" in text or "first half" in text:
        months.append(6)
    months = [month for month in months if 1 <= month <= 12]
    if not months:
        raise SourceError("в шапке файла нет отчётного месяца")
    return max(years), max(months)


def fetch_structure() -> dict:
    skipped: list[str] = []
    # Перебор идёт до первого разобравшегося месяца. Плохой файл выбывает сам:
    # раньше на нём обрывался весь перебор, и следующие отчёты не пробовались.
    for report in kgd_reports("fact")[:8]:
        period_label = f"документ {report.get('id', '?')}"
        try:
            doc_id = report.get("id") or "unknown"
            url = KGD + report["document"]
            book = Workbook(
                fetch_file(url, f"kgd_fact_{doc_id}.bin", max_age_days=30)
            )
            year, month = fact_period(book)
            period_label = f"{year}-{month:02d}"
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
                skipped.append(
                    f"{year}-{month:02d} (разрез {collected:.0f} против итога {declared:.0f})"
                )
                continue
        except (SourceError, OSError) as exc:
            skipped.append(f"{period_label} ({exc})")
            continue
        return {
            "period": f"{year}-{month:02d}",
            "year": year,
            "months": month,
            "items": items,
            "declared_total": round(declared, 2),
            "file_modified": book.modified,
            "published": (report.get("created_date") or "")[:10],
            "skipped": skipped,
            "source_url": KGD_STATS_PAGE,
            "source_file_url": url,
        }
    raise SourceError(f"ни один месячный файл не разобрался: {'; '.join(skipped)}")


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
    # Раздел, которого нет ни свежим, ни прошлым, потерян целиком.
    lost = [
        name
        for key, name in (
            ("dynamics", "динамика поступлений"),
            ("structure", "структура поступлений"),
        )
        if not data[key]
    ]
    if lost:
        raise SystemExit(f"потеряны разделы целиком: {', '.join(lost)}")


if __name__ == "__main__":
    main()
