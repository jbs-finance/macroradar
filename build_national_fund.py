"""Статическая страница jbs.finance/macroradar/national-fund/."""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from build_pulse import STYLE, fmt_num
from national_assets_block import BLOCK_STYLE, build_assets_blocks, build_assets_methodology
from sovereign_assets import load_disclosures
from layout import (
    ACCESSIBILITY_STYLE,
    CTA_STYLE,
    HEADER_STYLE,
    cta_block,
    detail_footer,
    meta_tags,
    site_header,
    skip_link,
)

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "national_fund.json"
DEFAULT_OUT = HERE / "out" / "national_fund.html"

FUND_STYLE = """
.fund-hero { padding-block: clamp(1.5rem, 4vw, 2.5rem) 1.25rem; max-width: 760px; }
.fund-hero h1 { max-width: 22ch; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.75rem, 4vw, 2.5rem); letter-spacing: -0.025em; line-height: 1.15; }
.fund-hero .lede { max-width: 58ch; font-size: 1.1rem; line-height: 1.55; }
.fund-summary { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 1px; margin-bottom: 3rem; background: var(--muted); border: 1px solid var(--muted); }
.story-heading { margin: 0 0 1rem; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.55rem, 3vw, 2.15rem); letter-spacing: -0.025em; }
.asset-map { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; margin: 0 0 3rem; background: var(--muted); border: 1px solid var(--muted); }
.asset-map a { min-width: 0; padding: clamp(1rem, 2.4vw, 1.4rem); color: inherit; text-decoration: none; background: var(--card); }
.asset-map a:hover, .asset-map a:focus-visible { background: #FAF4EA; }
.asset-map .owner { display: block; margin-bottom: 0.35rem; color: var(--muted-fg); font-size: 0.74rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
.asset-map strong { display: block; font-family: Georgia, "Times New Roman", serif; font-size: 1.25rem; }
.asset-map .map-value { display: block; margin: 0.65rem 0 0.2rem; font-size: 1.05rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.asset-map .map-note { display: block; color: var(--muted-fg); font-size: 0.84rem; line-height: 1.4; }
.fund-stat { padding: clamp(1rem, 2.4vw, 1.65rem); background: var(--card); }
.fund-stat .label { margin: 0 0 0.65rem; color: var(--muted-fg); font-size: 0.8rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; }
.fund-stat .number { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.65rem, 3.4vw, 2.8rem); letter-spacing: -0.035em; line-height: 1; }
.fund-stat .note { margin: 0.65rem 0 0; color: var(--muted-fg); font-size: 0.85rem; }
.fund-stat--main { background: #273C37; color: #F6F0E7; }
.fund-stat--main .label, .fund-stat--main .note { color: #D7DDD3; }
.trend-panel { padding: clamp(1.15rem, 3vw, 2rem); margin: 1.5rem 0 3rem; background: #EDE4D5; border-top: 3px solid #2F6B4F; }
.trend-panel > h2 { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.55rem, 3vw, 2.15rem); letter-spacing: -0.025em; }
.trend-panel > .section-note { margin: 0.5rem 0 1.25rem; }
.trend-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(310px, 0.75fr); gap: 1rem; }
.trend-card { min-width: 0; margin: 0; padding: 1rem; background: var(--card); border: 1px solid var(--muted); }
.trend-card figcaption { min-height: 3.2rem; margin-bottom: 0.75rem; }
.trend-card figcaption strong { display: block; margin-bottom: 0.2rem; }
.trend-card figcaption span { color: var(--muted-fg); font-size: 0.82rem; line-height: 1.35; }
.trend-card .spark { width: 100%; height: auto; min-height: 190px; color: #2F6B4F; overflow: visible; }
.trend-card .spark-line { stroke: currentColor; stroke-width: 2.5; fill: none; }
.trend-card .spark-area { fill: rgba(47, 107, 79, 0.13); }
.spark-anchor circle { fill: var(--card); stroke: #2F6B4F; stroke-width: 3; }
.spark-anchor text { fill: #25221F; font-size: 16px; font-weight: 700; paint-order: stroke; stroke: var(--card); stroke-width: 5px; stroke-linejoin: round; }
.spark-anchor .anchor-date { fill: var(--muted-fg); font-size: 13px; font-weight: 500; }
.spark-anchor:focus { outline: none; }
.spark-anchor:focus circle { stroke: #A8522F; stroke-width: 5; }
.return-plot { --zero: 52%; position: relative; display: grid; grid-template-columns: repeat(var(--return-count), minmax(0, 1fr)); gap: clamp(0.18rem, 0.8vw, 0.5rem); height: 178px; border-bottom: 1px solid var(--muted); }
.return-zero { position: absolute; z-index: 0; top: var(--zero); right: 0; left: 0; border-top: 1px solid var(--line); }
.return-column { position: relative; min-width: 0; height: 100%; }
.return-bar { position: absolute; z-index: 1; right: 18%; left: 18%; min-height: 2px; border-radius: 2px 2px 0 0; background: #2F6B4F; }
.return-bar--positive { bottom: calc(100% - var(--zero)); height: var(--bar-height); }
.return-bar--negative { top: var(--zero); height: var(--bar-height); border-radius: 0 0 2px 2px; background: #A8522F; }
.return-year { position: absolute; right: 0; bottom: 0; left: 0; color: var(--muted-fg); font-size: clamp(0.58rem, 1.2vw, 0.7rem); text-align: center; }
.return-value { position: absolute; right: -0.35rem; left: -0.35rem; color: #25221F; font-size: clamp(0.58rem, 1vw, 0.7rem); font-weight: 700; text-align: center; font-variant-numeric: tabular-nums; }
.return-bar--positive + .return-value { bottom: calc(100% - var(--zero) + var(--bar-height) + 0.2rem); }
.return-bar--negative + .return-value { top: calc(var(--zero) + var(--bar-height) + 0.2rem); }
.availability .details-body { max-width: 100%; overflow-x: auto; }
.availability details:not([open]) > .details-body { display: none; }
.availability { display: grid; grid-template-columns: 0.8fr 1.2fr; gap: clamp(1rem, 3vw, 2rem); align-items: start; padding: clamp(1.25rem, 3vw, 2rem); margin: 3rem 0; border: 1px solid var(--muted); }
.availability h2 { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: 1.8rem; line-height: 1.05; }
.availability dl { margin: 0; display: grid; gap: 1rem; }
.availability dt { font-weight: 700; }
.availability dd { margin: 0.2rem 0 0; color: var(--muted-fg); line-height: 1.45; }
.year-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.year-table th, .year-table td { padding: 0.7rem 0.5rem; border-bottom: 1px solid var(--muted); text-align: right; }
.year-table th:first-child, .year-table td:first-child { padding-left: 0; text-align: left; }
.year-table th { color: var(--muted-fg); font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
.year-table .negative { color: #A8522F; } .year-table .positive { color: #2F6B4F; }
.portfolio { margin: 3rem 0; padding: clamp(1.15rem, 3vw, 2rem); background: var(--card); border: 1px solid var(--muted); }
.portfolio h2 { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.55rem, 3vw, 2.15rem); letter-spacing: -0.025em; }
.portfolio-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; margin-top: 1.25rem; }
.portfolio-item { display: grid; grid-template-columns: 1fr auto; gap: 0.35rem 0.75rem; padding: 0.75rem 0; border-bottom: 1px solid var(--muted); }
.portfolio-item .share { font-family: Georgia, "Times New Roman", serif; font-size: 1.35rem; }
.portfolio-item .amount { color: var(--muted-fg); font-size: 0.82rem; }
@media (max-width: 640px) { .portfolio-grid { grid-template-columns: 1fr; } }
@media (max-width: 820px) { .trend-grid { grid-template-columns: 1fr; } .trend-card figcaption { min-height: 0; } }
@media (max-width: 820px) { .asset-map { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .fund-summary, .availability { grid-template-columns: 1fr; } .trend-panel { margin-inline: -0.35rem; } .trend-card { padding-inline: 0.75rem; } .return-value { font-size: 0.56rem; } }
"""

