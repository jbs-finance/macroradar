"""Контракт единственной публичной страницы Macro Radar."""

import json
import re
from pathlib import Path

from build_macroradar import build


HERE = Path(__file__).resolve().parent


def data(name: str) -> dict:
    return json.loads((HERE / "out" / name).read_text(encoding="utf-8"))


def national_fund() -> dict:
    return {
        "generated_at": "2026-09-05T12:00:00+00:00",
        "assets": [{"date": "2016-09", "value": 64.537}, {"date": "2025-12", "value": 60.1}, {"date": "2026-07", "value": 66.121}],
        "assets_source": "https://nationalbank.kz/assets",
        "returns": [{"date": "2016", "value": 0.84}, {"date": "2025", "value": 15.09}],
        "returns_source": "https://nationalbank.kz/returns",
        "issues": [],
    }


def page() -> str:
    return build(data("radar.json"), data("pulse.json"), data("trade.json"), national_fund(), data("tax.json"), data("minfin.json"), data("budget.json"), data("oblast.json"))


def test_root_has_all_analyses_as_tabs_and_metadata():
    document = page()
    assert 'rel="canonical" href="https://jbs.finance/macroradar/"' in document
    assert 'property="og:url" content="https://jbs.finance/macroradar/"' in document
    assert '"@type": "CollectionPage"' in document
    for view in ("hub", "macro", "trade", "fund", "budget", "tax"):
        assert f'id="view-{view}"' in document
        assert f'for="view-{view}"' in document


def test_root_includes_fund_portfolio_and_no_analysis_page_links():
    document = page()
    assert "Состав сберегательного портфеля" in document
    assert "36,3%" in document
    assert "Альтернативные инструменты" in document
    assert "не доли всего Нацфонда на текущую дату" in document
    assert not re.search(r'href="/macroradar/(macro|trade|national-fund|budget|tax)/"', document)
    assert 'href="#macro"' not in document


def test_root_is_self_contained_and_csp_prohibits_executable_scripts():
    document = page()
    assert "script-src 'none'" in document
    assert re.findall(r"<script[^>]*>", document) == ['<script type="application/ld+json">']
    assert "onclick=" not in document
