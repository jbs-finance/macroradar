"""Сборка статической страницы отраслевых рядов по областям из out/industry.json.

Отличие от build_energy.py: там 4 национальных ряда, каждый со своей полной
историей, здесь 20 областей на 2 показателя, только уровень области (решение
владельца 22.09.2026). Карточка на регион с полной историей растянула бы страницу
на 40 таблиц, поэтому вид другой: один ранжированный список на показатель, строка
на регион, последнее значение и год, без карточек.

Запуск: .venv/bin/python build_industry.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from build_pulse import STYLE
from industry import INDUSTRY_SERIES
from regional import REGIONS
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
DATASET = HERE / "out" / "industry.json"
DEFAULT_OUT = HERE / "out" / "industry.html"

# Отображение сортируется по русскому имени, а не по порядку REGIONS в industry.py
# (там порядок это порядок обнаружения term id, не алфавит).
REGIONS_BY_SLUG = {slug: name_ru for _term, name_ru, slug in REGIONS}
REGION_ORDER = sorted(REGIONS_BY_SLUG, key=lambda slug: REGIONS_BY_SLUG[slug])

INDUSTRY_STYLE = """
.industry-hero { padding-block: clamp(1.5rem, 5vw, 2.5rem) 1rem; max-width: 760px; }
.industry-hero h1 { max-width: 25ch; }
.industry-section { margin-block: 2rem; }
.region-table { width: 100%; min-width: 0; table-layout: fixed; border-collapse: collapse; margin-top: 0.85rem; font-variant-numeric: tabular-nums; }
.region-table th, .region-table td { padding: 0.5rem; border-bottom: 1px solid var(--muted); text-align: right; }
.region-table th:first-child, .region-table td:first-child { padding-left: 0; text-align: left; width: 40%; }
.region-table th { color: var(--muted-fg); font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em; }
.region-table td.gap { color: var(--muted-fg); font-style: italic; }
.industry-source { margin: 0.75rem 0 0; font-size: 0.8125rem; overflow-wrap: anywhere; }
.industry-source a { color: inherit; }
@media (max-width: 640px) {
  .region-table th, .region-table td { padding-inline: 0.3rem; font-size: 0.8125rem; }
  .region-table th:first-child, .region-table td:first-child { width: 34%; }
  .region-table th { letter-spacing: 0; font-size: 0.625rem; }
  .region-table .badge { white-space: normal; }
}
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
    rendered = " ".join(reversed(groups)) or "0"
    return f"{sign}{rendered}{',' if dot else ''}{fraction}"


def region_row(slug: str, name_ru: str, series: dict | None) -> str:
    if series is None:
        return f'<tr><td>{html.escape(name_ru)}</td><td class="gap" colspan="3">нет ряда</td></tr>'
    observations = series.get("obs") or []
    if not observations:
        return f'<tr><td>{html.escape(name_ru)}</td><td class="gap" colspan="3">нет наблюдений</td></tr>'
    latest = observations[-1]
    stale = bool(series.get("stale"))
    badge = freshness_badge(str(latest.get("date", "")), "A", stale)
    return (
        f"<tr><td>{html.escape(name_ru)}</td>"
        f"<td>{exact_value(latest.get('value', ''))}</td>"
        f"<td>{html.escape(str(latest.get('date', '')))}</td>"
        f"<td>{badge}</td></tr>"
    )


def indicator_section(
    spec: dict, by_id: dict[str, dict], prefix: str = "kz.industry"
) -> str:
    ids = {slug: f"{prefix}.{spec['series_key']}.{slug}" for slug in REGION_ORDER}
    rows = "\n".join(
        region_row(slug, REGIONS_BY_SLUG[slug], by_id.get(ids[slug]))
        for slug in REGION_ORDER
    )
    sample = next(
        (by_id[ids[slug]] for slug in REGION_ORDER if ids[slug] in by_id), None
    )
    source = str((sample or {}).get("source") or "Бюро национальной статистики")
    source_url = str((sample or {}).get("source_url", ""))
    source_link = (
        f'<a href="{html.escape(source_url, quote=True)}">{html.escape(source_url)}</a>'
        if source_url
        else "адрес источника не передан"
    )
    return f'''    <section class="industry-section" aria-labelledby="{spec["series_key"]}-title">
      <h2 id="{spec["series_key"]}-title">{html.escape(spec["name_ru"])}</h2>
      <table class="region-table"><caption class="sr-only">{html.escape(spec["name_ru"])} по областям</caption>
        <thead><tr><th scope="col">Область</th><th scope="col">Значение</th><th scope="col">Год</th><th scope="col">Свежесть</th></tr></thead>
        <tbody>{rows}</tbody></table>
      <p class="industry-source">Единица: {html.escape(spec["unit"])}. Источник: {html.escape(source)}.<br>{source_link}</p>
    </section>'''


def build(data: dict) -> str:
    by_id = {item.get("series_id"): item for item in data.get("series", [])}
    sections = "\n".join(indicator_section(spec, by_id) for spec in INDUSTRY_SERIES)
    if not by_id:
        sections = no_data("отраслевые ряды БНС не собраны")
    generated = datetime.fromisoformat(data["generated_at"])
    return TEMPLATE.format(
        meta=meta_tags(
            "Отраслевые показатели Казахстана по областям: БНС",
            "Металлургия и водозабор по двадцати областям Казахстана из Бюро национальной статистики.",
            "/macroradar/industry/",
        ),
        style=STYLE
        + HEADER_STYLE
        + ACCESSIBILITY_STYLE
        + CTA_STYLE
        + NO_DATA_STYLE
        + INDUSTRY_STYLE,
        header=site_header("industry"),
        skip_link=skip_link(),
        generated=generated.strftime("%d.%m.%Y %H:%M UTC"),
        generated_iso=generated.isoformat(),
        issues=issues_notice(data.get("issues")),
        sections=sections,
        cta=cta_block(),
        footer=detail_footer(date.today().year),
    )


TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{meta}<title>Отраслевые показатели Казахстана по областям</title><style>{style}</style></head><body>
{skip_link}{header}<div class="wrap"><header class="industry-hero"><h1>Отраслевые показатели по областям</h1>
<p class="lede">Годовые ряды Бюро национальной статистики, только уровень области: районы и города
районного значения не включены. Металлургия читается как индекс к предыдущему году, не как объём производства.</p>
<p class="updated">Собрано <time datetime="{generated_iso}">{generated}</time></p></header>{issues}
<main id="main-content">{sections}{cta}</main>{footer}</div></body></html>"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build(json.loads(dataset.read_text(encoding="utf-8"))), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
