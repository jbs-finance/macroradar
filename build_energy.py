"""Сборка статической страницы годового баланса энергии из out/energy.json.

Запуск: .venv/bin/python build_energy.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from build_pulse import STYLE, spark
from layout import (
    ACCESSIBILITY_STYLE,
    CTA_STYLE,
    HEADER_STYLE,
    NO_DATA_STYLE,
    cta_block,
    detail_footer,
    freshness_badge,
    issues_notice,
    meta_tags,
    no_data,
    site_header,
    skip_link,
)

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "energy.json"
DEFAULT_OUT = HERE / "out" / "energy.html"

ORDER = [
    "kz.energy.intensity",
    "kz.energy.primary_consumption",
    "kz.energy.final_consumption",
    "kz.energy.renewable_share",
]

ENERGY_STYLE = """
.energy-hero { padding-block: clamp(1.5rem, 5vw, 2.5rem) 1rem; max-width: 760px; }
.energy-hero h1 { max-width: 25ch; }
.energy-grid { display: grid; gap: var(--sp); grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }
.energy-grid > * { min-width: 0; }
.energy-card .source { margin: 0.75rem 0 0; font-size: 0.8125rem; overflow-wrap: anywhere; }
.energy-card .source a { color: inherit; }
.energy-card .observation { margin: 0.3rem 0 0; color: var(--muted-fg); font-size: 0.875rem; }
.energy-card .failure { margin: 0.75rem 0 0; padding: 0.55rem 0.7rem; background: var(--muted); border-left: 3px solid var(--accent); font-size: 0.8125rem; }
.series-table { width: 100%; table-layout: fixed; border-collapse: collapse; margin-top: 0.85rem; font-variant-numeric: tabular-nums; }
.energy-card .series-table { min-width: 0; max-width: 100%; }
.series-table caption { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.series-table th, .series-table td { padding: 0.5rem; border-bottom: 1px solid var(--muted); text-align: right; }
.series-table th:first-child, .series-table td:first-child { padding-left: 0; text-align: left; }
.series-table th { color: var(--muted-fg); font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em; }
"""


def exact_value(value: object) -> str:
    """Показывает значение наблюдения без округления или производного расчёта."""
    if isinstance(value, float):
        raw = format(value, ".15g")
    else:
        raw = str(value)
    integer, dot, fraction = raw.partition(".")
    sign = "" if not integer.startswith("-") else "-"
    digits = integer.removeprefix("-")
    groups = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    rendered = "\u00a0".join(reversed(groups)) or "0"
    return f"{sign}{rendered}{',' if dot else ''}{fraction}"


def rows(obs: list[dict]) -> str:
    return "\n".join(
        f"<tr><td>{html.escape(str(point.get('date', '')))}</td>"
        f"<td>{exact_value(point.get('value', ''))}</td></tr>"
        for point in reversed(obs)
    )


def series_card(series: dict) -> str:
    observations = series.get("obs") or []
    if not observations:
        return no_data(f"для ряда {series.get('name_ru', 'без названия')} нет наблюдений")
    latest = observations[-1]
    stale = bool(series.get("stale"))
    failure = ""
    if stale:
        failure = (
            '<p class="failure"><strong>Последняя сборка не подтвердила ряд.</strong> '
            f"Показан сохранённый срез: {html.escape(str(series.get('note') or 'причина не указана'))}</p>"
        )
    source_url = str(series.get("source_url", ""))
    source_link = (
        f'<a href="{html.escape(source_url, quote=True)}">{html.escape(source_url)}</a>'
        if source_url
        else "адрес источника не передан"
    )
    badge = freshness_badge(str(latest.get("date", "")), "A", stale)
    return f'''      <article class="card energy-card">
        <header class="card-head"><h2>{html.escape(str(series.get("name_ru", "")))}</h2>{badge}</header>
        <p class="value"><span class="num">{exact_value(latest.get("value", ""))}</span>
          <span class="unit">{html.escape(str(series.get("unit", "")))}</span></p>
        <p class="observation">Последнее наблюдение: {html.escape(str(latest.get("date", "")))} год.</p>
        {spark(observations)}
        <p class="source">Источник: {html.escape(str(series.get("source", "Бюро национальной статистики")))}.<br>{source_link}</p>
        {failure}
        <table class="series-table"><caption class="sr-only">Годовые наблюдения: {html.escape(str(series.get("name_ru", "")))}</caption>
          <thead><tr><th scope="col">Год</th><th scope="col">Значение</th></tr></thead><tbody>{rows(observations)}</tbody></table>
      </article>'''


def build(data: dict) -> str:
    by_id = {item.get("series_id"): item for item in data.get("series", [])}
    cards = "\n".join(series_card(by_id[key]) for key in ORDER if key in by_id)
    missing = [key for key in ORDER if key not in by_id]
    if missing:
        cards += no_data("не собраны ряды: " + ", ".join(missing))
    if not cards:
        cards = no_data("годовые ряды БНС не собраны")
    generated = datetime.fromisoformat(data["generated_at"])
    return TEMPLATE.format(
        meta=meta_tags(
            "Энергетический баланс Казахстана: годовые показатели БНС",
            "Четыре годовых показателя энергетического баланса Казахстана из Бюро национальной статистики.",
            "/macroradar/energy/",
        ),
        style=STYLE + HEADER_STYLE + ACCESSIBILITY_STYLE + CTA_STYLE + NO_DATA_STYLE + ENERGY_STYLE,
        header=site_header("energy"),
        skip_link=skip_link(),
        generated=generated.strftime("%d.%m.%Y %H:%M UTC"),
        generated_iso=generated.isoformat(),
        issues=issues_notice(data.get("issues")),
        cards=cards,
        cta=cta_block(),
        footer=detail_footer(date.today().year),
    )


TEMPLATE = '''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{meta}<title>Энергетический баланс Казахстана</title><style>{style}</style></head><body>
{skip_link}{header}<div class="wrap"><header class="energy-hero"><h1>Энергетический баланс Казахстана</h1>
<p class="lede">Годовые национальные ряды Бюро национальной статистики. Это не монитор валовой выработки электроэнергии: такой машиночитаемый ряд здесь не заявлен.</p>
<p class="updated">Собрано <time datetime="{generated_iso}">{generated}</time></p></header>{issues}
<main id="main-content"><h2>Годовые показатели</h2><div class="energy-grid">{cards}</div>{cta}</main>{footer}</div></body></html>'''


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(json.loads(dataset.read_text(encoding="utf-8"))), encoding="utf-8")


if __name__ == "__main__":
    main()
