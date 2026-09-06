"""Исполнение государственного бюджета Казахстана по отчётам Минфина.

Комитет госдоходов публикует свои таблицы с задержкой больше года, а Минфин
выкладывает отчёт об исполнении бюджета каждый месяц, с планом на период, фактом
и процентом исполнения. Отсюда берутся свежие цифры страны, а региональный разрез
остаётся за КГД: у Минфина его в этих отчётах нет.

Две особенности источника:

1. Сайт gov.kz это одностраничное приложение, в HTML данных нет. Список и карточки
   документов берутся из его публичного API content-manager, файл лежит в поле
   document карточки.
2. Отчёт «на 1 июня» это январь-май нарастающим итогом. Помесячные значения тут
   считаются разностями соседних отчётов, и если месяц пропущен, разность
   отбрасывается целиком: делить её пополам значит выдумывать данные.

Запуск: .venv/bin/python minfin.py out/minfin.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from budget import SourceError, Workbook, as_number, download, payload_problem
from etl import fetch_json

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DEFAULT_DATASET = HERE / "out" / "minfin.json"

SITE = "https://www.gov.kz"
API = f"{SITE}/api/v1/public/content-manager/documents"
ACTIVITY = 555  # раздел «Отчёты об исполнении бюджета»
DOC_PAGE = f"{SITE}/memleket/entities/minfin/documents/details"

MONTHS_EN = {
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
MONTHS_RU = {
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
MONTH_NAME = [
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

TITLES = {
    "state": (
        re.compile(
            r"execution of the state budget as of (\w+) (\d{1,2}),? (\d{4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"исполнени[ия] государственного бюджета на (\d{1,2}) (\w+) (\d{4})",
            re.IGNORECASE,
        ),
    ),
    "local": (
        re.compile(
            r"execution of the local budget as of (\w+) (\d{1,2}),? (\d{4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"исполнени[ия] местного бюджета на (\d{1,2}) (\w+) (\d{4})",
            re.IGNORECASE,
        ),
    ),
}

# Колонки отчёта Минфина: план на отчётный период, исполнено, процент исполнения.
# У областных отчётов раскладка своя, поэтому есть report_layout.
COL_PLAN = 10
COL_FACT = 11
COL_PCT = 15

MAX_REPORTS = 15
KEEP_MONTHS = 24

# Списки документов gov.kz весят десятки мегабайт: в поле full_text лежит
# полный текст каждой карточки. Общий потолок ответа их обрезает, а обрезанный
# JSON выглядит как битый источник.
LISTING_MAX_BODY = 128 * 1024 * 1024


def api_json(url: str, timeout: int = 90):
    """Список или карточка gov.kz. Ретраи общие с остальными источниками: одиночный
    запрос без повтора ронял весь прогон на первом же обрыве соединения."""
    return fetch_json(url, timeout=timeout, max_body=LISTING_MAX_BODY)


def parse_title(title: str, kind: str = "state") -> tuple[int, int] | None:
    """Год и месяц отчётной даты «на 1 июня 2026» -> (2026, 6)."""
    english, russian = TITLES[kind]
    m = english.search(title)
    if m:
        month = MONTHS_EN.get(m.group(1).lower())
        return (int(m.group(3)), month) if month else None
    m = russian.search(title)
    if m:
        month = MONTHS_RU.get(m.group(2).lower())
        return (int(m.group(3)), month) if month else None
    return None


def covered_period(year: int, month: int) -> tuple[int, int]:
    """Отчёт на 1 июня 2026 покрывает январь-май 2026, на 1 января 2026 весь 2025."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def reports(kind: str = "state") -> list[dict]:
    """Отчёты об исполнении бюджета выбранного уровня, свежие первыми."""
    found: dict[tuple[int, int], dict] = {}
    for page in range(12):
        chunk = api_json(
            f"{API}?projects=minfin&activities={ACTIVITY}&size=100&page={page}"
        )
        if not chunk:
            break
        for row in chunk:
            stamp = parse_title(row.get("title") or "", kind)
            if not stamp:
                continue
            year, months = covered_period(*stamp)
            files = [f for f in (row.get("full_text") or []) if f.get("document")]
            found.setdefault(
                (year, months),
                {
                    "id": row.get("id"),
                    "year": year,
                    "months": months,
                    "published": (row.get("created_date") or "")[:10],
                    # Ссылка берётся из списка: карточка части отчётов отвечает
                    # пустым объектом, и такой отчёт считался «без файла».
                    "document": files[0]["document"] if files else "",
                },
            )
        if len(chunk) < 100:
            break
    if not found:
        raise SourceError(f"в разделе отчётов Минфина нет отчётов уровня {kind}")
    return [found[key] for key in sorted(found, reverse=True)]


