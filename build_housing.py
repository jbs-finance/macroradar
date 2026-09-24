"""Сборка страницы /macroradar/housing/ из out/housing.json.

Заголовок страницы собирается из данных: выводится сегмент рынка, который за год вырос
сильнее остальных, и город с самым быстрым ростом в нём. Проценты берутся из
официальных индексов БНС (значение индекса минус 100), свои не считаются. Одно
исключение: изменение ввода жилья к тому же периоду прошлого года, это отношение двух
опубликованных значений, в шапке столбца оно подписано как расчёт.

Запуск: .venv/bin/python build_housing.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from build_pulse import STYLE, fmt_num, spark
from build_radar import MONTHS_RU_PAGE
from housing import CITIES, MARKETS, PREFIX, REGIONS_AND_COUNTRY
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
DATASET = HERE / "out" / "housing.json"
DEFAULT_OUT = HERE / "out" / "housing.html"
LISTINGS = HERE / "out" / "listings.json"
DEALS = HERE / "out" / "deals.json"

# Подлежащее и глагол для заголовка по сегменту рынка.
HEADLINE_SUBJECT = {
    "new": ("Новые квартиры", "подорожали", "подешевели"),
    "resale": ("Вторичные квартиры", "подорожали", "подешевели"),
    "rent": ("Аренда квартир", "подорожала", "подешевела"),
}
SHORT = {"new": "Новые", "resale": "Вторичка", "rent": "Аренда"}

HOUSING_STYLE = """
.housing-hero { padding-block: clamp(1.5rem, 5vw, 2.5rem) 1rem; max-width: 800px; }
.housing-hero h1 { max-width: 22ch; }
.housing-headline { margin: 0.9rem 0 0; font-size: clamp(1.125rem, 2.4vw, 1.4rem); font-weight: 600; line-height: 1.35; max-width: 40ch; }
.housing-headline .hl { color: var(--accent); }
.housing-cards { display: grid; gap: var(--sp); grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }
.housing-cards > * { min-width: 0; animation: rise var(--dur-in) var(--ease-out) both; }
.housing-cards > :nth-child(2) { animation-delay: 40ms; } .housing-cards > :nth-child(3) { animation-delay: 80ms; }
@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .housing-cards > * { animation: none; } }
.housing-card .unit { color: var(--muted-fg); font-size: 0.875rem; }
.housing-card .moves { margin: 0.35rem 0 0; display: flex; gap: 0.9rem; flex-wrap: wrap; font-size: 0.875rem; color: var(--muted-fg); }
.housing-card .moves b { color: var(--fg); font-variant-numeric: tabular-nums; }
.housing-section { margin-block: 2.25rem; }
.housing-note { margin: 0.35rem 0 0; color: var(--muted-fg); font-size: 0.875rem; max-width: 70ch; }
.table-wrap { overflow-x: auto; margin-top: 0.85rem; -webkit-overflow-scrolling: touch; }
.city-table { width: 100%; min-width: 0; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.city-table th, .city-table td { padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--muted); text-align: right; white-space: nowrap; }
.city-table th:first-child, .city-table td:first-child { padding-left: 0; text-align: left; position: sticky; left: 0; background: var(--bg); }
.city-table th { color: var(--muted-fg); font-size: 0.75rem; font-weight: 600; letter-spacing: .03em; }
.city-table tr.country td { font-weight: 600; }
.city-table td.gap { color: var(--muted-fg); }
.city-table .up { color: var(--accent); }
.housing-source { margin: 0.75rem 0 0; font-size: 0.8125rem; overflow-wrap: anywhere; color: var(--muted-fg); }
.housing-source a { color: inherit; }
@media (max-width: 640px) { .city-table th, .city-table td { padding-inline: 0.35rem; font-size: 0.8125rem; } }
"""


def last(series: dict | None) -> dict | None:
    obs = (series or {}).get("obs") or []
    return obs[-1] if obs else None


def month_label(stamp: str) -> str:
    year, month = stamp.split("-")
    return f"{MONTHS_RU_PAGE[int(month) - 1]} {year}"


def pct(index_value: float) -> str:
    change = round(index_value - 100, 1)
    sign = "+" if change > 0 else ("−" if change < 0 else "")
    return f"{sign}{fmt_num(abs(change), 1)}%"


def money(value: float) -> str:
    return fmt_num(value, 0)


def pick(by_id: dict, key: str, slug: str) -> dict | None:
    return by_id.get(f"{PREFIX}.{key}.{slug}")


def index_at(by_id: dict, key: str, slug: str, stamp: str) -> float | None:
    """Индекс строго за тот же месяц, что и цена: чужой месяц рядом с ценой вводит в заблуждение."""
    point = last(pick(by_id, key, slug))
    return point["value"] if point and point["date"] == stamp else None


def headline(by_id: dict) -> str:
    best = None
    for key, _market, _label, _unit in MARKETS:
        price = last(pick(by_id, f"price_{key}", "kz"))
        yoy = index_at(by_id, f"yoy_{key}", "kz", price["date"]) if price else None
        if yoy is not None and (best is None or yoy > best[1]):
            best = (key, yoy, price["date"])
    if best is None:
        return ""
    key, yoy, stamp = best
    subject, up, down = HEADLINE_SUBJECT[key]
    text = f'{subject} за год {up if yoy >= 100 else down} на <span class="hl">{pct(yoy).lstrip("+−")}</span>.'
    mom = index_at(by_id, f"mom_{key}", "kz", stamp)
    if mom is not None:
        month = MONTHS_RU_PAGE[int(stamp[5:]) - 1]
        text += f" За {month} {up if mom >= 100 else down} на {pct(mom).lstrip('+−')}."
    leaders = [
        (index_at(by_id, f"yoy_{key}", slug, stamp), name)
        for _t, name, slug in CITIES[1:]
    ]
    leaders = [item for item in leaders if item[0] is not None]
    if leaders:
        top, city = max(leaders)
        text += f" Быстрее всего в городе {html.escape(city)}: {pct(top)} за год."
    return f'<p class="housing-headline">{text}</p>'


def market_card(by_id: dict, key: str, label: str, unit: str) -> str:
    series = pick(by_id, f"price_{key}", "kz")
    point = last(series)
    if point is None:
        return no_data(f"нет цены: {label.lower()}")
    stamp = point["date"]
    moves = []
    for idx_key, caption in ((f"yoy_{key}", "за год"), (f"mom_{key}", "за месяц")):
        value = index_at(by_id, idx_key, "kz", stamp)
        if value is not None:
            moves.append(f"<span>{caption} <b>{pct(value)}</b></span>")
    history = [o for o in series["obs"] if o["date"] >= "2015-01"]
    badge = freshness_badge(stamp, "M", bool(series.get("stale")))
    return f"""      <article class="card housing-card">
        <header class="card-head"><h3>{html.escape(label)}</h3>{badge}</header>
        <p class="value"><span class="num">{money(point["value"])}</span> <span class="unit">{html.escape(unit)}</span></p>
        <p class="moves">{"".join(moves)}</p>
        {spark(history)}
        <p class="housing-note">{month_label(stamp).capitalize()}, среднее по стране. График с января 2015 года.</p>
      </article>"""


def city_row(by_id: dict, slug: str, name: str, stamps: dict[str, str]) -> str:
    cells = []
    for key, _market, _label, _unit in MARKETS:
        point = last(pick(by_id, f"price_{key}", slug))
        if point is None or point["date"] != stamps.get(key):
            cells += ['<td class="gap">н/д</td>', '<td class="gap">н/д</td>']
            continue
        yoy = index_at(by_id, f"yoy_{key}", slug, point["date"])
        cls = ' class="up"' if yoy is not None and yoy - 100 >= 15 else ""
        cells.append(f"<td>{money(point['value'])}</td>")
        cells.append(
            f"<td{cls}>{pct(yoy)}</td>"
            if yoy is not None
            else '<td class="gap">н/д</td>'
        )
    row_class = ' class="country"' if slug == "kz" else ""
    return f"<tr{row_class}><td>{html.escape(name)}</td>{''.join(cells)}</tr>"


def cities_section(by_id: dict) -> str:
    stamps = {}
    for key, _market, _label, _unit in MARKETS:
        point = last(pick(by_id, f"price_{key}", "kz"))
        if point:
            stamps[key] = point["date"]
    if not stamps:
        return no_data("цены по городам не собраны")
    order = sorted(
        CITIES[1:],
        key=lambda c: -((last(pick(by_id, "price_new", c[2])) or {}).get("value") or 0),
    )
    rows = "\n".join(
        city_row(by_id, slug, name, stamps) for _t, name, slug in [CITIES[0], *order]
    )
    head = "".join(
        f'<th scope="col">{SHORT[key]}, ₸/м²</th><th scope="col">за год</th>'
        for key, _m, _l, _u in MARKETS
    )
    month = month_label(max(stamps.values()))
    source = (pick(by_id, "price_new", "kz") or {}).get("source_url", "")
    return f"""    <section class="housing-section" aria-labelledby="cities-title">
      <h2 id="cities-title">Цены по городам</h2>
      <p class="housing-note">{month.capitalize()}. Цена одного квадратного метра общей площади, аренда за квадратный метр в месяц. Города отсортированы по цене новых квартир, рост за год от 15% выделен цветом.</p>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Цены на жильё по городам</caption>
        <thead><tr><th scope="col">Город</th>{head}</tr></thead>
        <tbody>{rows}</tbody></table></div>
      <p class="housing-source">Источник: Бюро национальной статистики, выборочное наблюдение цен на жильё по форме 1-ЦРЖ.<br><a href="{html.escape(source, quote=True)}">{html.escape(source)}</a></p>
    </section>"""


def built_section(by_id: dict) -> str:
    country = last(pick(by_id, "built_ytd", "kz"))
    if country is None:
        return no_data("ввод жилья не собран")
    stamp = country["date"]
    year, month = stamp.split("-")
    year_ago = f"{int(year) - 1}-{month}"
    rows = []
    for _term, name, slug in REGIONS_AND_COUNTRY:
        series = pick(by_id, "built_ytd", slug)
        obs = {o["date"]: o["value"] for o in (series or {}).get("obs", [])}
        now, before = obs.get(stamp), obs.get(year_ago)
        if now is None:
            rows.append(
                (
                    -1,
                    f'<tr><td>{html.escape(name)}</td><td class="gap" colspan="3">нет данных за {month_label(stamp)}</td></tr>',
                )
            )
            continue
        change = f"{pct(now / before * 100)}" if before else "н/д"
        row_class = ' class="country"' if slug == "kz" else ""
        rows.append(
            (
                float("inf") if slug == "kz" else now,
                f"<tr{row_class}><td>{html.escape(name)}</td><td>{fmt_num(now / 1000, 1)}</td>"
                f"<td>{fmt_num(before / 1000, 1) if before else 'н/д'}</td><td>{change}</td></tr>",
            )
        )
    rows.sort(key=lambda r: -r[0])
    months = int(month)
    source = (pick(by_id, "built_ytd", "kz") or {}).get("source_url", "")
    return f"""    <section class="housing-section" aria-labelledby="built-title">
      <h2 id="built-title">Ввод жилья по регионам</h2>
      <p class="housing-note">Общая площадь введённого жилья за {months} мес. {year} года нарастающим итогом, тысяч квадратных метров. Изменение рассчитано JB Solutions как отношение двух опубликованных значений.</p>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Ввод жилья по регионам</caption>
        <thead><tr><th scope="col">Регион</th><th scope="col">{months} мес. {year}</th><th scope="col">{months} мес. {int(year) - 1}</th><th scope="col">изменение</th></tr></thead>
        <tbody>{"".join(r[1] for r in rows)}</tbody></table></div>
      <p class="housing-source">Источник: Бюро национальной статистики.<br><a href="{html.escape(source, quote=True)}">{html.escape(source)}</a></p>
    </section>"""


def deals_section(deals: dict | None) -> str:
    """Число сделок купли-продажи из ежемесячных релизов БНС. Изменения считаются здесь, подписаны как расчёт."""
    obs = (deals or {}).get("obs") or []
    if not obs:
        return f"""    <section class="housing-section" id="housing-deals" aria-labelledby="deals-title">
      <h2 id="deals-title">Сделки купли-продажи жилья</h2>
{no_data("релизы БНС о сделках не разобраны при последнем сборе")}
    </section>"""
    latest = obs[-1]
    prev = obs[-2] if len(obs) > 1 and obs[-2]["date"] < latest["date"] else None
    moves = []
    if prev:
        moves.append(f"<span>за месяц <b>{pct(latest['total'] / prev['total'] * 100)}</b></span>")
    moves.append(f"<span>квартиры <b>{fmt_num(latest['flats'] / latest['total'] * 100, 1)}%</b></span>")
    rows = "".join(
        f"<tr><td>{month_label(o['date'])}</td><td>{money(o['total'])}</td><td>{money(o['flats'])}</td>"
        f"<td>{money(o['houses'])}</td><td>{money(o['almaty']) if o.get('almaty') else 'н/д'}</td>"
        f"<td>{money(o['astana']) if o.get('astana') else 'н/д'}</td></tr>"
        for o in reversed(obs)
    )
    # Спарклайн только по непрерывному хвосту: пропуск месяца на линии выглядел бы как плавный переход.
    tail = [obs[-1]]
    for o in reversed(obs[:-1]):
        y, m = map(int, tail[-1]["date"].split("-"))
        expected = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
        if o["date"] != expected:
            break
        tail.append(o)
    history = [{"date": o["date"], "value": o["total"]} for o in reversed(tail)]
    return f"""    <section class="housing-section" id="housing-deals" aria-labelledby="deals-title">
      <h2 id="deals-title">Сделки купли-продажи жилья</h2>
      <p class="housing-note">Зарегистрированные сделки по всей стране. БНС публикует их пресс-релизом примерно на десятый день после месяца, таблицы к релизу нет, поэтому цифры взяты из текста. В таблице месяцы, релиз по которым удалось разобрать.</p>
      <div class="housing-cards"><article class="card housing-card">
        <header class="card-head"><h3>{month_label(latest["date"]).capitalize()}</h3></header>
        <p class="value"><span class="num">{money(latest["total"])}</span> <span class="unit">сделок</span></p>
        <p class="moves">{"".join(moves)}</p>
        {spark(history)}
        <p class="housing-note">График: {month_label(history[0]["date"])} … {month_label(latest["date"])}. Изменение к прошлому месяцу рассчитано JB Solutions.</p>
      </article></div>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Сделки купли-продажи жилья по месяцам</caption>
        <thead><tr><th scope="col">Месяц</th><th scope="col">всего</th><th scope="col">квартиры</th><th scope="col">дома</th><th scope="col">Алматы</th><th scope="col">Астана</th></tr></thead>
        <tbody>{rows}</tbody></table></div>
      <p class="housing-source">Источник: Бюро национальной статистики, пресс-релиз за {month_label(latest["date"])}.<br><a href="{html.escape(latest["url"], quote=True)}">{html.escape(latest["url"])}</a></p>
    </section>"""


def offer_rows(rows: list[dict]) -> str:
    return "".join(
        f"<tr><td>{html.escape(r['city'])}</td><td>{r['rooms']}</td>"
        f"<td>{fmt_num(r['listings_on_site'], 0) if r.get('listings_on_site') else 'н/д'}</td>"
        f"<td>{money(r['median'])}</td><td>{money(r['q1'])} … {money(r['q3'])}</td></tr>"
        for r in rows
    )


def listings_section(by_id: dict, listings: dict | None) -> str:
    """Цены предложения площадок рядом с ценой БНС. Отдельный тип доверия, свои подписи."""
    if not listings or not (listings.get("kn") or listings.get("avi") or listings.get("korter")):
        return f"""    <section class="housing-section" id="housing-listings" aria-labelledby="listings-title">
      <h2 id="listings-title">Цены предложения на площадках</h2>
{no_data("площадки объявлений не ответили при последнем сборе")}
    </section>"""
    day = datetime.fromisoformat(listings["generated_at"]).strftime("%d.%m.%Y")
    bns = {
        slug: {key: last(pick(by_id, f"price_{key}", slug)) for key in ("new", "resale")}
        for _t, _name, slug in CITIES
    }
    slug_of = {name: slug for _t, name, slug in CITIES}
    parts = [
        f"""    <section class="housing-section" id="housing-listings" aria-labelledby="listings-title">
      <h2 id="listings-title">Цены предложения на площадках</h2>
      <p class="housing-note">Срез на {day}. Здесь цены, которые просят продавцы в объявлениях. Статистику БНС и цены сделок они не заменяют, зато показывают живой рынок: сколько квартир выставлено и почём.</p>"""
    ]
    kn = listings.get("kn") or []
    if kn:
        rows = offer_rows(kn)
        compare = []
        for city in dict.fromkeys(r["city"] for r in kn):
            points = bns.get(slug_of.get(city, ""), {})
            new, resale = points.get("new"), points.get("resale")
            if new and resale:
                compare.append(
                    f"{html.escape(city)}: новые {money(new['value'])}, вторичка {money(resale['value'])} ₸/м² ({month_label(resale['date'])})"
                )
        compare_note = f'<p class="housing-note">Для сравнения, БНС: {"; ".join(compare)}.</p>' if compare else ""
        parts.append(f"""      <h3>Квартиры в продаже на kn.kz</h3>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Цены предложения kn.kz по комнатности</caption>
        <thead><tr><th scope="col">Город</th><th scope="col">комнат</th><th scope="col">объявлений</th><th scope="col">медиана, ₸/м²</th><th scope="col">половина цен в диапазоне</th></tr></thead>
        <tbody>{rows}</tbody></table></div>
      <p class="housing-note">Медиана и квартили цены за м² по свежим объявлениям, до {max(r["sample"] for r in kn)} в строке: новые и вторичные квартиры вместе, как их выставляет площадка.</p>
      {compare_note}""")
    avi = listings.get("avi") or []
    if avi:
        parts.append(f"""      <h3>Квартиры в продаже на avi.kz</h3>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Цены предложения avi.kz по комнатности</caption>
        <thead><tr><th scope="col">Город</th><th scope="col">комнат</th><th scope="col">объявлений</th><th scope="col">медиана, ₸/м²</th><th scope="col">половина цен в диапазоне</th></tr></thead>
        <tbody>{offer_rows(avi)}</tbody></table></div>
      <p class="housing-note">Доска объявлений общего профиля, квартир на ней мало: в расчёт идут все объявления раздела, строки с выборкой меньше 10 не показываются.</p>""")
    korter = listings.get("korter") or []
    rows = []
    for r in korter:
        point = bns.get(slug_of.get(r["city"].split(" (")[0], ""), {}).get("new")
        if point is None:
            continue
        gap = pct(r["avg_price_m2"] / point["value"] * 100)
        rows.append(
            (r["avg_price_m2"], f"<tr><td>{html.escape(r['city'].split(' (')[0])}</td><td>{money(r['avg_price_m2'])}</td><td>{money(point['value'])}</td><td>{gap}</td></tr>")
        )
    if rows:
        rows.sort(key=lambda x: -x[0])
        parts.append(f"""      <h3>Новостройки на korter.kz</h3>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Средняя цена новостроек korter.kz и БНС</caption>
        <thead><tr><th scope="col">Город</th><th scope="col">korter, ₸/м²</th><th scope="col">БНС новые, ₸/м²</th><th scope="col">разница</th></tr></thead>
        <tbody>{"".join(r[1] for r in rows)}</tbody></table></div>
      <p class="housing-note">Средняя цена м² жилых комплексов на korter.kz, методику площадка не раскрывает. БНС за последний опубликованный месяц. Разница рассчитана JB Solutions.</p>""")
    parts.append(f"""      <p class="housing-source">Источники: <a href="https://www.kn.kz/">kn.kz</a>, <a href="https://avi.kz/">avi.kz</a>, <a href="https://korter.kz/">korter.kz</a>. Сбор раз в сутки с паузой между запросами, без персональных данных продавцов.</p>
    </section>""")
    return "\n".join(parts)


def build(data: dict, listings: dict | None = None, deals: dict | None = None) -> str:
    by_id = {item.get("series_id"): item for item in data.get("series", [])}
    if not by_id:
        body = no_data("ряды по жилью не собраны")
        head_line = ""
        month = ""
    else:
        cards = "\n".join(
            market_card(by_id, k, label, unit) for k, _m, label, unit in MARKETS
        )
        country = last(pick(by_id, "price_new", "kz"))
        month = month_label(country["date"]) if country else ""
        body = (
            f'    <section class="housing-section" id="housing-summary" aria-labelledby="summary-title">\n'
            f'      <h2 id="summary-title">Страна за {month}</h2>\n'
            f'      <div class="housing-cards">\n{cards}\n      </div>\n    </section>\n'
            + cities_section(by_id)
            + "\n"
            + deals_section(deals)
            + "\n"
            + listings_section(by_id, listings)
            + "\n"
            + built_section(by_id)
        )
        head_line = headline(by_id)
    generated = datetime.fromisoformat(data["generated_at"])
    return TEMPLATE.format(
        meta=meta_tags(
            "Цены на жильё в Казахстане: квадратный метр, аренда, ввод",
            "Цена квадратного метра новых и вторичных квартир, аренда и ввод жилья по городам и регионам Казахстана, каждый месяц по данным БНС.",
            "/macroradar/housing/",
        ),
        style=STYLE
        + HEADER_STYLE
        + ACCESSIBILITY_STYLE
        + CTA_STYLE
        + NO_DATA_STYLE
        + HOUSING_STYLE,
        header=site_header("housing"),
        skip_link=skip_link(),
        month=f" Данные за {month}." if month else "",
        headline=head_line,
        generated=generated.strftime("%d.%m.%Y %H:%M UTC"),
        generated_iso=generated.isoformat(),
        issues=issues_notice(data.get("issues")),
        body=body,
        cta=cta_block(),
        footer=detail_footer(date.today().year),
    )


TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{meta}<title>Цены на жильё в Казахстане</title><style>{style}</style></head><body>
{skip_link}{header}<div class="wrap"><header class="housing-hero"><h1>Жильё в Казахстане</h1>
<p class="lede">Цена квадратного метра, аренда и ввод жилья по городам и регионам. Бюро национальной статистики публикует их каждый месяц на девятый день.{month}</p>
{headline}
<p class="updated">Собрано <time datetime="{generated_iso}">{generated}</time></p></header>{issues}
<main id="main-content">
{body}{cta}</main>{footer}</div></body></html>"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else DATASET
    listings_path = Path(sys.argv[3]) if len(sys.argv) > 3 else LISTINGS
    listings = json.loads(listings_path.read_text(encoding="utf-8")) if listings_path.exists() else None
    deals = json.loads(DEALS.read_text(encoding="utf-8")) if DEALS.exists() else None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build(json.loads(dataset.read_text(encoding="utf-8")), listings, deals), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