MONTHS_RU = (
    "",
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)

MONTHS_RU_GENITIVE = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

def annual_assets(points: list[dict]) -> list[dict]:
    """Последняя месячная точка каждого года, без искусственной агрегации."""
    by_year = {}
    for point in points:
        by_year[point["date"][:4]] = point
    return list(by_year.values())


def change(points: list[dict], months: int) -> float | None:
    if len(points) <= months:
        return None
    base = points[-1 - months]["value"]
    return (points[-1]["value"] / base - 1) * 100 if base else None


def signed(value: float | None) -> str:
    if value is None:
        return "нет сопоставимой базы"
    return f"{'+' if value > 0 else ''}{fmt_num(value, 1)}%"


def count_text(value: int, forms: tuple[str, str, str]) -> str:
    """Русское склонение небольших счётчиков на публичной странице."""
    tail = value % 100
    if 11 <= tail <= 14:
        form = forms[2]
    elif value % 10 == 1:
        form = forms[0]
    elif 2 <= value % 10 <= 4:
        form = forms[1]
    else:
        form = forms[2]
    return f"{value} {form}"


def table_rows(assets: list[dict], returns: list[dict]) -> str:
    returns_by_year = {point["date"]: point["value"] for point in returns}
    rows = []
    for point in reversed(annual_assets(assets)):
        year, month = point["date"].split("-")
        yearly_return = returns_by_year.get(year)
        tone = "positive" if (yearly_return or 0) > 0 else "negative" if yearly_return is not None else ""
        rendered_return = "нет данных" if yearly_return is None else signed(yearly_return)
        period = year if month == "12" else month_label(point["date"])
        rows.append(
            f"<tr><td>{html.escape(period)}</td>"
            f"<td>${fmt_num(point['value'], 2)}</td>"
            f"<td class=\"{tone}\">{rendered_return}</td></tr>"
        )
    return "\n".join(rows)


