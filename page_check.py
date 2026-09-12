"""Проверка набора страниц Macro Radar: структура плюс наполнение.

Хаб и пять тем разъехались по собственным адресам: у каждой свой файл, свой h1
и свой canonical. Проверка идёт по каталогу public/macroradar, а не по одному
файлу: нужно поймать не только сломанную разметку внутри страницы, но и
разрыв перелинковки между страницами, и возврат прежней склейки вкладок.

Разметка бывает целой, а страница при этом пустой: вырезанный main, секция без
единого числа, график без точек, таблица без строк, пропавшая или протухшая
выгрузка. Такие сборки уезжали на прод с кодом 0, поэтому рядом со
структурными проверками (problems) идут проверки наполнения (content_problems).
Категории считаются отдельно и обе валят прогон, но в логе видно, что именно
сломалось.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

SITE = "https://jbs.finance"

PAGES = {
    "": "index.html",
    "macro": "macro/index.html",
    "trade": "trade/index.html",
    "national-fund": "national-fund/index.html",
    "budget": "budget/index.html",
    "tax": "tax/index.html",
}

METHOD_PAGE = "methodology/index.html"
METHOD_URL = "/macroradar/methodology/"


class Node:
    def __init__(self, tag: str, attrs: list, parent: Node | None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def walk(self):
        for child in self.children:
            yield child
            yield from child.walk()


class Tree(HTMLParser):
    def __init__(self, document: str):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", [], None)
        self.cur = self.root
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        # Текст лежит в дереве отдельными узлами: проверке наполнения нужно
        # считать числа и подписи внутри конкретной секции, а не по всему файлу.
        if data.strip():
            self.cur.children.append(Node("#text", [("data", data)], self.cur))


def path_for(slug: str) -> str:
    return f"/macroradar/{slug}/" if slug else "/macroradar/"


def url_for(slug: str) -> str:
    return f"{SITE}{path_for(slug)}"


def page_problems(base: Path, slug: str) -> list[str]:
    relpath = PAGES[slug]
    path = base / relpath
    if not path.exists():
        return [f"{relpath}: файл не найден"]
    document = path.read_text(encoding="utf-8")
    if not document.strip():
        return [f"{relpath}: файл пустой"]

    found = []
    if 'class="tab-state"' in document or "#view-" in document:
        found.append(f"{relpath}: осталась склейка вкладок (tab-state или #view-)")

    # Пока страницы склеивались, палитру можно было брать у соседа по документу.
    # Теперь каждая отвечает за свои переменные сама: незамеченная нехватка уводит
    # страницу на прод без цветов, при этом вся разметка на месте и остальные
    # проверки зелёные. Так хаб и уехал бы после разделения.
    used = set(re.findall(r"var\((--[a-z0-9-]+)\)", document))
    declared = set(re.findall(r"(--[a-z0-9-]+)\s*:", document))
    missing = sorted(used - declared)
    if missing:
        found.append(f"{relpath}: переменные без объявления: {', '.join(missing)}")

    tree = Tree(document)
    nodes = list(tree.root.walk())

    h1s = [n for n in nodes if n.tag == "h1"]
    if len(h1s) != 1:
        found.append(f"{relpath}: {len(h1s)} тегов h1 вместо одного")

    canonical = next(
        (n for n in nodes if n.tag == "link" and n.attrs.get("rel") == "canonical"),
        None,
    )
    expected = url_for(slug)
    if canonical is None:
        found.append(f"{relpath}: нет rel=canonical")
    elif canonical.attrs.get("href") != expected:
        found.append(
            f"{relpath}: canonical {canonical.attrs.get('href')} вместо {expected}"
        )

    for n in nodes:
        if n.tag == "script" and n.attrs.get("type") != "application/ld+json":
            found.append(
                f"{relpath}: исполняемый <script> запрещён CSP (script-src 'none')"
            )

    if slug == "":
        cards = [n for n in nodes if n.tag == "a" and "radar-card" in n.classes]
        if len(cards) != 5:
            found.append(f"{relpath}: на хабе {len(cards)} карточек вместо 5")
        for card in cards:
            href = card.attrs.get("href", "")
            target_slug = next((s for s in PAGES if s and path_for(s) == href), None)
            if target_slug is None or not (base / PAGES[target_slug]).exists():
                found.append(
                    f"{relpath}: карточка ведёт на несуществующую страницу {href}"
                )
    else:
        nav = next((n for n in nodes if n.tag == "nav" and "tabs" in n.classes), None)
        if nav is None:
            found.append(f"{relpath}: нет навигации .tabs в шапке")
        else:
            nav_hrefs = {n.attrs.get("href") for n in nav.walk() if n.tag == "a"}
            for other in PAGES:
                if other == slug:
                    continue
                href = path_for(other)
                if href not in nav_hrefs:
                    found.append(f"{relpath}: в шапке нет ссылки на {href}")
                elif not (base / PAGES[other]).exists():
                    found.append(
                        f"{relpath}: ссылка на {href} ведёт на несуществующий файл"
                    )

    return found


def problems(base: Path) -> list[str]:
    found = []
    for slug in PAGES:
        found.extend(page_problems(base, slug))
    return found


def methodology_problems(base: Path) -> list[str]:
    """Методика доступна из футера отдельной страницей, вне витрины и вкладок."""
    found = []
    hub_path = base / PAGES[""]
    method_path = base / METHOD_PAGE
    if not hub_path.exists():
        return found

    hub = Tree(hub_path.read_text(encoding="utf-8"))
    hub_nodes = list(hub.root.walk())
    links = [
        node
        for node in hub_nodes
        if node.tag == "a" and node.attrs.get("href") == METHOD_URL
    ]
    footer = next((node for node in hub_nodes if node.tag == "footer"), None)
    footer_links = list(footer.walk()) if footer else []
    if len(links) != 1 or links[0] not in footer_links:
        found.append(
            f"{PAGES['']}: методика должна быть доступна одной ссылкой из футера"
        )
    elif re.sub(r"\s+", " ", visible_text([links[0]])).strip() != "Методика и источники":
        found.append(
            f"{PAGES['']}: подпись ссылки на методику должна быть «Методика и источники»"
        )
    if not method_path.exists():
        found.append(f"{METHOD_PAGE}: отдельная страница методики не найдена")
        return found

    document = method_path.read_text(encoding="utf-8")
    if not document.strip():
        found.append(f"{METHOD_PAGE}: файл пустой")
        return found

    method = Tree(document)
    nodes = list(method.root.walk())
    if not any(node.tag == "main" for node in nodes):
        found.append(f"{METHOD_PAGE}: нет <main>")
    h1s = [node for node in nodes if node.tag == "h1"]
    if len(h1s) != 1:
        found.append(f"{METHOD_PAGE}: {len(h1s)} тегов h1 вместо одного")
    if any(node.tag == "a" and "radar-card" in node.classes for node in nodes):
        found.append(f"{METHOD_PAGE}: методика не должна быть плиткой радара")
    for nav in (node for node in nodes if node.tag == "nav" and "tabs" in node.classes):
        if any(
            node.tag == "a" and node.attrs.get("href") == METHOD_URL
            for node in nav.walk()
        ):
            found.append(f"{METHOD_PAGE}: методика не должна быть вкладкой радара")

    canonical = next(
        (
            node
            for node in nodes
            if node.tag == "link" and node.attrs.get("rel") == "canonical"
        ),
        None,
    )
    expected = f"{SITE}{METHOD_URL}"
    if canonical is None or canonical.attrs.get("href") != expected:
        got = canonical.attrs.get("href") if canonical else None
        found.append(f"{METHOD_PAGE}: canonical {got} вместо {expected}")
    if "Как читать отчёт" not in visible_text(nodes):
        found.append(f"{METHOD_PAGE}: нет раздела «Как читать отчёт»")
    return found


# ---------------------------------------------------------------------------
# Наполнение
# ---------------------------------------------------------------------------
# Разметка бывает целой, а страница пустой: вырезанный main, схлопнувшаяся
# секция, график без точек, таблица без строк. Структурные проверки такое не
# видят и пропускают неполную сборку на прод.
#
# Пороги ниже абсолютные, а не выведенные из тех же данных, которые проверяют.
# Во встроенном гейте workflow было наоборот (page.count('name="drill-region"')
# >= len(regions) из того же budget.json), поэтому схлопывание выгрузки
# схлопывало и порог. Все числа сняты с здоровых страниц public/macroradar от
# 06.09.2026 и поставлены с запасом вниз: они ловят провал, а не колебание.

CONTENT_MAX_AGE_HOURS = 24
# Даты на страницах местные: сборка идёт по Астане, UTC+5.
ALMATY = timezone(timedelta(hours=5))

DRAW_TAGS = {"path", "rect", "circle", "polyline", "polygon", "line"}
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# Нерезолвленные значения, которым нельзя доезжать до публикации.
UNRESOLVED = (
    (r"код\s+\d{2,4}", "код страны без названия (UN Comtrade)"),
    (r"\bNone\b", "None"),
    (r"\bnan\b", "nan"),
    (r"\bNaN\b", "NaN"),
)

# Минимумы по выгрузкам. В скобках факт на 06.09.2026.
MIN_OBS = 15  # длина ряда, ниже которой ряд считается схлопнутым
MIN_PULSE_SERIES = 10  # рядов не короче MIN_OBS в pulse.json (12 из 13)
MIN_MACRO_SERIES = 2  # ставка и месячная инфляция в data.json (2)
MIN_MACRO_INFLATION = 15  # месяцев инфляции в data.json (21)
MIN_MACRO_CALENDAR = 6  # ближайших релизов (14)
MIN_MACRO_EVENTS = 3  # событий «что изменилось» (5)
MIN_MACRO_NEIGHBOURS = 3  # разрезов по соседям (3)
MIN_TRADE_SERIES = 5  # рядов внешней торговли (5)
MIN_TRADE_BREAKDOWNS = 3  # разрезов структуры торговли (3)
MIN_TRADE_PARTNERS = 10  # партнёров в каждом разрезе (10)
MIN_FUND_ASSETS = 100  # месячных точек активов Нацфонда (121)
MIN_FUND_RETURNS = 8  # годовых точек доходности (10)
MIN_KGD_REGIONS = 15  # областей в разбивке КГД, всего в стране 20 (21 объект)
MIN_KGD_MONTHS = 10  # месяцев в помесячном разрезе КГД (12)
MIN_OBLAST_REGIONS = 20  # регионов в бюллетене Минфина, их ровно двадцать (20)
MIN_MINFIN_MONTHS = 10  # месяцев в графике исполнения плана (11)
MIN_MINFIN_KINDS = 5  # видов налогов в структуре поступлений (7)
MIN_TAX_GROUPS = 5  # групп ставок (5)
MIN_TAX_RATES = 25  # строк со ставками во всех группах (30)
MIN_TAX_BASE = 5  # базовых величин: МРП, МЗП, вычет, пороги (5)

# Выгрузка рядом с HTML: без неё страница собрана вслепую. Значение это тема,
# в отчёте о проблеме нужно видеть, какая страница осталась без данных.
DATASETS = {
    "data.json": "macro",
    "pulse.json": "macro",
    "trade/data.json": "trade",
    "national-fund/data.json": "national-fund",
    "budget/oblast.json": "budget",
    "tax/data.json": "tax",
    "tax/budget.json": "budget",
    "tax/minfin.json": "budget",
}

# Блоки, где все даты обязаны быть в прошлом. Календарь будущих релизов сюда
# не входит: даты вперёд там норма.
PAST_SECTIONS = {"macro": ("#events",)}

# Страницы, которые публикуют штамп сборки: у хаба и Нацфонда его нет.
STAMPED = ("macro", "trade", "budget", "tax")


@dataclass(frozen=True)
class Section:
    """Обязательная секция страницы и минимум наполнения внутри неё.

    anchor: «#id», «.class» или точный текст заголовка. Заголовок задаёт
    область до следующего заголовка того же или более высокого уровня, элемент
    с id или классом задаёт своё поддерево. Опора на структуру, а не на
    конкретную вёрстку блока: перестановка карточек внутри секции проверку не
    ломает.
    """

    anchor: str
    title: str
    numbers: int = 0
    rows: int = 0
    charts: int = 0
    items: int = 0
    links: int = 0
    entries: int = 0


SECTIONS = {
    "": (
        Section(".radar-grid", "витрина анализов", links=5),
    ),
    "macro": (
        Section("#scan", "три секунды", numbers=7, charts=5),
        Section("#events", "что изменилось", items=3),
        Section("#calendar", "ближайшие релизы", items=6),
        Section("#fx", "официальные курсы валют", numbers=4, charts=4),
        Section("#macro-economy", "экономика", numbers=5, charts=5),
        Section("#bns", "данные БНС", numbers=3, charts=3),
        Section("#business", "деловая активность", numbers=5),
        Section("#peers", "Казахстан среди соседей", numbers=3, items=9),
        Section("#sources", "источники и свежесть", rows=12),
    ),
    "trade": (
        Section("Товарооборот", "товарооборот", numbers=3, charts=3),
        Section("Инвестиции и открытость", "инвестиции и открытость", charts=2),
        Section("Структура торговли", "структура торговли", items=30),
    ),
    "national-fund": (
        Section(".fund-summary", "ключевые показатели фонда", numbers=3),
        Section("#assets-title", "валютные активы", charts=1),
        Section("#availability-title", "доступность данных", items=3),
        Section("#portfolio-title", "состав портфеля", numbers=3),
        Section("#history-title", "годовые точки", rows=8),
    ),
    "budget": (
        Section("Сколько собирают на самом деле", "поступления", numbers=8, charts=1),
        Section("Помесячно, факт против плана", "помесячно план и факт", charts=1),
        # Регионов в бюллетене всегда двадцать, порог с запасом вниз.
        Section("Доходы регионов", "доходы регионов", entries=18),
        Section("Кто платит: регионы", "регионы", numbers=8, charts=2),
    ),
    "tax": (
        Section("Базовые величины", "базовые величины", numbers=5),
        Section("#vat", "НДС", rows=3),
        Section("#cit", "КПН", rows=3),
        Section("#pit", "ИПН", rows=3),
        Section("#social", "зарплатные налоги", rows=3),
        Section("#special", "спецрежимы", rows=3),
        Section("Сроки и санкции", "сроки и санкции", rows=5),
    ),
}


def level(node: Node) -> int:
    return HEADINGS.index(node.tag) if node.tag in HEADINGS else 0


def text_of(node: Node) -> str:
    if node.tag == "#text":
        return node.attrs.get("data", "")
    if node.tag in ("style", "script"):
        return ""
    return " ".join(text_of(child) for child in node.children)


def visible_text(region: list[Node]) -> str:
    return re.sub(r"\s+", " ", " ".join(text_of(node) for node in region))


def walk(region: list[Node]):
    for node in region:
        yield node
        yield from node.walk()


def region_for(root: Node, anchor: str) -> list[Node] | None:
    """Область секции по якорю: поддерево элемента или хвост после заголовка."""
    nodes = list(root.walk())
    if anchor.startswith("#"):
        node = next((n for n in nodes if n.attrs.get("id") == anchor[1:]), None)
    elif anchor.startswith("."):
        node = next((n for n in nodes if anchor[1:] in n.classes), None)
    else:
        node = next(
            (
                n
                for n in nodes
                if n.tag in HEADINGS and text_of(n).strip() == anchor
            ),
            None,
        )
    if node is None:
        return None
    if node.tag not in HEADINGS:
        return [node]
    parent = node.parent
    siblings = parent.children if parent else []
    start = siblings.index(node)
    region = []
    for sibling in siblings[start + 1 :]:
        if sibling.tag in HEADINGS and level(sibling) <= level(node):
            break
        region.append(sibling)
    return region


def is_chart(node: Node) -> bool:
    return node.tag == "svg" and any(n.tag in DRAW_TAGS for n in node.walk())


def measure(region: list[Node]) -> dict[str, int]:
    nodes = list(walk(region))
    text = visible_text(region)
    return {
        "numbers": len(re.findall(r"\d+(?:[.,  ]\d+)*", text)),
        "rows": sum(
            1 for n in nodes if n.tag == "tr" and any(c.tag == "td" for c in n.walk())
        ),
        "charts": sum(1 for n in nodes if is_chart(n)),
        "items": sum(1 for n in nodes if n.tag in ("li", "dd")),
        "links": sum(1 for n in nodes if n.tag == "a"),
        "entries": sum(1 for n in nodes if is_entry(n)),
        "text": len(text.strip()),
    }


ROW_CLASS = re.compile(r"(^|-)row$")


def is_entry(node: Node) -> bool:
    """Строка разбивки: пункт списка, строка таблицы или блок-строка вёрстки."""
    if node.tag in ("li", "dd"):
        return True
    if node.tag == "tr":
        return any(c.tag == "td" for c in node.walk())
    return any(ROW_CLASS.search(name) for name in node.classes)


KIND_NAMES = {
    "numbers": "чисел",
    "rows": "строк таблицы",
    "charts": "графиков",
    "items": "пунктов списка",
    "links": "ссылок",
    "entries": "строк разбивки",
}


def section_problems(relpath: str, root: Node, slug: str) -> list[str]:
    found = []
    for spec in SECTIONS[slug]:
        region = region_for(root, spec.anchor)
        if region is None:
            found.append(
                f"{relpath}: секции «{spec.title}» нет на странице "
                f"(искали по {spec.anchor})"
            )
            continue
        got = measure(region)
        if not any(got[kind] for kind in KIND_NAMES) and got["text"] < 40:
            found.append(
                f"{relpath}: секция «{spec.title}» пуста: ни числа, "
                "ни строки таблицы, ни графика"
            )
            continue
        for kind, name in KIND_NAMES.items():
            want = getattr(spec, kind)
            if want and got[kind] < want:
                found.append(
                    f"{relpath}: секция «{spec.title}»: ожидалось {name} "
                    f"не меньше {want}, найдено {got[kind]}"
                )
    return found


def chart_problems(relpath: str, root: Node) -> list[str]:
    """Пустые графики и вырожденные ряды."""
    found = []
    for node in root.walk():
        if node.tag == "svg" and not is_chart(node):
            found.append(f"{relpath}: график без фигур: {chart_name(node)}")
        if node.tag in ("polyline", "polygon"):
            points = node.attrs.get("points", "").split()
            if len(points) < 2:
                found.append(
                    f"{relpath}: ряд из {len(points)} точек в графике "
                    f"{chart_name(node)}"
                )
        if node.tag == "path":
            d = " ".join(node.attrs.get("d", "").split())
            if d in ("", "M0 0", "M 0 0"):
                found.append(
                    f"{relpath}: пустая линия d=\"{d}\" в графике {chart_name(node)}"
                )
    return found


def chart_name(node: Node) -> str:
    while node is not None:
        label = node.attrs.get("aria-label") or node.attrs.get("class")
        if label:
            return label
        node = node.parent
    return "без подписи"


def table_problems(relpath: str, root: Node) -> list[str]:
    found = []
    for node in root.walk():
        if node.tag != "table":
            continue
        rows = [n for n in node.walk() if is_entry(n) and n.tag == "tr"]
        if not rows:
            found.append(f"{relpath}: таблица без строк данных, только шапка")
    return found


def unresolved_problems(relpath: str, root: Node) -> list[str]:
    found = []
    text = visible_text([root])
    for pattern, name in UNRESOLVED:
        hits = re.findall(pattern, text)
        if hits:
            sample = ", ".join(sorted(set(hits))[:3])
            found.append(
                f"{relpath}: в видимом тексте {len(hits)} раз(а) {name}: {sample}"
            )
    return found


def size(payload: dict, *path: str) -> int:
    """Длина списка по пути в выгрузке: пропавшая ветка это ноль, а не падение."""
    node = payload
    for key in path:
        node = (node or {}).get(key)
    return len(node or [])


def json_expectations(relpath: str, payload: dict) -> list[tuple[str, int, int]]:
    """Что обязано лежать в выгрузке: подпись, факт, абсолютный минимум."""
    if relpath == "data.json":
        neighbours = payload.get("neighbours") or []
        shortest = min((len(n.get("items") or []) for n in neighbours), default=0)
        return [
            ("рядов", size(payload, "series"), MIN_MACRO_SERIES),
            ("месяцев инфляции", size(payload, "inflation"), MIN_MACRO_INFLATION),
            ("релизов в календаре", size(payload, "calendar"), MIN_MACRO_CALENDAR),
            ("событий", size(payload, "events"), MIN_MACRO_EVENTS),
            ("разрезов по соседям", len(neighbours), MIN_MACRO_NEIGHBOURS),
            ("стран в самом коротком разрезе соседей", shortest, 3),
        ]
    if relpath == "pulse.json":
        series = payload.get("series") or []
        long_rows = [s for s in series if len(s.get("obs") or []) >= MIN_OBS]
        return [(f"рядов не короче {MIN_OBS} точек", len(long_rows), MIN_PULSE_SERIES)]
    if relpath == "trade/data.json":
        series = payload.get("series") or []
        long_rows = [s for s in series if len(s.get("obs") or []) >= MIN_OBS]
        breakdowns = payload.get("breakdowns") or []
        thinnest = min((len(b.get("items") or []) for b in breakdowns), default=0)
        return [
            (f"рядов не короче {MIN_OBS} точек", len(long_rows), MIN_TRADE_SERIES),
            ("разрезов структуры", len(breakdowns), MIN_TRADE_BREAKDOWNS),
            ("партнёров в самом коротком разрезе", thinnest, MIN_TRADE_PARTNERS),
        ]
    if relpath == "national-fund/data.json":
        return [
            ("месячных точек активов", size(payload, "assets"), MIN_FUND_ASSETS),
            ("годовых точек доходности", size(payload, "returns"), MIN_FUND_RETURNS),
        ]
    if relpath == "budget/oblast.json":
        return [
            (
                "регионов в разрезе доходов",
                size(payload, "regions"),
                MIN_OBLAST_REGIONS,
            )
        ]
    if relpath == "tax/data.json":
        groups = payload.get("groups") or []
        rates = sum(len(g.get("items") or []) for g in groups)
        return [
            ("групп ставок", len(groups), MIN_TAX_GROUPS),
            ("строк со ставками", rates, MIN_TAX_RATES),
            ("базовых величин", size(payload, "base"), MIN_TAX_BASE),
        ]
    if relpath == "tax/budget.json":
        return [
            (
                "областей в разбивке КГД",
                size(payload, "dynamics", "regions"),
                MIN_KGD_REGIONS,
            ),
            (
                "месяцев в разбивке КГД",
                size(payload, "dynamics", "months"),
                MIN_KGD_MONTHS,
            ),
            (
                "видов налогов в структуре",
                size(payload, "structure", "items"),
                MIN_MINFIN_KINDS,
            ),
        ]
    if relpath == "tax/minfin.json":
        return [
            ("месяцев исполнения", size(payload, "monthly"), MIN_MINFIN_MONTHS),
            (
                "видов налогов в последнем отчёте",
                size(payload, "latest", "items"),
                MIN_MINFIN_KINDS,
            ),
        ]
    return []


def parse_stamp(value: str) -> datetime | None:
    text = value.strip().replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=ALMATY)


def dataset_problems(base: Path, now: datetime) -> list[str]:
    found = []
    for relpath, slug in DATASETS.items():
        path = base / relpath
        if not path.exists():
            found.append(f"{relpath}: выгрузки нет, странице {slug} нечем наполняться")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            found.append(f"{relpath}: выгрузка не читается: {exc}")
            continue
        for name, got, want in json_expectations(relpath, payload):
            if got < want:
                found.append(
                    f"{relpath}: {name}: ожидалось не меньше {want}, найдено {got}"
                )
        stamp = parse_stamp(str(payload.get("generated_at") or ""))
        if stamp is None:
            found.append(f"{relpath}: нет generated_at, свежесть не проверить")
            continue
        hours = (now - stamp).total_seconds() / 3600
        if hours > CONTENT_MAX_AGE_HOURS:
            found.append(
                f"{relpath}: данные собраны {stamp:%d.%m.%Y %H:%M}, это "
                f"{hours:.0f} ч назад при пороге {CONTENT_MAX_AGE_HOURS} ч"
            )
    return found


def page_stamp_problems(
    relpath: str, root: Node, slug: str, now: datetime
) -> list[str]:
    """Штамп сборки страницы и даты из будущего в блоке прошедших событий."""
    found = []
    stamps = [
        parse_stamp(n.attrs["datetime"])
        for n in root.walk()
        if n.tag == "time" and "T" in n.attrs.get("datetime", "")
    ]
    stamps = [s for s in stamps if s]
    if slug in STAMPED:
        if not stamps:
            found.append(
                f"{relpath}: нет штампа сборки, свежесть страницы не проверить"
            )
        else:
            hours = (now - max(stamps)).total_seconds() / 3600
            if hours > CONTENT_MAX_AGE_HOURS:
                found.append(
                    f"{relpath}: собрана {max(stamps):%d.%m.%Y %H:%M}, это "
                    f"{hours:.0f} ч назад при пороге {CONTENT_MAX_AGE_HOURS} ч"
                )
    today = now.astimezone(ALMATY).date()
    for anchor in PAST_SECTIONS.get(slug, ()):
        region = region_for(root, anchor)
        if region is None:
            continue
        for node in walk(region):
            if node.tag != "time":
                continue
            if "data-upcoming" in node.attrs:
                continue
            when = parse_stamp(node.attrs.get("datetime", ""))
            if when and when.astimezone(ALMATY).date() > today:
                line = visible_text(list(node.parent.children[1:]))
                found.append(
                    f"{relpath}: в блоке прошедших событий дата из будущего "
                    f"{when:%d.%m.%Y}: «{line[:80].strip()}»"
                )
    return found


WORD_NUMBERS = {
    "двадцать": 20,
    "двадцати": 20,
    "двадцати одного": 21,
    "двадцати одной": 21,
    "двадцати двух": 22,
}
CLAIM = re.compile(
    r"(\d+)\s+регион\w*\s+из\s+(\d+|двадцати одной|двадцати одного|"
    r"двадцати двух|двадцати|двадцать)"
)


def claim_problems(relpath: str, root: Node, slug: str) -> list[str]:
    """Подпись против факта: «12 регионов из двадцати» при 21 объекте."""
    found = []
    totals: dict[int, str] = {}
    for spec in SECTIONS[slug]:
        region = region_for(root, spec.anchor)
        if region is None:
            continue
        rendered = measure(region)["entries"]
        for stated_text, total_text in CLAIM.findall(visible_text(region)):
            stated = int(stated_text)
            total = (
                int(total_text) if total_text.isdigit() else WORD_NUMBERS[total_text]
            )
            totals.setdefault(total, spec.title)
            if stated > total:
                found.append(
                    f"{relpath}: секция «{spec.title}»: подпись говорит про "
                    f"{stated} регионов из {total}, это больше целого"
                )
            if rendered and rendered < stated:
                found.append(
                    f"{relpath}: секция «{spec.title}»: подпись обещает "
                    f"{stated} регионов, в разбивке {rendered} объектов"
                )
    if len(totals) > 1:
        parts = ", ".join(f"{k} ({v})" for k, v in sorted(totals.items()))
        found.append(
            f"{relpath}: подписи спорят о числе регионов в стране: {parts}"
        )
    return found


def list_sizes(region: list[Node]) -> list[int]:
    sizes = []
    for node in walk(region):
        if node.tag in ("ol", "ul"):
            sizes.append(sum(1 for c in node.walk() if c.tag == "li"))
    return sizes


def load_json(base: Path, relpath: str) -> dict:
    path = base / relpath
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def cross_problems(base: Path, relpath: str, root: Node, slug: str) -> list[str]:
    """Сверка отрисованного с выгрузкой. Пороги абсолютные, выгрузка добавляет
    второе условие: отрисовать меньше, чем собрано, тоже потеря."""
    found = []
    if slug == "trade":
        region = region_for(root, "Структура торговли")
        sizes = sorted(list_sizes(region or []), reverse=True)
        full = [size for size in sizes if size >= MIN_TRADE_PARTNERS]
        if len(full) < MIN_TRADE_BREAKDOWNS:
            found.append(
                f"{relpath}: разрезов по {MIN_TRADE_PARTNERS} партнёров "
                f"{len(full)}, ожидалось {MIN_TRADE_BREAKDOWNS}; "
                f"длины списков: {sizes[:5]}"
            )
    if slug == "budget":
        region = region_for(root, "Кто платит: регионы") or []
        radios = sum(
            1
            for n in walk(region)
            if n.tag == "input" and n.attrs.get("name") == "drill-region"
        )
        # Разбивка КГД видна двумя способами: переключатель региона и рейтинг.
        # Схлопнуться может любой из них, поэтому проверяем оба, а не максимум.
        counts = {"кнопок выбора региона": radios} if radios else {}
        counts["строк в рейтинге регионов"] = max(list_sizes(region), default=0)
        for name, got in counts.items():
            if got < MIN_KGD_REGIONS:
                found.append(
                    f"{relpath}: в разбивке КГД {name} {got}, ожидалось "
                    f"не меньше {MIN_KGD_REGIONS} (областей в стране 20)"
                )
        dynamics = load_json(base, "tax/budget.json").get("dynamics") or {}
        collected = size(dynamics, "regions")
        drawn = min(counts.values())
        if collected and drawn < collected:
            found.append(
                f"{relpath}: в выгрузке {collected} областей, на странице {drawn}"
            )
        chart = region_for(root, "Помесячно, факт против плана") or []
        bars = sum(
            1
            for n in walk(chart)
            if n.tag == "rect" and "bar" in n.attrs.get("class", "")
        )
        if bars < MIN_MINFIN_MONTHS:
            found.append(
                f"{relpath}: в графике исполнения {bars} месяцев, ожидалось "
                f"не меньше {MIN_MINFIN_MONTHS}"
            )
    if slug == "tax":
        rates = 0
        for spec in SECTIONS["tax"]:
            if not spec.anchor.startswith("#"):
                continue
            rates += measure(region_for(root, spec.anchor) or [])["rows"]
        if rates < MIN_TAX_RATES:
            found.append(
                f"{relpath}: строк со ставками {rates}, ожидалось "
                f"не меньше {MIN_TAX_RATES}"
            )
    return found


def content_problems(base: Path, now: datetime | None = None) -> list[str]:
    """Проблемы наполнения: страница собралась, но данных на ней нет."""
    now = now or datetime.now(timezone.utc)
    found = dataset_problems(base, now)
    found.extend(methodology_problems(base))
    for slug, relpath in PAGES.items():
        path = base / relpath
        if not path.exists():
            continue
        document = path.read_text(encoding="utf-8")
        root = Tree(document).root
        main = next((n for n in root.walk() if n.tag == "main"), None)
        if main is None:
            found.append(f"{relpath}: нет <main>, на странице только шапка и подвал")
            continue
        if slug == "" and "Как читать радар" in visible_text(list(root.walk())):
            found.append(
                f"{relpath}: технический текст «Как читать радар» должен быть на отдельной странице"
            )
        found.extend(section_problems(relpath, root, slug))
        found.extend(chart_problems(relpath, root))
        found.extend(table_problems(relpath, root))
        found.extend(unresolved_problems(relpath, root))
        found.extend(page_stamp_problems(relpath, root, slug, now))
        found.extend(claim_problems(relpath, root, slug))
        found.extend(cross_problems(base, relpath, root, slug))
    return found

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Использование: page_check.py КАТАЛОГ (например public/macroradar)"
        )
    base = Path(sys.argv[1])
    structure = problems(base)
    content = content_problems(base)
    if structure:
        print("структура собрана неверно:")
        for line in structure:
            print(" -", line)
    if content:
        print("наполнение неполное:")
        for line in content:
            print(" -", line)
    if structure or content:
        print(
            f"итог: структурных проблем {len(structure)}, "
            f"проблем наполнения {len(content)}"
        )
        raise SystemExit(1)
    print(f"страниц проверено: {len(PAGES)}, проверок наполнения пройдено")


if __name__ == "__main__":
    main()
