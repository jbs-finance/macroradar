"""Контракт связки Macro Radar: хаб плюс пять самостоятельных тем.

Раньше вкладки жили на одном URL через соседский CSS-селектор. Регресс, который
эти тесты обязаны ловить: страница темы должна существовать отдельным файлом,
со своим canonical и ровно одним h1, а не панелью внутри хаба.
"""

import json
import re
from pathlib import Path

from build_budget import build as build_budget
from build_macroradar import build as build_hub
from build_national_fund import build as build_national_fund
from build_radar import build as build_radar
from build_tax import build as build_tax
from build_trade import build as build_trade
from page_check import PAGES, problems

HERE = Path(__file__).resolve().parent

TOPICS = ("macro", "trade", "national-fund", "budget", "tax")


def data(name: str) -> dict:
    return json.loads((HERE / "fixtures" / name).read_text(encoding="utf-8"))


def national_fund_data() -> dict:
    return {
        "generated_at": "2026-09-05T12:00:00+00:00",
        "assets": [
            {"date": "2016-09", "value": 64.537},
            {"date": "2025-12", "value": 60.1},
            {"date": "2026-07", "value": 66.121},
        ],
        "assets_source": "https://nationalbank.kz/assets",
        "returns": [{"date": "2016", "value": 0.84}, {"date": "2025", "value": 15.09}],
        "returns_source": "https://nationalbank.kz/returns",
        "issues": [],
    }


def documents() -> dict[str, str]:
    return {
        "": build_hub(),
        "macro": build_radar(
            data("radar.json"), data("pulse.json"), data("trade.json")
        ),
        "trade": build_trade(data("trade.json")),
        "national-fund": build_national_fund(national_fund_data()),
        "budget": build_budget(
            data("minfin.json"), data("budget.json"), data("oblast.json")
        ),
        "tax": build_tax(data("tax.json")),
    }


def write_pages(base: Path, pages: dict[str, str]) -> None:
    for slug, document in pages.items():
        path = base / PAGES[slug]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document, encoding="utf-8")


def test_hub_links_to_five_topic_pages_with_own_urls():
    document = documents()[""]
    assert 'rel="canonical" href="https://jbs.finance/macroradar/"' in document
    assert 'property="og:url" content="https://jbs.finance/macroradar/"' in document
    assert '"@type": "CollectionPage"' in document
    for topic in TOPICS:
        assert f'href="/macroradar/{topic}/"' in document
        assert f'"url": "https://jbs.finance/macroradar/{topic}/"' in document


def test_hub_has_no_leftover_tab_gluing_and_single_h1():
    document = documents()[""]
    assert 'class="tab-state"' not in document
    assert "#view-" not in document
    assert document.count("<h1") == 1


def test_hub_links_to_methodology_only_from_the_footer():
    document = documents()[""]
    assert "Как читать радар" not in document
    assert document.count('href="/macroradar/methodology/"') == 1
    footer = re.search(r"<footer>.*?</footer>", document, flags=re.S)
    assert footer is not None
    assert ">Методика и источники</a>" in footer.group(0)


def test_hub_is_self_contained_and_csp_prohibits_executable_scripts():
    document = documents()[""]
    assert "script-src 'none'" in document
    assert re.findall(r"<script[^>]*>", document) == [
        '<script type="application/ld+json">'
    ]
    assert "onclick=" not in document


def test_each_topic_page_has_own_canonical_and_single_h1():
    pages = documents()
    for topic in TOPICS:
        document = pages[topic]
        expected = f"https://jbs.finance/macroradar/{topic}/"
        assert f'rel="canonical" href="{expected}"' in document
        assert document.count("<h1") == 1
        assert 'class="tab-state"' not in document
        assert "#view-" not in document


def test_each_topic_page_links_back_to_the_other_five():
    pages = documents()
    for topic in TOPICS:
        document = pages[topic]
        for other in ("",) + TOPICS:
            if other == topic:
                continue
            href = f"/macroradar/{other}/" if other else "/macroradar/"
            assert f'href="{href}"' in document


def test_full_page_set_passes_the_structural_gate(tmp_path):
    write_pages(tmp_path, documents())
    assert problems(tmp_path) == []