def month_label(value: str) -> str:
    year, month = value.split("-")
    return f"{MONTHS_RU[int(month)]} {year}"


def full_date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{int(day)} {MONTHS_RU_GENITIVE[int(month)]} {year}"


def month_in_label(value: str) -> str:
    year, month = value.split("-")
    forms = (
        "", "январе", "феврале", "марте", "апреле", "мае", "июне",
        "июле", "августе", "сентябре", "октябре", "ноябре", "декабре",
    )
    return f"{forms[int(month)]} {year} года"


def generated_label(value: str) -> str:
    stamp = datetime.fromisoformat(value)
    return f"{stamp.day} {MONTHS_RU_GENITIVE[stamp.month]} {stamp.year}, {stamp:%H:%M} UTC"


def asset_chart(points: list[dict], width: int = 900, height: int = 230) -> str:
    """Линия активов с тремя подписанными опорными точками."""
    values = [float(point["value"]) for point in points]
    if len(values) < 2:
        return '<p class="section-note">Данных для графика пока недостаточно.</p>'
    left, right, top, bottom = 34, 866, 30, 196
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    step = (right - left) / (len(values) - 1)

    def coordinates(index: int) -> tuple[float, float]:
        x = left + index * step
        y = top + (hi - values[index]) / span * (bottom - top)
        return x, y

    coords = [coordinates(index) for index in range(len(points))]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{left},{bottom} {poly} {right},{bottom}"
    anchors = []
    selected = []
    for index in (0, values.index(lo), len(points) - 1):
        if index not in selected:
            selected.append(index)
    for order, index in enumerate(selected):
        point = points[index]
        x, y = coords[index]
        text_anchor = "start" if order == 0 else "end" if index == len(points) - 1 else "middle"
        label_x = x + (5 if text_anchor == "start" else -5 if text_anchor == "end" else 0)
        label_y = max(20, y - 16)
        spoken = f"{month_label(point['date'])}: {fmt_num(point['value'], 2)} миллиарда долларов"
        anchors.append(
            f'<g class="spark-anchor" tabindex="0" role="img" aria-label="{html.escape(spoken)}">'
            f'<title>{html.escape(spoken)}</title><circle cx="{x:.1f}" cy="{y:.1f}" r="5"/>'
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{text_anchor}">${fmt_num(point["value"], 2)}</text>'
            f'<text class="anchor-date" x="{label_x:.1f}" y="{label_y + 18:.1f}" text-anchor="{text_anchor}">{html.escape(month_label(point["date"]))}</text>'
            "</g>"
        )
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="group" '
        'aria-label="Динамика валютных активов Национального фонда">'
        f'<polygon class="spark-area" points="{area}"/><polyline class="spark-line" points="{poly}"/>'
        + "".join(anchors)
        + "</svg>"
    )


