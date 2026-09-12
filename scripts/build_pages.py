#!/usr/bin/env python3
"""Собирает самостоятельный статический сайт Macro Radar для Cloudflare Pages.

Генераторы остаются общими с публикацией на jbs.finance. Этот адаптер только
раскладывает результат в корневое дерево Pages и детерминированно заменяет
публичный URL-контракт. По умолчанию файл ``dist/macro/index.html`` обслуживается
через ``https://jbs.finance/macroradar/macro/`` Worker-прокси, который снимает
префикс только перед обращением к Pages. CTA на основной сайт не меняется.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_budget import build as build_budget
from build_macroradar import build as build_hub
from build_national_fund import build as build_national_fund
from build_radar import (
    build as build_radar,
    calendar_markup,
    events_markup,
    reading_guidance_markup,
    sources_rows,
)
from build_tax import build as build_tax
from build_trade import build as build_trade
import page_check

SITE_URL = "https://jbs.finance"
PUBLIC_PREFIX = "/macroradar"
PAGE_PATHS = {
    "hub": "index.html",
    "macro": "macro/index.html",
    "trade": "trade/index.html",
    "national_fund": "national-fund/index.html",
    "budget": "budget/index.html",
    "tax": "tax/index.html",
    "methodology": "methodology/index.html",
}
INPUTS = {
    "radar": "radar.json",
    "pulse": "pulse.json",
    "trade": "trade.json",
    "national_fund": "national_fund.json",
    "budget": "budget.json",
    "minfin": "minfin.json",
    "oblast": "oblast.json",
    "tax": "tax.json",
}
COPIES = {
    "radar": "data.json",
    "pulse": "pulse.json",
    "trade": "trade/data.json",
    "national_fund": "national-fund/data.json",
    "oblast": "budget/oblast.json",
    "tax": "tax/data.json",
    "budget": "tax/budget.json",
    "minfin": "tax/minfin.json",
}
HEADERS = """/*
  Content-Security-Policy: default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'self' https://jbs.finance; font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
  Referrer-Policy: strict-origin-when-cross-origin
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
"""


def fixture_national_fund() -> dict:
    """Малый детерминированный аналог выгрузки НБРК для offline-сборки."""
    assets = []
    for offset in range(120):
        year = 2016 + (6 + offset) // 12
        month = (6 + offset) % 12 + 1
        assets.append({"date": f"{year}-{month:02d}", "value": 60 + offset / 10})
    returns = [
        {"date": str(2016 + year), "value": round(1.2 + year * 0.31, 2)}
        for year in range(10)
    ]
    return {
        "generated_at": "2026-09-05T12:00:00+00:00",
        "assets": assets,
        "assets_source": "https://nationalbank.kz/ru/page/aktivy-nacionalnogo-fonda",
        "returns": returns,
        "returns_source": "https://nationalbank.kz/ru/page/investicionnyy-dohod",
        "issues": [],
    }


def load_inputs(data_dir: Path, fixtures: bool) -> dict[str, dict]:
    source_dir = ROOT / "fixtures" if fixtures else data_dir
    loaded = {}
    for key, filename in INPUTS.items():
        if fixtures and key == "national_fund":
            loaded[key] = fixture_national_fund()
            continue
        path = source_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"не найдена выгрузка: {path}")
        loaded[key] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def methodology(radar: dict, pulse: dict) -> str:
    """Техническое приложение к рабочей странице Macro Radar.

    Здесь остаются динамические сведения, нужные для проверки данных, но не для
    ежедневного чтения показателей: лента изменений, ожидаемые релизы и
    построчная свежесть рядов.
    """
    rows = sources_rows(list(pulse.get("series", [])) + list(radar.get("series", [])))
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Методика и источники Macro Radar Казахстана">
<link rel="canonical" href="https://jbs.finance/macroradar/methodology/"><title>Методика и источники Macro Radar</title>
<style>body{{max-width:70rem;margin:2rem auto;padding:0 1rem;font:16px/1.6 system-ui;color:#1c1c2e;background:#f8f5f0}}a{{color:#a8522f}}section{{margin:2.5rem 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(18rem,1fr));gap:1.5rem}}.panel{{padding:1.25rem;background:#fff;border:1px solid #ded5ca;border-radius:.75rem}}ol{{padding-left:1.2rem}}li{{margin:.55rem 0}}time{{font-family:ui-monospace,SFMono-Regular,monospace;color:#6e6259;font-size:.9em}}.kind{{display:inline-block;width:.5rem;height:.5rem;border-radius:50%;background:#a8522f;margin-right:.35rem}}.kind-stat{{background:#556b8e}}.type{{color:#6e6259;font-size:.9em}}.table-wrap{{overflow-x:auto;background:#fff;border:1px solid #ded5ca;border-radius:.75rem}}table{{border-collapse:collapse;width:100%;min-width:48rem}}th,td{{padding:.7rem .8rem;text-align:left;vertical-align:top;border-bottom:1px solid #e7dfd5}}th{{color:#6e6259;font-size:.85rem}}details{{background:#fff;border:1px solid #ded5ca;border-radius:.75rem;padding:1rem}}summary{{cursor:pointer;font-weight:700}}</style></head>
<body><main id="main-content"><p><a href="/macroradar/">← Macro Radar</a></p><h1>Методика и источники</h1>
<h2>Как читать отчёт</h2><p>Каждый показатель содержит дату, источник и пояснение. Сначала смотри на свежесть ряда, затем на динамику, а для решения сверяй цифры с первоисточником.</p>
<section class="grid" aria-label="Журнал данных"><section class="panel feed" id="events" aria-labelledby="events-title"><h2 id="events-title">Что изменилось</h2>{events_markup(radar.get("events", []))}</section><section class="panel feed" id="calendar" aria-labelledby="calendar-title"><h2 id="calendar-title">Ближайшие релизы</h2>{calendar_markup(radar.get("calendar", []))}</section></section>
<section id="sources" aria-labelledby="sources-title"><h2 id="sources-title">Источники и свежесть данных</h2><p>Используются открытые данные БНС, НБРК, Минфина, КГД, Всемирного банка и UN Comtrade. Если источник не обновился, последняя точка помечается как устаревшая, а не заменяется оценкой.</p><div class="table-wrap"><table><thead><tr><th scope="col">Показатель</th><th scope="col">Источник</th><th scope="col">Точек</th><th scope="col">Последняя</th><th scope="col">Забрано</th><th scope="col">Статус</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<details id="reading-guidance"><summary>Как читать эти цифры</summary><div>{reading_guidance_markup()}</div></details>
<p>© JB Solutions</p></main></body></html>"""


def normalized_prefix(path_prefix: str) -> str:
    """Возвращает пустой префикс либо URL-путь без завершающего слеша."""
    if path_prefix in ("", "/"):
        return ""
    return "/" + path_prefix.strip("/")


def standalone(
    document: str, site_url: str, path_prefix: str = PUBLIC_PREFIX
) -> str:
    """Переводит URL-контракт радара, не меняя физическое дерево Pages."""
    prefix = normalized_prefix(path_prefix)
    public_root = f"{site_url.rstrip('/')}{prefix}/"
    document = document.replace("https://jbs.finance/macroradar/", public_root)
    # Заменяем путь только в начале URL-значения. Глобальная замена ломала CTA
    # ``https://jbs.finance/ai/macroradar/``, который намеренно остаётся на
    # основном сайте, а не в отдельном продукте.
    return document.replace('"/macroradar/', f'"{prefix}/')


def documents(
    data: dict[str, dict], site_url: str, path_prefix: str = PUBLIC_PREFIX
) -> dict[str, str]:
    raw = {
        "hub": build_hub(),
        "macro": build_radar(data["radar"], data["pulse"], data["trade"]),
        "trade": build_trade(data["trade"]),
        "national_fund": build_national_fund(data["national_fund"]),
        "budget": build_budget(data["minfin"], data["budget"], data["oblast"]),
        "tax": build_tax(data["tax"]),
        "methodology": methodology(data["radar"], data["pulse"]),
    }
    return {
        name: standalone(document, site_url, path_prefix)
        for name, document in raw.items()
    }


def write_tree(
    target: Path, data: dict[str, dict], site_url: str, path_prefix: str = PUBLIC_PREFIX
) -> None:
    if target.exists():
        raise FileExistsError(
            f"каталог сборки уже существует: {target}; выбери новый --output"
        )
    target.mkdir(parents=True)
    (target / "_headers").write_text(HEADERS, encoding="utf-8")
    for name, document in documents(data, site_url, path_prefix).items():
        path = target / PAGE_PATHS[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document, encoding="utf-8")
    for key, relpath in COPIES.items():
        path = target / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data[key], ensure_ascii=False), encoding="utf-8")


def verify(
    target: Path,
    site_url: str,
    path_prefix: str = PUBLIC_PREFIX,
    now: datetime | None = None,
) -> list[str]:
    old_site, old_path = page_check.SITE, page_check.BASE_PATH
    try:
        page_check.configure_urls(site_url, path_prefix or "/")
        return page_check.problems(target) + page_check.content_problems(target, now=now)
    finally:
        page_check.configure_urls(old_site, old_path)


def verify_structure(
    target: Path, site_url: str, path_prefix: str = PUBLIC_PREFIX
) -> list[str]:
    """Проверяет URL и перелинковку offline fixtures без заявления о свежести."""
    old_site, old_path = page_check.SITE, page_check.BASE_PATH
    try:
        page_check.configure_urls(site_url, path_prefix or "/")
        return page_check.problems(target)
    finally:
        page_check.configure_urls(old_site, old_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "out")
    parser.add_argument("--fixtures", action="store_true", help="offline fixtures из репозитория")
    parser.add_argument("--site-url", default=SITE_URL)
    parser.add_argument(
        "--path-prefix",
        default=PUBLIC_PREFIX,
        help="публичный префикс URL, который Worker снимает перед Pages",
    )
    args = parser.parse_args()

    data = load_inputs(args.data_dir, args.fixtures)
    write_tree(args.output, data, args.site_url, args.path_prefix)
    found = (
        verify_structure(args.output, args.site_url, args.path_prefix)
        if args.fixtures
        else verify(args.output, args.site_url, args.path_prefix)
    )
    if found:
        for line in found:
            print(f" - {line}")
        raise SystemExit("Pages-сборка не прошла page_check")
    if args.fixtures:
        print("Fixture-сборка проверена по структуре: свежесть источников не заявляется")
    print(f"Pages-сборка готова: {args.output}")


if __name__ == "__main__":
    main()
