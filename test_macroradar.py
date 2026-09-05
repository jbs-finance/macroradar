"""Контракт статической главной Macro Radar."""

import re

from build_macroradar import build


def test_hub_has_all_analysis_links_and_metadata():
    page = build()
    assert 'rel="canonical" href="https://jbs.finance/macroradar/"' in page
    assert 'property="og:url" content="https://jbs.finance/macroradar/"' in page
    assert '"@type": "CollectionPage"' in page
    for path in ("macro", "trade", "budget", "tax"):
        assert f'href="/macroradar/{path}/"' in page


def test_hub_is_self_contained_and_csp_prohibits_executable_scripts():
    page = build()
    assert "script-src 'none'" in page
    scripts = re.findall(r"<script[^>]*>", page)
    assert scripts == ['<script type="application/ld+json">']
    assert "onclick=" not in page
    assert "/" + "radar/" not in page
