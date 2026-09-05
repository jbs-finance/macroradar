"""Структурная проверка собранной страницы радара.

Страница переключает вкладки без скриптов: CSP стоит `script-src 'none'`, поэтому
показ панели держится на соседском селекторе `#view-x:checked ~ ... .panel-x`.
Селектор работает молча: стоит панели уехать из соседей радиокнопки, вкладка
открывается пустой, а все проверки по наличию идентификаторов остаются зелёными.
Здесь проверяется именно достижимость, а не присутствие разметки.
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

VIEWS = {"view-hub": "panel-hub", "view-macro": "panel-macro", "view-trade": "panel-trade", "view-fund": "panel-national-fund", "view-budget": "panel-budget", "view-tax": "panel-tax"}


class Node:
    def __init__(self, tag: str, attrs: list, parent: "Node | None"):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def walk(self):
        for child in self.children:
            yield child
            yield from child.walk()

    def descends_from(self, other: "Node") -> bool:
        node = self.parent
        while node is not None:
            if node is other:
                return True
            node = node.parent
        return False


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


def reachable(source: Node, target: Node) -> bool:
    """Правило `source:checked ~ ... target` срабатывает, только если target лежит
    в самом последующем соседе source или внутри него."""
    siblings = source.parent.children
    after = siblings[siblings.index(source) + 1:]
    return any(target is node or target.descends_from(node) for node in after)


def problems(document: str) -> list[str]:
    tree = Tree(document)
    inputs = {node.attrs.get("id"): node for node in tree.root.walk() if "tab-state" in node.classes}
    panels = {name: node for node in tree.root.walk() for name in node.classes if name.startswith("panel-")}
    found = []
    for view, panel in VIEWS.items():
        if view not in inputs:
            found.append(f"нет радиокнопки #{view}")
        elif panel not in panels:
            found.append(f"нет панели .{panel}")
        elif not reachable(inputs[view], panels[panel]):
            found.append(f"панель .{panel} не показать через #{view}:checked")
    every = [node for node in tree.root.walk() if "tab-panel" in node.classes]
    for node in every:
        if any(node.descends_from(other) for other in every):
            found.append(f"вкладка {' '.join(node.classes)} вложена в другую вкладку")
    navs = [node for node in tree.root.walk() if "tabs" in node.classes]
    if not navs:
        found.append("нет панели вкладок .tabs")
    else:
        for view in VIEWS:
            if view in inputs and not reachable(inputs[view], navs[0]):
                found.append(f"подсветку вкладки {view} не применить")
    return found


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Использование: page_check.py PAGE.html")
    found = problems(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if found:
        print("вкладки собраны неверно:")
        for line in found:
            print(" -", line)
        raise SystemExit(1)
    print(f"вкладки достижимы: {len(VIEWS)}")


if __name__ == "__main__":
    main()
