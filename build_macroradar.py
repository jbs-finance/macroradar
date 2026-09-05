"""Единая статическая страница Macro Radar: jbs.finance/macroradar/."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

from build_budget import build as build_budget
from build_national_fund import build as build_national_fund
from build_radar import build as build_radar
from build_tax import build as build_tax
from build_trade import build as build_trade
from layout import HEADER_STYLE, meta_tags, site_header

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "out" / "macroradar.html"

HUB_STYLE = """
.radar-hero { padding-block: clamp(2.5rem, 8vw, 5.75rem) clamp(2rem, 5vw, 3.5rem); max-width: 900px; }
.eyebrow { display: inline-flex; align-items: center; gap: .55rem; margin: 0 0 1rem; color: var(--accent); font-size: .75rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.eyebrow::before { content: ""; width: 1.8rem; height: 2px; background: currentColor; }
.radar-hero h1 { max-width: 15ch; font-family: Georgia, "Times New Roman", serif; font-size: clamp(2.4rem, 6.5vw, 5.2rem); letter-spacing: -.045em; line-height: .98; margin-bottom: 1.25rem; }
.radar-hero .lede { max-width: 52ch; font-size: clamp(1.05rem, 1.6vw, 1.3rem); line-height: 1.55; }
.reading-note { max-width: 66ch; padding: 1rem 0; border-top: 1px solid var(--line); color: var(--muted-fg); font-size: .9rem; }
.radar-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 1rem; padding-bottom: clamp(3.5rem, 8vw, 6rem); }
.radar-card { grid-column: span 6; min-height: 240px; display: flex; flex-direction: column; justify-content: space-between; padding: clamp(1.25rem, 3vw, 2rem); background: var(--card); color: var(--fg); text-decoration: none; border: 1px solid var(--muted); border-top: 3px solid var(--card-tone, var(--accent)); border-radius: var(--radius); }
.radar-card:hover, .radar-card:focus-visible { transform: translateY(-4px); box-shadow: 0 14px 26px rgba(44, 36, 32, .11); outline: none; }
.radar-card--macro { --card-tone: #A8522F; } .radar-card--trade { --card-tone: #2F6B4F; } .radar-card--fund { --card-tone: #2F6B4F; } .radar-card--budget { --card-tone: #8A6A2C; } .radar-card--tax { --card-tone: #755C8C; }
.card-kicker { margin: 0; color: var(--card-tone); font-size: .75rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
.radar-card h2 { margin: .35rem 0 .65rem; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.6rem, 3vw, 2.3rem); letter-spacing: -.025em; line-height: 1.05; }
.radar-card p { max-width: 38ch; margin: 0; color: var(--muted-fg); font-size: .95rem; }
.card-link { display: flex; justify-content: space-between; align-items: center; margin-top: 1.75rem; padding-top: .85rem; border-top: 1px solid var(--muted); color: var(--fg); font-size: .875rem; font-weight: 650; }
.card-link span:last-child { color: var(--card-tone); font-size: 1.25rem; line-height: 1; }
.analysis-section { padding-block: clamp(3rem, 8vw, 6rem); border-top: 1px solid var(--muted); }
.tab-state { position: fixed; opacity: 0; pointer-events: none; }
.tab-panel { display: none; }
#view-hub:checked ~ main .panel-hub, #view-macro:checked ~ main .panel-macro, #view-trade:checked ~ main .panel-trade, #view-fund:checked ~ main .panel-national-fund, #view-budget:checked ~ main .panel-budget, #view-tax:checked ~ main .panel-tax { display: block !important; }
#view-hub:checked ~ .tabs label[for="view-hub"], #view-macro:checked ~ .tabs label[for="view-macro"], #view-trade:checked ~ .tabs label[for="view-trade"], #view-fund:checked ~ .tabs label[for="view-fund"], #view-budget:checked ~ .tabs label[for="view-budget"], #view-tax:checked ~ .tabs label[for="view-tax"] { color: var(--fg); border-bottom-color: var(--accent); }
.radar-card { cursor: pointer; }
.inline-tab-link { color: var(--accent); cursor: pointer; text-decoration: underline; }
.method { padding: clamp(1.25rem, 3vw, 2rem); margin-bottom: 3rem; background: #EDE4D5; border-left: 3px solid var(--accent); }
.method h2 { margin: 0 0 .5rem; font-family: Georgia, "Times New Roman", serif; font-size: 1.5rem; }
.method p { max-width: 70ch; margin: 0; color: var(--muted-fg); }
footer { padding-block: 1.5rem 2.5rem; border-top: 1px solid var(--muted); color: var(--muted-fg); font-size: .8125rem; } footer p { margin: 0; }
@media (max-width: 640px) { .radar-hero { padding-top: 2.25rem; } .radar-card { grid-column: 1 / -1; min-height: 225px; } }
"""

SECTIONS = (
    ("macro", "Макро", "Условия для бизнеса", "Ставка, инфляция, курс, доходы и деловая активность. Контекст для цен, зарплат и кредитов."),
    ("trade", "Торговля", "Связь с внешним рынком", "Экспорт, импорт, партнёры и товарные группы. Где меняется внешний спрос и зависимость от поставок."),
    ("national-fund", "Нацфонд", "Подушка государства", "Валютные активы, доходность и состав сберегательного портфеля Нацфонда."),
    ("budget", "Бюджет", "Факт против плана", "Поступления, исполнение плана и регионы. Как наполняется бюджет и где меняется налоговая база."),
    ("tax", "Ставки", "Норма на текущую дату", "Налоговые ставки, пороги и сроки. Справочник с датой сверки, чтобы начать расчёт с правильной базы."),
)


def page_jsonld() -> str:
    payload = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Macro Radar Казахстана", "description": "Открытые данные о макроэкономике, торговле, Нацфонде, бюджете и налогах Казахстана.", "url": "https://jbs.finance/macroradar/", "inLanguage": "ru-KZ", "isPartOf": {"@type": "WebSite", "name": "JB Solutions", "url": "https://jbs.finance"}, "hasPart": [{"@type": "Dataset", "name": name} for _, name, _, _ in SECTIONS]}
    return '<script type="application/ld+json">' + json.dumps(payload, ensure_ascii=False) + "</script>"


def page_style(document: str) -> str:
    match = re.search(r"<style>(.*?)</style>", document, re.DOTALL)
    if not match:
        raise ValueError("У анализа отсутствуют встроенные стили")
    return match.group(1)


def page_content(document: str) -> str:
    """Извлекает анализ без второй шапки, footer и повторяющегося CTA."""
    match = re.search(r'<div class="wrap">(.*)</div>\s*</body>', document, re.DOTALL)
    if not match:
        raise ValueError("У анализа отсутствует контейнер .wrap")
    content = re.sub(r"<footer>.*?</footer>", "", match.group(1), flags=re.DOTALL)
    content = re.sub(r'<section class="cta".*?</section>', "", content, flags=re.DOTALL)
    content = re.sub(
        r'<a href="/macroradar/(macro|trade|national-fund|budget|tax)/">(.*?)</a>',
        lambda match: f'<label class="inline-tab-link" for="view-{match.group(1)}">{match.group(2)}</label>',
        content,
    )
    return content.replace("<main>", "").replace("</main>", "")


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(radar: dict, pulse: dict, trade: dict, national_fund: dict, tax: dict, minfin: dict | None = None, budget: dict | None = None, oblast: dict | None = None) -> str:
    documents = (build_radar(radar, pulse, trade), build_trade(trade), build_national_fund(national_fund), build_budget(minfin, budget, oblast), build_tax(tax))
    sections = "\n".join(f'<section class="analysis-section tab-panel panel-{anchor}" aria-label="{name}">\n{page_content(document)}\n</section>' for (anchor, name, _, _), document in zip(SECTIONS, documents))
    cards = "\n".join(f'''      <label class="radar-card radar-card--{'fund' if anchor == 'national-fund' else anchor}" for="view-{'fund' if anchor == 'national-fund' else anchor}">
        <div><p class="card-kicker">{kicker}</p><h2>{name}</h2><p>{description}</p></div>
        <span class="card-link"><span>Перейти к анализу</span><span aria-hidden="true">↓</span></span>
      </label>''' for anchor, name, kicker, description in SECTIONS)
    return TEMPLATE.format(meta=meta_tags("Macro Radar Казахстана: экономика, торговля, Нацфонд, бюджет и налоги", "Открытые данные для решений в Казахстане: макроэкономика, внешняя торговля, Нацфонд, бюджет и налоговые ставки.", "/macroradar/") + "\n" + page_jsonld(), header=site_header("hub", tabs_as_controls=True), style=HUB_STYLE + HEADER_STYLE + "\n".join(page_style(document) for document in documents), cards=cards, sections=sections, year=date.today().year)


TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src 'self' https://jbs.finance; font-src 'self'; base-uri 'none'; form-action 'none'">
{meta}<title>Macro Radar Казахстана</title><style>{style}</style></head><body>
{header}<div class="wrap"><input class="tab-state" type="radio" name="radar-view" id="view-hub" checked><input class="tab-state" type="radio" name="radar-view" id="view-macro"><input class="tab-state" type="radio" name="radar-view" id="view-trade"><input class="tab-state" type="radio" name="radar-view" id="view-fund"><input class="tab-state" type="radio" name="radar-view" id="view-budget"><input class="tab-state" type="radio" name="radar-view" id="view-tax"><main>
<section class="tab-panel panel-hub">
<header id="overview" class="radar-hero"><p class="eyebrow">JB Solutions</p><h1>Macro Radar Казахстана</h1><p class="lede">Пять срезов экономики на одной странице: от макроусловий и торговли до Нацфонда, бюджета и налогов.</p></header>
<p class="reading-note">Выбери анализ плиткой или вкладкой выше. У каждого показателя указаны дата и первоисточник. Это ориентир для анализа, не персональная инвестиционная или налоговая рекомендация.</p>
<section class="radar-grid" aria-label="Анализы Macro Radar">
{cards}
</section>
{sections}
<aside class="method" aria-labelledby="method-title"><h2 id="method-title">Как читать радар</h2><p>Мы не смешиваем норму, фактические поступления и макроиндикаторы в одну таблицу. Сначала выбери вопрос, затем проверь дату и источник конкретного показателя.</p></aside></section>
</main><footer><p>© {year} JB Solutions. Данные собираются из открытых источников.</p></footer></div></body></html>"""


def main() -> None:
    if len(sys.argv) != 10:
        raise SystemExit("Использование: build_macroradar.py OUT RADAR PULSE TRADE FUND TAX MINFIN BUDGET OBLAST")
    out = Path(sys.argv[1])
    radar, pulse, trade, fund, tax, minfin, budget, oblast = (load_json(path) for path in sys.argv[2:])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(radar, pulse, trade, fund, tax, minfin, budget, oblast), encoding="utf-8")
    print(f"Страница собрана: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
