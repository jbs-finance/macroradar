"""Контракт отдельной Cloudflare Pages-сборки Macro Radar."""

import json
from pathlib import Path

from scripts.build_pages import (
    COPIES,
    HEADERS,
    PAGE_PATHS,
    PUBLIC_PREFIX,
    SITE_URL,
    documents,
    load_inputs,
    verify_structure,
    write_tree,
)

HERE = Path(__file__).resolve().parent


def test_fixture_build_preserves_jbs_macroradar_url_contract(tmp_path: Path):
    data = load_inputs(Path("unused"), fixtures=True)
    target = tmp_path / "dist"
    write_tree(target, data, SITE_URL)

    assert (target / "index.html").exists()
    for relpath in PAGE_PATHS.values():
        assert (target / relpath).exists(), relpath
    hub = (target / "index.html").read_text(encoding="utf-8")
    assert 'href="/macroradar/macro/"' in hub
    assert 'https://jbs.finance/macroradar/' in hub
    macro = (target / "macro/index.html").read_text(encoding="utf-8")
    assert 'https://jbs.finance/ai/macroradar/' in macro
    assert verify_structure(target, SITE_URL, PUBLIC_PREFIX) == []


def test_fixture_build_can_use_root_urls_behind_another_domain(tmp_path: Path):
    data = load_inputs(Path("unused"), fixtures=True)
    target = tmp_path / "dist"
    write_tree(target, data, "https://macroradar.jbs.finance", "")

    hub = (target / "index.html").read_text(encoding="utf-8")
    assert 'href="/macro/"' in hub
    assert 'href="/macroradar/' not in hub
    assert 'https://macroradar.jbs.finance/' in hub
    assert verify_structure(target, "https://macroradar.jbs.finance", "") == []


def test_methodology_contains_technical_journal_not_macro_page():
    data = load_inputs(Path("unused"), fixtures=True)
    pages = documents(data, SITE_URL)

    macro = pages["macro"]
    methodology = pages["methodology"]
    for marker in (
        "Что изменилось",
        "Ближайшие релизы",
        "Источники и свежесть данных",
        "Как читать эти цифры",
    ):
        assert marker not in macro
        assert marker in methodology
    assert 'id="events"' in methodology
    assert 'id="calendar"' in methodology
    assert 'id="sources"' in methodology


def test_pages_headers_prohibit_scripts_for_every_static_route(tmp_path: Path):
    data = load_inputs(Path("unused"), fixtures=True)
    target = tmp_path / "dist"
    write_tree(target, data, SITE_URL)

    assert (target / "_headers").read_text(encoding="utf-8") == HEADERS
    assert HEADERS.startswith("/*\n")
    assert "script-src 'none'" in HEADERS
    assert "default-src 'none'" in HEADERS
    assert "connect-src 'none'" in HEADERS


def test_build_copies_every_dataset_expected_by_page_check(tmp_path: Path):
    data = load_inputs(Path("unused"), fixtures=True)
    target = tmp_path / "dist"
    write_tree(target, data, SITE_URL)

    assert set(COPIES.values()) == set(__import__("page_check").DATASETS)
    for key, relpath in COPIES.items():
        assert json.loads((target / relpath).read_text(encoding="utf-8")) == data[key]


def test_deploy_workflow_keeps_daily_refresh_and_post_deploy_smoke():
    workflow = (HERE / ".github/workflows/deploy-macroradar-pages.yml").read_text(
        encoding="utf-8"
    )
    assert 'cron: "0 4 * * *"' in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "timeout-minutes: 30" in workflow
    assert "pages deploy dist --project-name=jbs-macroradar --branch=main" in workflow
    assert "Deploy path-preserving Macro Radar Worker" in workflow
    assert "Smoke test Macro Radar public URL" in workflow
    assert "jbs.finance/macroradar" in workflow
    assert "x-macroradar-upstream: jbs-macroradar-pages" in workflow
    assert '--dump-header "$headers"' in workflow
    assert "check_root_redirect" in workflow
    assert "name: Restore UN Comtrade trade snapshot" in workflow
    assert "uses: actions/cache@v4" in workflow
    assert "path: out/trade.json" in workflow
    assert "key: macroradar-trade-${{ runner.os }}-${{ hashFiles('trade.py') }}" in workflow
    assert "macroradar-trade-${{ runner.os }}-" in workflow
    assert "name: Reject stale trade data restored from cache" in workflow
    assert 'if row.get("stale")' in workflow
    assert "торговые данные не обновлены, публикация остановлена" in workflow
    for step in (
        "Collect macro pulse",
        "Collect trade data",
        "Derive macro radar",
        "Collect KGD budget",
        "Collect Minfin data",
        "Collect regional budget data",
        "Collect tax data",
        "Collect National Fund data",
    ):
        assert f"name: {step}" in workflow
    for path in ("/macroradar/", "/macroradar/macro/", "/macroradar/methodology/"):
        assert f"check_page {path}" in workflow


def test_worker_only_handles_macroradar_public_prefix():
    source = (HERE / "worker/src/index.mjs").read_text(encoding="utf-8")
    config = (HERE / "worker/wrangler.toml").read_text(encoding="utf-8")

    assert 'const PUBLIC_PREFIX = "/macroradar"' in source
    assert "!SAFE_METHODS.has(request.method)" in source
    assert 'return workerResponse("Not found", { status: 404 })' in source
    assert 'headers.delete("cookie")' in source
    assert 'headers.delete("authorization")' in source
    assert 'jbs.finance/macroradar/*' in config
    assert 'jbs.finance/macroradar", zone_name' in config
    assert 'PAGES_ORIGIN = "https://jbs-macroradar.pages.dev"' in config
    assert 'headers.set(UPSTREAM_HEADER, UPSTREAM_HEADER_VALUE)' in source
