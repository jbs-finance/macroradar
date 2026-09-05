"""Общая оболочка сайта для страниц радара: шапка, вкладки, мета-теги.

Страницы собираются вне роутера Next и обязаны выглядеть частью jbs.finance, а не
чужим виджетом. Здесь повторены только цвета и ритм шапки сайта, значения взяты из
app/globals.css и components/layout/Header.tsx репозитория website.
"""

from __future__ import annotations

import html
import json

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
.tabs a { display: inline-block; padding: 0.8rem 0.75rem; color: var(--muted-fg); text-decoration: none;
  font-size: 0.9375rem; font-weight: 500; border-bottom: 2px solid transparent; white-space: nowrap;
  transition: color var(--dur-in) var(--ease-out), border-color var(--dur-in) var(--ease-out); }
.tabs a[aria-current="page"] { color: var(--fg); border-bottom-color: var(--accent); }
.tabs a:hover, .tabs a:focus-visible { color: var(--fg); }
.tabs .title { margin-inline-end: auto; padding: 0.8rem 0.75rem 0.8rem 0; font-weight: 600; color: var(--fg); font-size: 0.9375rem; white-space: nowrap; }
[id] { scroll-margin-top: 64px; }
@media (max-width: 640px) {
  .site-bar .inner { height: auto; min-height: 52px; padding-block: 0.65rem; align-items: flex-start; }
  .site-brand { flex: 0 0 auto; }
  .site-links { justify-content: flex-end; gap: 0.35rem 0.7rem; font-size: 0.75rem; }
  .tabs .inner { justify-content: flex-start; padding-inline: 0.65rem; overflow-x: auto; }
  .tabs .title { display: none; }
  .tabs a { padding-inline: 0.25rem; font-size: 0.75rem; }
}
@media print { .site-bar, .tabs { display: none; } }
"""


def site_header(active: str) -> str:
    """Тёмная полоса сайта плюс липкие вкладки радара."""
    tabs = "\n".join(
        f'      <a href="{href}">{label}</a>' if key != active
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
      <h2 id="cta-title">Такой же радар по вашей отрасли или компании</h2>
      <p>Этот радар собирается автоматически из открытых источников. Тот же движок
        работает на данных клиента: продажи против рынка, цены поставщиков против
        инфляции, план против факта, с ежедневным обновлением и без ручной сводки.</p>
      <a class="cta-link" href="{SITE}/ru/contacts">Обсудить радар для вашего бизнеса</a>
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
                "creator": {"@type": "Organization", "name": "JB Solutions", "url": SITE},
                "spatialCoverage": {"@type": "Place", "name": "Казахстан"},
                "sourceOrganization": [
                    {"@type": "Organization", "name": n} for n in names.split(", ") if n
                ],
            },
            ensure_ascii=False,
        )
        + "</script>"
    )