def return_bars(points: list[dict]) -> str:
    """Отдельная шкала годовой доходности без смешения с активами в USD."""
    maximum = max((abs(float(point["value"])) for point in points), default=1) or 1
    rendered = []
    for point in points:
        value = float(point["value"])
        height = abs(value) / maximum * 40
        tone = "positive" if value >= 0 else "negative"
        spoken = f"{'плюс ' if value > 0 else 'минус ' if value < 0 else ''}{fmt_num(abs(value), 1)} процента"
        rendered.append(
            f'<span class="return-column" tabindex="0" role="img" aria-label="{html.escape(point["date"])} год: {spoken}" title="{signed(value)}">'
            f'<span class="return-bar return-bar--{tone}" style="--bar-height:{height:.4f}%" aria-hidden="true"></span>'
            f'<span class="return-value" style="--bar-height:{height:.4f}%" aria-hidden="true">{signed(value)}</span>'
            f'<span class="return-year" aria-hidden="true">{html.escape(point["date"])}</span></span>'
        )
    return "".join(rendered)


def build(data: dict) -> str:
    assets = data["assets"]
    returns = data["returns"]
    latest_assets = assets[-1]
    latest_return = returns[-1]
    disclosures = data.get("official_disclosures") or load_disclosures()
    fund_disclosure = disclosures["national_fund"]
    children_disclosure = disclosures["children"]
    reserves_disclosure = disclosures["nbk_reserves"]
    enpf_disclosure = disclosures["enpf"]["nbk_managed"]
    domestic_rate = disclosures["fx_rates"][fund_disclosure["domestic_monthly"]["as_of"]]
    enpf_rate = disclosures["fx_rates"][enpf_disclosure["as_of"]]
    annual_rate = disclosures["fx_rates"][fund_disclosure["annual_2025"]["as_of"]]
    issues = data.get("issues") or []
    issue_block = ""
    if issues:
        issue_block = '<div class="notice" role="status"><p><strong>Часть данных не обновилась.</strong> Показан сохранённый срез.</p><ul>' + "".join(f"<li>{html.escape(item)}</li>" for item in issues) + "</ul></div>"
    return TEMPLATE.format(
        meta=meta_tags(
            "Нацфонд, резервы НБК и пенсионные средства",
            "Три самостоятельных пула: государственный Нацфонд, международные резервы НБК и пенсионные средства вкладчиков ЕНПФ.",
            "/macroradar/national-fund/",
        ),
        header=site_header("fund"),
        style=STYLE + HEADER_STYLE + ACCESSIBILITY_STYLE + CTA_STYLE + FUND_STYLE + BLOCK_STYLE,
        generated=generated_label(data["generated_at"]),
        asset_value=fmt_num(latest_assets["value"], 2),
        asset_date=month_label(latest_assets["date"]),
        annual_change=signed(change(assets, 12)),
        return_value=signed(latest_return["value"]),
        return_date=html.escape(latest_return["date"]),
        spark=asset_chart(assets),
        last_period=month_label(assets[-1]["date"]),
        return_bars=return_bars(returns),
        return_count_css=len(returns),
        asset_count=count_text(len(assets), ("точка", "точки", "точек")),
        asset_start=month_in_label(assets[0]["date"]),
        return_count=count_text(len(returns), ("наблюдение", "наблюдения", "наблюдений")),
        return_start=html.escape(returns[0]["date"]),
        return_end=html.escape(returns[-1]["date"]),
        rows=table_rows(assets, returns),
        assets_blocks=build_assets_blocks(data.get("official_disclosures") or load_disclosures()),
        assets_methodology=build_assets_methodology(data.get("official_disclosures") or load_disclosures()),
        asset_source=html.escape(data["assets_source"], quote=True),
        return_source=html.escape(data["returns_source"], quote=True),
        issue_block=issue_block,
        map_fund_value=fmt_num(latest_assets["value"], 2),
        map_fund_date=month_label(latest_assets["date"]),
        map_reserves_value=fmt_num(reserves_disclosure["gross"] / 1000, 2),
        map_reserves_date=full_date(reserves_disclosure["as_of"]),
        map_enpf_value=fmt_num(enpf_disclosure["total"] / enpf_rate["kzt_per_usd"], 2),
        map_enpf_date=full_date(enpf_disclosure["as_of"]),
        cta=cta_block(),
        skip_link=skip_link(),
        footer=detail_footer(date.today().year),
        annual_source=html.escape(fund_disclosure["annual_2025"]["source"], quote=True),
        domestic_source=html.escape(fund_disclosure["domestic_monthly"]["source"], quote=True),
        child_source=html.escape(children_disclosure["sources"][0], quote=True),
        child_participant_api=html.escape(children_disclosure["sources"][1], quote=True),
        child_recipient_api=html.escape(children_disclosure["sources"][2], quote=True),
        child_method_source=html.escape(children_disclosure["sources"][3], quote=True),
        reserves_source=html.escape(reserves_disclosure["source"], quote=True),
        enpf_source=html.escape(enpf_disclosure["source"], quote=True),
        annual_rate=fmt_num(annual_rate["kzt_per_usd"], 2),
        domestic_rate=fmt_num(domestic_rate["kzt_per_usd"], 2),
        domestic_rate_source=html.escape(domestic_rate["source"], quote=True),
        enpf_rate=fmt_num(enpf_rate["kzt_per_usd"], 2),
        enpf_rate_source=html.escape(enpf_rate["source"], quote=True),
        kzt_rows=currency_provenance_rows(disclosures),
        year=date.today().year,
    )


