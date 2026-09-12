"""Общая оболочка сайта для страниц радара: шапка, вкладки, мета-теги.

Страницы собираются вне роутера Next и обязаны выглядеть частью jbs.finance, а не
чужим виджетом. Здесь повторены только цвета и ритм шапки сайта, значения взяты из
app/globals.css и components/layout/Header.tsx репозитория website.
"""

from __future__ import annotations

import html
import json
from calendar import monthrange
from datetime import date

SITE = "https://jbs.finance"

TABS = [
    ("hub", "Обзор", "/macroradar/"),
    ("macro", "Макро", "/macroradar/macro/"),
    ("trade", "Торговля", "/macroradar/trade/"),
    ("fund", "Нацфонд", "/macroradar/national-fund/"),
    ("budget", "Бюджет", "/macroradar/budget/"),
    ("tax", "Ставки", "/macroradar/tax/"),
]

HEADER_STYLE = """
.site-bar { background: #1C1C2E; color: #F5F0E8; }
.site-bar .inner { max-width: 1120px; margin-inline: auto; padding-inline: clamp(1rem, 4vw, 2.5rem);
  display: flex; align-items: center; justify-content: space-between; height: 56px; gap: 1rem; }
.site-brand { display: inline-flex; align-items: center; gap: 0.6rem; color: inherit; text-decoration: none;
  font-weight: 600; font-size: 0.9375rem; }
.site-brand .mark { width: 28px; height: 28px; background: #A8522F; border-radius: 3px; display: inline-flex;
  align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700; color: #fff; }
.site-links { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.5rem 1.1rem; font-size: 0.875rem; }
.site-links a { color: rgba(245,240,232,0.8); text-decoration: none; transition: color var(--dur-in) var(--ease-out); }
.site-links a:hover, .site-links a:focus-visible { color: #fff; }
.tabs { position: sticky; top: 0; z-index: 20; background: var(--bg); border-bottom: 1px solid var(--muted);
  transition: box-shadow var(--dur-in) var(--ease-out); }
.tabs .inner { max-width: 1120px; margin-inline: auto; padding-inline: clamp(1rem, 4vw, 2.5rem);
  display: flex; gap: 0.1rem; overflow-x: auto; scrollbar-width: thin; }
.tabs a, .tabs label { display: inline-block; padding: 0.8rem 0.75rem; color: var(--muted-fg); text-decoration: none;
  font-size: 0.9375rem; font-weight: 500; border-bottom: 2px solid transparent; white-space: nowrap;
  transition: color var(--dur-in) var(--ease-out), border-color var(--dur-in) var(--ease-out); }
.tabs a[aria-current="page"], .tabs label:hover { color: var(--fg); border-bottom-color: var(--accent); }
.tabs a:hover, .tabs a:focus-visible, .tabs label:focus-visible { color: var(--fg); }
.tabs .title { margin-inline-end: auto; padding: 0.8rem 0.75rem 0.8rem 0; font-weight: 600; color: var(--fg); font-size: 0.9375rem; white-space: nowrap; }
[id] { scroll-margin-top: 64px; }
@media (max-width: 640px) {
  .site-bar .inner { height: auto; min-height: 52px; padding-block: 0.65rem; align-items: flex-start; }
  .site-brand { flex: 0 0 auto; }
  .site-links { justify-content: flex-end; gap: 0.35rem 0.7rem; font-size: 0.75rem; }
  .tabs .inner { justify-content: flex-start; padding-inline: 0.65rem; overflow-x: auto; }
  .tabs .title { display: none; }
  .tabs a, .tabs label { padding-inline: 0.25rem; font-size: 0.75rem; }
}
@media print { .site-bar, .tabs { display: none; } }
"""


ACCESSIBILITY_STYLE = """
.skip-link { position: fixed; z-index: 100; inset: 0 auto auto 50%; transform: translate(-50%, -160%);
  padding: 0.65rem 1rem; background: #1C1C2E; color: #fff; border-radius: 0 0 6px 6px;
  font-weight: 600; text-decoration: none; transition: transform var(--dur-in) var(--ease-out); }
.skip-link:focus-visible { transform: translate(-50%, 0); outline: 3px solid #A8522F; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { .skip-link { transition: none; } }
"""


def skip_link() -> str:
    """Ссылка для клавиатуры, ведущая сразу к содержимому страницы."""
    return '<a class="skip-link" href="#main-content">Перейти к содержанию</a>'


