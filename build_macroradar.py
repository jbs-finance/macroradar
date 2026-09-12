"""Страница-хаб Macro Radar: jbs.finance/macroradar/.

Хаб только направляет: герой и пять карточек на самостоятельные темы. Методика
и источники живут на отдельной странице, доступной только из футера. Сам анализ
живёт на страницах тем, у каждой свой build_*.py, свой canonical и свой h1.
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
.radar-hero { padding-block: clamp(1.75rem, 4vw, 2.75rem) clamp(1.25rem, 3vw, 1.75rem); max-width: 900px; }
.eyebrow { display: inline-flex; align-items: center; gap: .55rem; margin: 0 0 1rem; color: var(--accent); font-size: .75rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.eyebrow::before { content: ""; width: 1.8rem; height: 2px; background: currentColor; }
.radar-hero h1 { max-width: 24ch; font-family: Georgia, "Times New Roman", serif; font-size: clamp(2rem, 4.2vw, 3rem); letter-spacing: -.03em; line-height: 1.06; margin-bottom: .75rem; }
.radar-hero .lede { max-width: 62ch; font-size: clamp(1rem, 1.2vw, 1.1rem); line-height: 1.5; }
.reading-note { max-width: 66ch; padding: 1rem 0; border-top: 1px solid var(--line); color: var(--muted-fg); font-size: .9rem; }
.radar-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: .875rem; padding-bottom: clamp(2rem, 4vw, 3rem); }
.radar-card { grid-column: span 4; min-height: 190px; display: flex; flex-direction: column; justify-content: space-between; padding: clamp(1.25rem, 3vw, 2rem); background: var(--card); color: var(--fg); text-decoration: none; border: 1px solid var(--muted); border-top: 3px solid var(--card-tone, var(--accent)); border-radius: var(--radius); transition: transform var(--dur-in) var(--ease-out), box-shadow var(--dur-in) var(--ease-out); }
.radar-card:hover, .radar-card:focus-visible { transform: translateY(-4px); box-shadow: 0 14px 26px rgba(44, 36, 32, .11); outline: none; }
.radar-card--macro { --card-tone: #A8522F; } .radar-card--trade { --card-tone: #2F6B4F; } .radar-card--fund { --card-tone: #2F6B4F; } .radar-card--budget { --card-tone: #8A6A2C; } .radar-card--tax { --card-tone: #755C8C; }
.card-kicker { margin: 0; color: var(--card-tone); font-size: .75rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
.radar-card h2 { margin: .3rem 0 .5rem; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.35rem, 2vw, 1.7rem); letter-spacing: -.02em; line-height: 1.1; }
.radar-card p { max-width: 38ch; margin: 0; color: var(--muted-fg); font-size: .95rem; }
.card-link { display: flex; justify-content: space-between; align-items: center; margin-top: 1.1rem; padding-top: .7rem; border-top: 1px solid var(--muted); color: var(--fg); font-size: .875rem; font-weight: 650; }
.card-link span:last-child { color: var(--card-tone); font-size: 1.25rem; line-height: 1; }
footer { padding-block: 1.5rem 2.5rem; border-top: 1px solid var(--muted); color: var(--muted-fg); font-size: .8125rem; } footer p { margin: 0; } footer a { color: inherit; text-decoration: underline; text-underline-offset: .16em; transition: color var(--dur-in) var(--ease-out); } footer a:hover, footer a:focus-visible { color: var(--fg); }
@media (max-width: 1000px) { .radar-card { grid-column: span 6; } }
@media (max-width: 640px) { .radar-hero { padding-top: 1.5rem; } .radar-card { grid-column: 1 / -1; min-height: 170px; } }
@media (prefers-reduced-motion: reduce) { .radar-card, footer a { transition: none; } .radar-card:hover, .radar-card:focus-visible { transform: none; } }
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
<header id="overview" class="radar-hero"><p class="eyebrow">JB Solutions</p><h1>Macro Radar Казахстана</h1><p class="lede">Пять срезов экономики Казахстана: макроусловия, внешняя торговля, Нацфонд, бюджет и налоговые ставки. У каждого своя страница с датой сверки и первоисточником.</p></header>
<p class="reading-note">Выбери срез карточкой ниже или ссылкой в шапке. У каждого показателя указаны дата и первоисточник. Это ориентир для анализа, персональной инвестиционной или налоговой рекомендацией он не является.</p>
<section class="radar-grid" aria-label="Анализы Macro Radar">
{cards}
</section>
</main><footer><p>© {year} JB Solutions. Данные собираются из открытых источников. <a href="/macroradar/methodology/">Методика и источники</a></p></footer></div></body></html>"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"Страница собрана: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