def currency_provenance_rows(disclosures: dict) -> str:
    domestic = disclosures["national_fund"]["domestic_monthly"]
    enpf = disclosures["enpf"]
    main = enpf["nbk_managed"]
    rows = [
        ("Нацфонд: долговые инструменты, номинал", domestic["as_of"], domestic["debt_nominal"]),
        ("Нацфонд: долговые инструменты, справедливая стоимость", domestic["as_of"], domestic["debt_fair_value"]),
        ("Нацфонд: долевые инструменты, стоимость приобретения", domestic["as_of"], domestic["equity_cost"]),
        ("Нацфонд: долевые инструменты, справедливая стоимость", domestic["as_of"], domestic["equity_fair_value"]),
        ("Нацфонд: остаток денег", domestic["as_of"], domestic["cash"]),
        ("ЕНПФ: основной портфель под управлением НБК", main["as_of"], main["total"]),
        ("ЕНПФ: ОПВР со взносным счётом", enpf["opvr"]["as_of"], enpf["opvr"]["including_contribution_account"]),
        ("ЕНПФ: частные управляющие", enpf["private_managers"]["as_of"], enpf["private_managers"]["value"]),
    ]
    return "".join(
        f"<tr><td>{html.escape(label)}</td><td>{full_date(as_of)}</td><td>{fmt_num(value, 4)} млрд KZT</td></tr>"
        for label, as_of, value in rows
    )


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}
<title>Нацфонд, резервы НБК и пенсионные средства</title>
<style>{style}</style>
</head>
<body>
{skip_link}
{header}
<div class="wrap">
  <header class="fund-hero">
    <h1>Нацфонд, резервы НБК и пенсионные средства</h1>
    <p class="lede">Это три разные суммы с разными владельцами и задачами. Нацфонд принадлежит государству. Международными резервами управляет Национальный банк. Пенсионные средства принадлежат вкладчикам ЕНПФ.</p>
    <p class="updated">Собрано {generated}</p>
  </header>
{issue_block}
  <main id="main-content">
    <section aria-labelledby="map-title">
      <h2 class="story-heading" id="map-title">Три пула, три задачи</h2>
      <p class="section-note">Общей суммы здесь нет. Каждый блок отвечает на свой вопрос.</p>
      <div class="asset-map">
        <a href="#national-fund"><span class="owner">Государственные средства · управление НБК</span><strong>Национальный фонд</strong><span class="map-value">${map_fund_value} млрд</span><span class="map-note">Валютные активы за {map_fund_date}. Фонд сберегает нефтяные доходы и поддерживает бюджет.</span></a>
        <a href="#reserves"><span class="owner">Национальный банк Казахстана</span><strong>Международные резервы</strong><span class="map-value">${map_reserves_value} млрд</span><span class="map-note">Валовой предварительный остаток на {map_reserves_date}. Резерв для внешней устойчивости.</span></a>
        <a href="#enpf"><span class="owner">Личные пенсионные средства вкладчиков</span><strong>Пенсионные средства ЕНПФ</strong><span class="map-value">${map_enpf_value} млрд</span><span class="map-note">Основной портфель на {map_enpf_date}. Эти деньги предназначены для пенсионных выплат.</span></a>
      </div>
    </section>

    <section id="national-fund" aria-labelledby="national-fund-title">
    <h2 class="story-heading" id="national-fund-title">Национальный фонд</h2>
    <p class="section-note">Государственный фонд получает нефтяные доходы, сохраняет часть средств и перечисляет трансферты в бюджет. Программа «Нацфонд — детям» работает внутри этого фонда.</p>
    <section class="fund-summary" aria-label="Ключевые показатели Национального фонда">
      <article class="fund-stat fund-stat--main"><p class="label">Валютные активы</p><p class="number">${asset_value}</p><p class="note">млрд за {asset_date}</p></article>
      <article class="fund-stat"><p class="label">Изменение за 12 месяцев</p><p class="number">{annual_change}</p><p class="note">по ежемесячному ряду валютных активов</p></article>
      <article class="fund-stat"><p class="label">Доходность</p><p class="number">{return_value}</p><p class="note">за {return_date} год, не доход бюджета</p></article>
    </section>

    <section class="trend-panel" aria-labelledby="assets-title">
      <h2 id="assets-title">Динамика Национального фонда</h2>
      <p class="section-note">Активы и доходность измеряются по разным шкалам. Поэтому они показаны рядом, но не объединены в одну линию.</p>
      <div class="trend-grid">
        <figure class="trend-card"><figcaption><strong>Валютные активы, $ млрд</strong><span>Месячный ряд НБРК. Подписаны начало, минимум и последняя точка за {last_period}.</span></figcaption>{spark}</figure>
        <figure class="trend-card"><figcaption><strong>Годовая доходность, %</strong><span>Отдельный официальный ряд. Доходность за 2026 год ещё не опубликована.</span></figcaption><div class="return-plot" style="--return-count:{return_count_css}" aria-label="Годовая доходность активов Национального фонда">{return_bars}<span class="return-zero" aria-hidden="true"></span></div></figure>
      </div>
    </section>
    </section>

    {assets_blocks}

    <section class="availability" aria-labelledby="availability-title">
      <h2 id="availability-title">Источники и методология</h2>
      <div><p class="section-note">Здесь собраны официальные ссылки, полнота рядов и применённые правила расчёта.</p><dl>
        <div><dt>Валютные активы</dt><dd>НБРК публикует месячный JSON. В радаре {asset_count}. Ряд начинается в {asset_start}.</dd></div>
        <div><dt>Доходность</dt><dd>НБРК обновляет годовую таблицу. В радаре {return_count}: с {return_start} по {return_end} год.</dd></div>
        <div><dt>Операции и трансферты</dt><dd>Свежие операции выходят ежемесячно. Единого машиночитаемого ряда за десять лет нет, поэтому архивные таблицы пока не объединены.</dd></div>
      </dl><details><summary>Как рассчитаны показатели</summary><div class="details-body"><ul>
        <li>Месячная линия активов построена по исходному JSON НБРК без интерполяции.</li>
        <li>На графике подписаны начало ряда, минимальная точка и последняя публикация. Последняя точка 2026 года относится к сентябрю.</li>
        <li>Годовая доходность взята из отдельного ряда НБРК. Она не рассчитана из изменения активов.</li>
        <li>Доли на диаграммах рассчитаны от официального валового итога соответствующего пула.</li>
        <li>Валютные активы показаны в долларах на конец периода. Годовые поступления в бюджет считаются отдельно.</li>
        <li>С 1 февраля 2024 года НБРК показывает валютные активы после учёта обязательств по целевым требованиям программы «Нацфонд — детям». Для сравнения с ранними периодами нужна эта оговорка.</li>
        <li>Доходность относится к управлению валютными активами. Поступления от нефтяного сектора и трансферты в бюджет в неё не входят.</li>
        <li>Нацфонд, резервы НБК и пенсионные активы относятся к разным владельцам и задачам. Общая сумма для них не рассчитывается.</li>
      </ul></div></details><details><summary>Точные ряды, сверка итогов и оценки</summary><div class="details-body"><p>Здесь находятся точные годовые значения, бухгалтерская сверка и пояснение к разным оценкам портфелей.</p><table class="year-table"><thead><tr><th>Период</th><th>Активы, $ млрд</th><th>Доходность</th></tr></thead><tbody>{rows}</tbody></table>{assets_methodology}</div></details><details><summary>Исходные суммы в тенге и пересчёт</summary><div class="details-body"><p>Формула для тенговых строк: млрд KZT ÷ официальный курс KZT за $1 = $ млрд.</p><table class="data-table"><thead><tr><th>Показатель</th><th>Дата оценки</th><th>Исходное значение</th></tr></thead><tbody>{kzt_rows}</tbody></table><ul><li>Курс на 30 сентября 2026: <a href="{domestic_rate_source}">{domestic_rate} тенге за $1</a>.</li><li>Курс на 1 октября 2026: <a href="{enpf_rate_source}">{enpf_rate} тенге за $1</a>.</li><li>Годовой отчёт на 31 декабря 2025 использует курс {annual_rate} тенге за $1. Долларовые эквиваленты взяты прямо из отчёта.</li></ul></div></details><h3>Официальные источники</h3><ul class="source-list">
        <li><a href="{asset_source}">НБРК: валютные активы Нацфонда и международные резервы</a></li>
        <li><a href="{return_source}">НБРК: доходность валютных активов Нацфонда</a></li>
        <li><a href="{annual_source}">НБРК: годовой отчёт Нацфонда за 2025 год</a></li>
        <li><a href="{domestic_source}">НБРК: операции Нацфонда за сентябрь 2026 года</a></li>
        <li><a href="{child_source}">ЕНПФ: официальная таблица программы «Нацфонд — детям»</a></li>
        <li><a href="{child_method_source}">НБРК: правила программы «Национальный фонд — детям»</a></li>
        <li><a href="{enpf_source}">ЕНПФ: структура инвестиционного портфеля</a></li>
      </ul><details><summary>Машиночитаемые данные программы</summary><div class="details-body"><ul><li><a href="{child_participant_api}">ЕНПФ: участники и целевые требования</a></li><li><a href="{child_recipient_api}">ЕНПФ: получатели и целевые накопления</a></li><li><a href="{reserves_source}">НБРК: таблица резервов</a></li></ul></div></details></div>
    </section>
{cta}
  </main>
  {footer}
</div>
</body>
</html>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else DATASET
    data = json.loads(dataset.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data), encoding="utf-8")
    print(f"Страница Нацфонда собрана: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
