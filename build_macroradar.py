"""Страница-хаб Macro Radar: jbs.finance/macroradar/.

Хаб только направляет: герой, пять карточек на самостоятельные темы и короткая
памятка о том, как их читать. Сам анализ живёт на страницах тем, у каждой свой
build_*.py, свой canonical и свой h1.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from layout import HEADER_STYLE, meta_tags, site_header

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "out" / "macroradar.html"

HUB_STYLE = """
/* Пока хаб склеивался с темами, палитра приезжала из их стилей. Теперь темы живут
   отдельно, и без своего :root хаб уходит на прод бесцветным: переменные ниже
   используются его же карточками и шапкой. Значения те же, что у страниц тем. */
:root {
  --bg: #F5F0E8;
  --fg: #2C2420;
  --card: #FFFFFF;
  --muted: #E8DFD0;
  --muted-fg: #6E6256;
  --accent: #C0603D;
  --line: #9B8E82;
  --radius: 10px;
  --dur-in: 200ms;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 1120px; margin-inline: auto; padding-inline: clamp(1rem, 4vw, 2.5rem); }
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
.method { padding: clamp(1.25rem, 3vw, 2rem); margin-bottom: 3rem; background: #EDE4D5; border-left: 3px solid var(--accent); }
.method h2 { margin: 0 0 .5rem; font-family: Georgia, "Times New Roman", serif; font-size: 1.5rem; }
.method p { max-width: 70ch; margin: 0; color: var(--muted-fg); }
footer { padding-block: 1.5rem 2.5rem; border-top: 1px solid var(--muted); color: var(--muted-fg); font-size: .8125rem; } footer p { margin: 0; }
@media (max-width: 640px) { .radar-hero { padding-top: 2.25rem; } .radar-card { grid-column: 1 / -1; min-height: 225px; } }
"""

SECTIONS = (
    (
        "macro",
        "Макро",
        "Условия для бизнеса",
        "Ставка, инфляция, курс, доходы и деловая активность. Контекст для цен, зарплат и кредитов.",
    ),
    (
        "trade",
        "Торговля",
        "Связь с внешним рынком",
        "Экспорт, импорт, партнёры и товарные группы. Где меняется внешний спрос и зависимость от поставок.",
    ),
    (
        "national-fund",
        "Нацфонд",
        "Подушка государства",
        "Валютные активы, доходность и состав сберегательного портфеля Нацфонда.",
    ),
    (
        "budget",
        "Бюджет",
        "Факт против плана",
        "Поступления, исполнение плана и регионы. Как наполняется бюджет и где меняется налоговая база.",
    ),
    (
        "tax",
        "Ставки",
        "Норма на текущую дату",
        "Налоговые ставки, пороги и сроки. Справочник с датой сверки, чтобы начать расчёт с правильной базы.",
    ),
)


def page_jsonld() -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Macro Radar Казахстана",
        "description": "Открытые данные о макроэкономике, торговле, Нацфонде, бюджете и налогах Казахстана.",
        "url": "https://jbs.finance/macroradar/",
        "inLanguage": "ru-KZ",
        "isPartOf": {
            "@type": "WebSite",
            "name": "JB Solutions",
            "url": "https://jbs.finance",
        },
        "hasPart": [
            {
                "@type": "Dataset",
                "name": name,
                "url": f"https://jbs.finance/macroradar/{anchor}/",
            }
            for anchor, name, _, _ in SECTIONS
        ],
    }
    return (
        '<script type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )


def build() -> str:
    cards = "\n".join(
        f"""      <a class="radar-card radar-card--{"fund" if anchor == "national-fund" else anchor}" href="/macroradar/{anchor}/">
        <div><p class="card-kicker">{kicker}</p><h2>{name}</h2><p>{description}</p></div>
        <span class="card-link"><span>Перейти к анализу</span><span aria-hidden="true">→</span></span>
      </a>"""
        for anchor, name, kicker, description in SECTIONS
    )
    return TEMPLATE.format(
        meta=meta_tags(
            "Macro Radar Казахстана: экономика, торговля, Нацфонд, бюджет и налоги",
            "Открытые данные для решений в Казахстане: макроэкономика, внешняя торговля, Нацфонд, бюджет и налоговые ставки.",
            "/macroradar/",
        )
        + "\n"
        + page_jsonld(),
        header=site_header("hub"),
        style=HUB_STYLE + HEADER_STYLE,
        cards=cards,
        year=date.today().year,
    )


TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src 'self' https://jbs.finance; font-src 'self'; base-uri 'none'; form-action 'none'">
{meta}<title>Macro Radar Казахстана</title><style>{style}</style></head><body>
{header}<div class="wrap"><main>
<header id="overview" class="radar-hero"><p class="eyebrow">JB Solutions</p><h1>Macro Radar Казахстана</h1><p class="lede">Пять срезов экономики на одной странице: от макроусловий и торговли до Нацфонда, бюджета и налогов.</p></header>
<p class="reading-note">Выбери анализ плиткой или вкладкой выше. У каждого показателя указаны дата и первоисточник. Это ориентир для анализа, не персональная инвестиционная или налоговая рекомендация.</p>
<section class="radar-grid" aria-label="Анализы Macro Radar">
{cards}
</section>
<aside class="method" aria-labelledby="method-title"><h2 id="method-title">Как читать радар</h2><p>Мы не смешиваем норму, фактические поступления и макроиндикаторы в одну таблицу. Сначала выбери вопрос, затем проверь дату и источник конкретного показателя.</p></aside>
</main><footer><p>© {year} JB Solutions. Данные собираются из открытых источников.</p></footer></div></body></html>"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"Страница собрана: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