def detail_footer(year: int) -> str:
    """Общий футер тематических страниц с доступной, но не навигационной методикой."""
    return f"""<footer>
    <p>Данные собираются из открытых источников и приводятся без гарантии пригодности
      для конкретного решения. Для расчётов и отчётности сверяйтесь с первоисточником.</p>
    <p><a href="/macroradar/methodology/">Методика и источники</a></p>
    <p>&copy; {year} JB Solutions</p>
  </footer>"""


def site_header(active: str) -> str:
    """Тёмная полоса сайта плюс липкие вкладки радара."""
    tabs = "\n".join(
        f'      <a href="{href}">{label}</a>'
        if key != active
        else f'      <a href="{href}" aria-current="page">{label}</a>'
        for key, label, href in TABS
    )
    return f"""<div class="site-bar">
  <div class="inner">
    <a class="site-brand" href="{SITE}/ru"><span class="mark">JB</span>JB Solutions</a>
    <nav class="site-links" aria-label="Сайт">
      <a href="{SITE}/ru/services">Услуги</a>
      <a href="{SITE}/ru/resources">Полезные сервисы</a>
      <a href="{SITE}/ru/contacts">Контакты</a>
    </nav>
  </div>
</div>
<nav class="tabs" aria-label="Разделы радара">
  <div class="inner">
    <span class="title">Радар экономики Казахстана</span>
{tabs}
  </div>
</nav>"""


def meta_tags(
    title: str, description: str, path: str, image: str = "/og-image.png"
) -> str:
    """Публичная страница: canonical, Open Graph, без noindex."""
    t = html.escape(title, quote=True)
    d = html.escape(description, quote=True)
    url = f"{SITE}{path}"
    return f"""<meta name="description" content="{d}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="JB Solutions">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}{image}">
<meta property="og:locale" content="ru_KZ">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{SITE}/favicon.ico">"""


def cta_block() -> str:
    """Радар это витрина: такой же собирается под отрасль или компанию клиента."""
    return f"""    <section class="cta" aria-labelledby="cta-title">
      <h2 id="cta-title">Радар под ваш рынок или компанию</h2>
      <p>Код этого радара открыт, поднять такой же можно самостоятельно по
        инструкции в репозитории. Настройку под источники клиента и радар под
        другую отрасль или рынок делает JB Solutions.</p>
      <a class="cta-link" href="{SITE}/ai/macroradar/">Все способы получить радар</a>
    </section>"""


CTA_STYLE = """
.cta { background: var(--card); border: 1px solid var(--muted); border-left: 3px solid var(--accent);
  border-radius: var(--radius); padding: 1.25rem 1.4rem; margin-block: 2.5rem 1rem; }
.cta h2 { margin: 0 0 0.5rem; font-size: 1.125rem; }
.cta p { margin: 0 0 0.9rem; max-width: 70ch; color: var(--muted-fg); }
.cta-link { display: inline-block; background: var(--accent); color: #fff; text-decoration: none;
  padding: 0.6rem 1rem; border-radius: 6px; font-weight: 500; font-size: 0.9375rem;
  transition: transform var(--dur-in) var(--ease-out), opacity var(--dur-in) var(--ease-out); }
.cta-link:hover, .cta-link:focus-visible { opacity: 0.92; transform: translateY(-1px); }
@media (prefers-reduced-motion: reduce) { .cta-link:hover { transform: none; } }
"""


def dataset_jsonld(
    updated_iso: str,
    sources: list[str],
    name: str = "Радар экономики Казахстана",
    description: str = (
        "Ключевые макропоказатели Казахстана с ежедневным обновлением: "
        "базовая ставка, инфляция, курсы валют, рост ВВП, оплата труда, "
        "внешняя торговля."
    ),
    path: str = "/macroradar/",
) -> str:
    """Разметка набора данных: поисковику и языковой модели нужно понимать, что это
    регулярно обновляемые данные с названными источниками, а не статья."""
    names = ", ".join(sorted(set(sources)))
    return (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Dataset",
                "name": name,
                "description": description,
                "url": f"{SITE}{path}",
                "inLanguage": "ru",
                "isAccessibleForFree": True,
                "dateModified": updated_iso,
                "creator": {
                    "@type": "Organization",
                    "name": "JB Solutions",
                    "url": SITE,
                },
                "spatialCoverage": {"@type": "Place", "name": "Казахстан"},
                "sourceOrganization": [
                    {"@type": "Organization", "name": n} for n in names.split(", ") if n
                ],
            },
            ensure_ascii=False,
        )
        + "</script>"
    )


