"""Структурная проверка набора страниц Macro Radar.

Хаб и пять тем разъехались по собственным адресам: у каждой свой файл, свой h1
и свой canonical. Проверка идёт по каталогу public/macroradar, а не по одному
файлу: нужно поймать не только сломанную разметку внутри страницы, но и
разрыв перелинковки между страницами, и возврат прежней склейки вкладок.
"""

from __future__ import annotations

import re
import sys
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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Использование: page_check.py КАТАЛОГ (например public/macroradar)"
        )
    base = Path(sys.argv[1])
    found = problems(base)
    if found:
        print("страницы собраны неверно:")
        for line in found:
            print(" -", line)
        raise SystemExit(1)
    print(f"страниц проверено: {len(PAGES)}")


if __name__ == "__main__":
    main()