def card_document(doc_id) -> str:
    """Ссылка на файл из карточки документа. Запасной путь: у части отчётов
    карточка отвечает пустым объектом, и тогда работает ссылка из списка."""
    card = api_json(f"{API}/{doc_id}")
    files = (
        [f for f in (card.get("full_text") or []) if f.get("document")]
        if isinstance(card, dict)
        else []
    )
    if not files:
        raise SourceError(f"у отчёта {doc_id} нет файла ни в списке, ни в карточке")
    return files[0]["document"]


def fetch_report(report: dict) -> Workbook:
    """Файл отчёта. Опубликованный отчёт не меняется, поэтому кэш держится без
    срока, но битый файл в кэше жил бы вечно, поэтому кэш проверяется сигнатурой."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = (
        RAW
        / f"minfin_{report.get('kind', 'state')}_{report['year']}_{report['months']:02d}.bin"
    )
    if path.exists():
        raw = path.read_bytes()
        if payload_problem(raw, "xlsx", 10_000) is None:
            return Workbook(raw)
        path.unlink(missing_ok=True)  # кэш испорчен прошлым сбоем источника
    link = report.get("document") or card_document(report["id"])
    return Workbook(download(SITE + link, path, min_size=10_000, expect="xlsx"))


def report_layout(rows: list[list[str]]) -> tuple[int, int, int, int]:
    """Колонки отчёта об исполнении: план, факт, процент и левый край наименований.

    Форма одна и та же, но раскладка колонок у Минфина и у областей разная, а факт
    в разных отчётах подписан то «Принятые обязательства», то «Исполнение
    поступлений». Поэтому колонки ищутся по шапке, а выбор факта проверяется
    процентом исполнения из самого отчёта."""
    header = None
    plan_mark = None
    for index, row in enumerate(rows[:14]):
        # Шапка бывает разбита на две строки: в одной наименование, в соседней
        # подписи плановых колонок. Читаются они только вместе.
        following = rows[index + 1] if index + 1 < len(rows) else []
        width = max(len(row), len(following))
        row = [
            " ".join(
                part
                for part in (
                    row[i] if i < len(row) else "",
                    following[i] if i < len(following) else "",
                )
                if part.strip()
            )
            for i in range(width)
        ]
        joined = " ".join(row).lower()
        if "наименование" not in joined:
            continue
        # Форма 7-ОИБ подписывает плановую колонку «Сводный план», а сводки
        # областей, где рядом стоят прошлые годы, пишут «План на <дата>».
        for mark in ("сводный план", "план на "):
            if mark in joined:
                header, plan_mark = row, mark
                break
        if header is not None:
            break
    if header is None:
        raise SourceError("в отчёте нет шапки со сводным планом")

    col_plan = next(i for i, c in enumerate(header) if plan_mark in c.lower())
    name_col = next(i for i, c in enumerate(header) if "наименование" in c.lower())
    col_pct = next(
        (
            i
            for i, c in enumerate(header)
            if "к плану на период" in c.lower() or "исп-е поступ" in c.lower()
        ),
        -1,
    )

    # Первая колонка правее плана, где число сходится с процентом исполнения.
    candidates = [
        i for i in range(col_plan + 1, len(header) + 6) if col_pct < 0 or i != col_pct
    ]
    for row in rows:
        plan = as_number(row[col_plan]) if len(row) > col_plan else None
        pct = as_number(row[col_pct]) if col_pct >= 0 and len(row) > col_pct else None
        if not plan or not pct:
            continue
        for col in candidates:
            fact = as_number(row[col]) if len(row) > col else None
            if fact and abs(fact / plan * 100 - pct) < 0.5:
                return col_plan, col, col_pct, name_col

    # Формы, где процента нет вовсе: колонка исполнения подписана в шапке, а
    # правдоподобие проверяется отношением факта к плану на нескольких строках.
    named = next(
        (i for i, c in enumerate(header) if i > col_plan and "исполнени" in c.lower()),
        -1,
    )
    if named >= 0:
        checked = 0
        for row in rows:
            plan = as_number(row[col_plan]) if len(row) > col_plan else None
            fact = as_number(row[named]) if len(row) > named else None
            if plan and fact and 0.2 < fact / plan < 2.0:
                checked += 1
            if checked >= 3:
                return col_plan, named, -1, name_col
    raise SourceError("в отчёте не нашлась колонка исполнения")


def level_of(row: list[str]) -> int:
    """Уровень строки: наименование сдвигается вправо по вложенности."""
    for i in range(1, min(len(row), 7)):
        if row[i].strip():
            return i
    return 0


# Категории доходов. В отчётах Минфина у них есть код, в областных формах код стоит
# в другой строке, чем факт, поэтому опознаются они по названию.
INCOME_CATEGORIES = [
    ("1", "налоговые поступления"),
    ("2", "неналоговые поступления"),
    ("3", "поступления от продажи основного капитала"),
    ("4", "специальные поступления"),
    ("5", "поступления трансфертов"),
]


def category_code(name: str) -> str | None:
    """Код категории доходов по её названию, без учёта регистра и хвостов."""
    text = " ".join(name.lower().split())
    for code, title in INCOME_CATEGORIES:
        if text.startswith(title):
            return code
    return None


def parse_income(
    rows: list[list[str]], layout: tuple[int, int, int, int] | None = None
) -> list[dict]:
    """Категории доходов верхнего уровня: налоги, неналоговые, трансферты и прочее.

    Нужны, чтобы показать, на чём держится бюджет уровня: у местных бюджетов
    заметная часть доходов это трансферты из республиканского, и без них картина
    поступлений читается неверно."""
    col_plan, col_fact, col_pct, name_col = layout or report_layout(rows)
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) <= col_fact:
            continue
        # Наименование сдвигается вправо по уровню вложенности, и у разных форм
        # категория оказывается в разных колонках между шапкой и плановыми числами.
        title = next(
            (
                row[i]
                for i in range(name_col, min(col_plan, len(row)))
                if row[i].strip()
            ),
            "",
        )
        code = category_code(title)
        if not code or code in seen:
            continue
        fact = as_number(row[col_fact])
        if fact is None:
            continue
        seen.add(code)
        out.append(
            {
                "code": code,
                "name": " ".join(title.split()).capitalize(),
                "plan": (as_number(row[col_plan]) or 0) / 1e6,
                "fact": fact / 1e6,
                "pct": as_number(row[col_pct]) if 0 <= col_pct < len(row) else None,
            }
        )
        if len(out) == len(INCOME_CATEGORIES):
            break
    return out


def parse_report(book: Workbook) -> dict:
    """Налоговые поступления: план на период, факт и разрез по видам налогов."""
    rows = book.rows(book.sheets[0][1])
    total: dict | None = None
    items: list[dict] = []
    inside = False
    for row in rows:
        if len(row) <= COL_FACT:
            continue
        level = level_of(row)
        name = row[level].strip() if level else row[0].strip()
        plan = as_number(row[COL_PLAN])
        fact = as_number(row[COL_FACT])
        if level == 1 and name.lower().startswith("налоговые поступления"):
            # Заголовок повторяется дальше по отчёту в других разрезах бюджета,
            # и без остановки разрез сложился бы из нескольких блоков сразу.
            if total is not None:
                break
            inside = True
            total = {
                "name": "Налоговые поступления",
                "plan": (plan or 0) / 1e6,
                "fact": (fact or 0) / 1e6,
                "pct": as_number(row[COL_PCT]) if len(row) > COL_PCT else None,
            }
            continue
        if inside and level == 1:
            break  # началась следующая категория доходов
        if inside and level == 2 and fact:
            items.append(
                {
                    "code": row[0].strip(),
                    "name": name,
                    "plan": (plan or 0) / 1e6,
                    "fact": fact / 1e6,
                    "pct": as_number(row[COL_PCT]) if len(row) > COL_PCT else None,
                }
            )
    if not total or not items:
        raise SourceError("в отчёте не нашлось налоговых поступлений")
    collected = sum(i["fact"] for i in items)
    # Нулевой итог достижим: факт берётся как (fact or 0). Делить на него нельзя,
    # а ZeroDivisionError мимо except в collect роняла весь прогон, а не отчёт.
    if not total["fact"]:
        raise SourceError("итог налоговых поступлений нулевой")
    if abs(collected - total["fact"]) / total["fact"] > 0.02:
        raise SourceError(
            f"разрез не сходится с итогом: {collected:.0f} против {total['fact']:.0f}"
        )
    items.sort(key=lambda i: -i["fact"])
    return {"total": total, "items": items, "income": parse_income(rows)}


def monthly(points: list[dict]) -> list[dict]:
    """Помесячные поступления из накопительных итогов.

    Точки идут по возрастанию периода. Разность берётся только у соседних месяцев:
    если отчёт за месяц не опубликован, пропуск остаётся пропуском."""
    out = []
    previous: dict | None = None
    for point in points:
        year, months = point["year"], point["months"]
        if months == 1:
            value, plan = point["fact"], point["plan"]  # январь: итог равен месяцу
        elif previous and previous["year"] == year and previous["months"] == months - 1:
            value = point["fact"] - previous["fact"]
            plan = point["plan"] - previous["plan"]
        else:
            previous = point
            continue
        out.append(
            {
                "period": f"{year}-{months:02d}",
                "year": year,
                "month": months,
                "value": round(value, 2),
                "plan": round(plan, 2),
            }
        )
        previous = point
    return out[-KEEP_MONTHS:]


def collect(kind: str, issues: list[str]) -> tuple[dict | None, list[dict]]:
    """Свежий срез уровня бюджета и помесячный ряд по нему."""
    latest: dict | None = None
    history: list[dict] = []
    try:
        available = reports(kind)
    except SourceError as exc:
        issues.append(f"список отчётов ({kind}): {exc}")
        return None, []

    for report in available[:MAX_REPORTS]:
        report = {**report, "kind": kind}
        try:
            parsed = parse_report(fetch_report(report))
        except (SourceError, OSError, ArithmeticError) as exc:
            issues.append(
                f"отчёт {kind} {report['year']}-{report['months']:02d}: {exc}"
            )
            continue
        history.append(
            {**report, "fact": parsed["total"]["fact"], "plan": parsed["total"]["plan"]}
        )
        if latest is None:
            latest = {
                **report,
                "period": f"{report['year']}-{report['months']:02d}",
                "url": f"{DOC_PAGE}/{report['id']}?lang=ru",
                "total": parsed["total"],
                "items": parsed["items"],
                "income": parsed["income"],
            }
    history.sort(key=lambda p: (p["year"], p["months"]))
    if latest:
        # Тот же отрезок года назад: январь-июль 2026 сравнивается с январём-июлем
        # 2025, а не с целым прошлым годом.
        base = next(
            (
                p
                for p in history
                if p["year"] == latest["year"] - 1 and p["months"] == latest["months"]
            ),
            None,
        )
        latest["year_ago"] = (
            {"period": f"{base['year']}-{base['months']:02d}", "fact": base["fact"]}
            if base
            else None
        )
    return latest, history


def build() -> dict:
    issues: list[str] = []
    state, state_history = collect("state", issues)
    local, local_history = collect("local", issues)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Министерство финансов РК",
        "source_url": f"{SITE}/memleket/entities/minfin/activities/448?lang=ru",
        "latest": state,
        "monthly": monthly(state_history),
        "local": local,
        "monthly_local": monthly(local_history),
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
    # Источник отвечает не всегда: прошлый срез честнее пустого блока.
    for key, series in (("latest", "monthly"), ("local", "monthly_local")):
        if not data[key] and previous.get(key):
            data[key] = {**previous[key], "stale": True}
            data[series] = previous.get(series, [])
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if data["latest"]:
        latest = data["latest"]
        print(
            f"исполнение: {latest['period']}, позиций {len(latest['items'])}, "
            f"факт {latest['total']['fact']:.0f} млрд, "
            f"план {latest['total']['plan']:.0f} млрд"
        )
    if data["local"]:
        local = data["local"]
        transfers = next((i for i in local["income"] if "рансферт" in i["name"]), None)
        income = sum(i["fact"] for i in local["income"]) or 1
        print(
            f"местные бюджеты: {local['period']}, налоги {local['total']['fact']:.0f} млрд, "
            f"трансферты {transfers['fact'] if transfers else 0:.0f} млрд "
            f"({(transfers['fact'] if transfers else 0) / income * 100:.0f}% доходов)"
        )
    print(
        f"помесячно: точек {len(data['monthly'])} по стране, "
        f"{len(data['monthly_local'])} по местным"
    )
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")
    # Уровень бюджета, которого нет ни свежим, ни прошлым, потерян целиком.
    lost = [
        name
        for key, name in (
            ("latest", "государственный бюджет"),
            ("local", "местные бюджеты"),
        )
        if not data[key]
    ]
    if lost:
        raise SystemExit(f"потеряны разделы целиком: {', '.join(lost)}")


if __name__ == "__main__":
    main()