NO_DATA_STYLE = """
.no-data { background: var(--muted); border-radius: var(--radius); padding: 0.85rem 1.1rem;
  margin-block: 1rem; font-size: 0.875rem; color: var(--muted-fg); }
.no-data b { color: var(--fg); font-weight: 600; }
"""


def no_data(reason: str) -> str:
    """Заглушка вместо пустой секции.

    Заголовки и вводные абзацы стоят в шаблонах статически, поэтому пустая строка
    вместо блока оставляет заголовок висеть над пустотой: читается как сломанная
    вёрстка, а не как отсутствие данных. Пустоты быть не должно, должна быть
    названная причина.
    """
    return f'<p class="no-data"><b>Данные не собрались:</b> {html.escape(reason)}</p>'


ISSUES_INTRO = (
    "<strong>Часть данных не обновилась в последнем прогоне.</strong> "
    "Показаны предыдущие значения."
)


def issues_notice(issues: list[str] | None, intro: str = ISSUES_INTRO) -> str:
    """Список того, что не собралось. Разметка общая для всех страниц радара."""
    if not issues:
        return ""
    items = "".join(f"<li>{html.escape(i)}</li>" for i in issues)
    return f'<div class="notice" role="status"><p>{intro}</p><ul>{items}</ul></div>'


# Разумный лаг последней точки по частоте ряда, в днях. Дневной ряд, отставший на
# неделю, уже не актуален, а годовому отстать на год нормально: он так и выходит.
MAX_AGE_DAYS = {"D": 7, "M": 60, "Q": 150, "A": 500}
DEFAULT_MAX_AGE_DAYS = 60

FRESH_BADGE = '<span class="badge badge-fresh">актуально</span>'
STALE_BADGE = '<span class="badge badge-stale">данные устарели</span>'


def parse_point_date(raw: str | None) -> date | None:
    """Дата точки ряда. Источники пишут её тремя способами: «2024», «2026-07» и
    «2026-09-02». Неполная дата разворачивается в конец периода, иначе годовой ряд
    считался бы просроченным на весь свой год."""
    if not raw:
        return None
    parts = str(raw).strip().split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 12
        day = int(parts[2]) if len(parts) > 2 else monthrange(year, month)[1]
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def is_outdated(last: str | None, freq: str, today: date | None = None) -> bool:
    """Последняя точка старше лага, положенного её частоте."""
    point = parse_point_date(last)
    if point is None:
        return False
    today = today or date.today()
    return (today - point).days > MAX_AGE_DAYS.get(freq, DEFAULT_MAX_AGE_DAYS)


def freshness_badge(
    last: str | None,
    freq: str,
    stale: bool = False,
    today: date | None = None,
) -> str:
    """Бейдж свежести по двум признакам сразу.

    Признак `stale` говорит только о том, что забор данных не удался. Ряд, который
    забрался без ошибок, но кончается 2024 годом, по нему проходит как актуальный.
    Поэтому второй критерий: возраст самой последней точки.
    """
    if stale:
        return STALE_BADGE
    if is_outdated(last, freq, today):
        return (
            f'<span class="badge badge-stale">устарело: {html.escape(str(last))}</span>'
        )
    return FRESH_BADGE


def series_badge(series: dict, today: date | None = None) -> str:
    """Бейдж свежести ряда: частота и дата последней точки берутся из него самого."""
    obs = series.get("obs") or []
    return freshness_badge(
        obs[-1]["date"] if obs else None,
        series.get("freq", "M"),
        bool(series.get("stale")),
        today,
    )


def with_freshness(markup: str, series: dict, today: date | None = None) -> str:
    """Уточнить бейдж в уже собранной карточке ряда.

    Карточки рядов рисует общий для всех страниц build_pulse.card, и он ставит
    бейдж по одному лишь факту успешного забора. Здесь готовая разметка правится
    по возрасту точки, чтобы не разводить две конвенции оформления карточек.
    """
    badge = series_badge(series, today)
    return markup.replace(FRESH_BADGE, badge) if badge != FRESH_BADGE else markup
