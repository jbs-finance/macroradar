"""Сборка страницы /macroradar/transport/ из out/transport.json.

Проценты к прошлому году берутся из официальных индексов БНС (значение минус 100).
Изменение годового грузооборота по видам сообщения это отношение двух опубликованных
значений, в шапке столбца оно подписано как расчёт.

Запуск: .venv/bin/python build_transport.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from build_housing import HOUSING_STYLE, last, month_label, pct
from build_pulse import STYLE, fmt_num, spark
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
from regional import REGIONS
from transport import DIRECTIONS, PREFIX

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "transport.json"
DEFAULT_OUT = HERE / "out" / "transport.html"

CARDS = (
    ("cargo_yoy", "Грузооборот"),
    ("passenger_yoy", "Пассажирооборот"),
)


def pick(by_id: dict, key: str, slug: str = "kz") -> dict | None:
    return by_id.get(f"{PREFIX}.{key}.{slug}")


def bn(value: float) -> str:
    return fmt_num(value / 1e9, 1)


def change_phrase(index_value: float, up: str, down: str) -> str:
    verb = up if index_value >= 100 else down
    return f"{verb} на {pct(index_value).lstrip('+−')}"


def headline(by_id: dict) -> str:
    parts = []
    cargo = pick(by_id, "cargo_yoy")
    point = last(cargo)
    if point:
        text = (
            f"Грузооборот за {month_label(point['date'])} года "
            f'<span class="hl">{change_phrase(point["value"], "вырос", "сократился")}</span> к прошлому году'
        )
        history = cargo["obs"]
        if len(history) > 12 and point["value"] <= min(o["value"] for o in history):
            text += f", это минимум ряда с {history[0]['date'][:4]} года"
        parts.append(text + ".")
    passenger = last(pick(by_id, "passenger_yoy"))
    if passenger:
        parts.append(
            f"Пассажирооборот {change_phrase(passenger['value'], 'вырос', 'сократился')}."
        )
    transit = pick(by_id, "cargo_transit")
    if transit and len(transit["obs"]) >= 2:
        before, now = transit["obs"][-2:]
        parts.append(
            f"Транзит грузов за {now['date']} год {bn(now['value'])} млрд т·км, "
            f"{pct(now['value'] / before['value'] * 100)} к {before['date']} году."
        )
    return f'<p class="housing-headline">{" ".join(parts)}</p>' if parts else ""


def index_card(by_id: dict, key: str, label: str) -> str:
    series = pick(by_id, key)
    point = last(series)
    if point is None:
        return no_data(f"нет ряда: {label.lower()}")
    history = [o for o in series["obs"] if o["date"] >= "2018-01"]
    badge = freshness_badge(point["date"], "M", bool(series.get("stale")))
    return f"""      <article class="card housing-card">
        <header class="card-head"><h3>{html.escape(label)}</h3>{badge}</header>
        <p class="value"><span class="num">{pct(point["value"])}</span> <span class="unit">к тому же месяцу прошлого года</span></p>
        {spark(history)}
        <p class="housing-note">{month_label(point["date"]).capitalize()}, индекс физического объёма БНС. График с января 2018 года.</p>
      </article>"""


def directions_section(by_id: dict) -> str:
    rows = []
    years = None
    for key, _term, label in DIRECTIONS:
        obs = (pick(by_id, f"cargo_{key}") or {}).get("obs") or []
        if len(obs) < 2:
            rows.append(
                f'<tr><td>{html.escape(label)}</td><td class="gap" colspan="3">н/д</td></tr>'
            )
            continue
        before, now = obs[-2:]
        years = years or (before["date"], now["date"])
        nested = key in ("export", "import", "transit")
        name = f"&nbsp;&nbsp;{html.escape(label)}" if nested else html.escape(label)
        row_class = ' class="country"' if key == "total" else ""
        rows.append(
            f"<tr{row_class}><td>{name}</td><td>{bn(before['value'])}</td><td>{bn(now['value'])}</td>"
            f"<td>{pct(now['value'] / before['value'] * 100)}</td></tr>"
        )
    if years is None:
        return no_data("годовой грузооборот не собран")
    values = {
        key: last(pick(by_id, f"cargo_{key}"))["value"]
        for key in ("total", "international", "domestic")
        if last(pick(by_id, f"cargo_{key}"))
    }
    residual = ""
    if len(values) == 3:
        rest = values["total"] - values["international"] - values["domestic"]
        residual = (
            f" Итог за {years[1]} год больше суммы международного и внутреннего сообщения "
            f"на {bn(rest)} млрд т·км: эту часть БНС по видам сообщения не разносит."
        )
    source = (pick(by_id, "cargo_total") or {}).get("source_url", "")
    return f"""    <section class="housing-section" aria-labelledby="directions-title">
      <h2 id="directions-title">Грузооборот по видам сообщения</h2>
      <p class="housing-note">Миллиардов тонно-километров за год, вид деятельности «Транспорт». Экспорт, импорт и транзит в сумме дают международное сообщение.{residual} Изменение рассчитано JB Solutions как отношение двух опубликованных значений.</p>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Грузооборот по видам сообщения</caption>
        <thead><tr><th scope="col">Сообщение</th><th scope="col">{years[0]}</th><th scope="col">{years[1]}</th><th scope="col">изменение</th></tr></thead>
        <tbody>{"".join(rows)}</tbody></table></div>
      <p class="housing-source">Источник: Бюро национальной статистики.<br><a href="{html.escape(source, quote=True)}">{html.escape(source)}</a></p>
    </section>"""


def passenger_section(by_id: dict) -> str:
    country = last(pick(by_id, "passenger_yoy"))
    if country is None:
        return no_data("пассажирооборот по регионам не собран")
    stamp = country["date"]
    rows = []
    for _term, name, slug in [("", "Казахстан", "kz"), *REGIONS]:
        point = last(pick(by_id, "passenger_yoy", slug))
        if point is None or point["date"] != stamp:
            rows.append(
                (
                    float("-inf"),
                    f'<tr><td>{html.escape(name)}</td><td class="gap">н/д</td></tr>',
                )
            )
            continue
        row_class = ' class="country"' if slug == "kz" else ""
        rows.append(
            (
                float("inf") if slug == "kz" else point["value"],
                f"<tr{row_class}><td>{html.escape(name)}</td><td>{pct(point['value'])}</td></tr>",
            )
        )
    rows.sort(key=lambda r: -r[0])
    source = (pick(by_id, "passenger_yoy") or {}).get("source_url", "")
    return f"""    <section class="housing-section" aria-labelledby="passenger-title">
      <h2 id="passenger-title">Пассажирооборот по регионам</h2>
      <p class="housing-note">{month_label(stamp).capitalize()}, все виды транспорта, к тому же месяцу прошлого года. Регионы отсортированы по росту.</p>
      <div class="table-wrap"><table class="city-table"><caption class="sr-only">Пассажирооборот по регионам</caption>
        <thead><tr><th scope="col">Регион</th><th scope="col">к прошлому году</th></tr></thead>
        <tbody>{"".join(r[1] for r in rows)}</tbody></table></div>
      <p class="housing-note">Грузооборот по регионам не показан: с января 2026 года областные индексы БНС в разы расходятся с прошлыми годами, сравнение с ними некорректно.</p>
      <p class="housing-source">Источник: Бюро национальной статистики.<br><a href="{html.escape(source, quote=True)}">{html.escape(source)}</a></p>
    </section>"""


def build(data: dict) -> str:
    by_id = {item.get("series_id"): item for item in data.get("series", [])}
    if not by_id:
        body, head_line = no_data("ряды по транспорту не собраны"), ""
    else:
        cards = "\n".join(index_card(by_id, key, label) for key, label in CARDS)
        body = (
            '    <section class="housing-section" id="transport-summary" aria-labelledby="summary-title">\n'
            '      <h2 id="summary-title">Страна за последний месяц</h2>\n'
            f'      <div class="housing-cards">\n{cards}\n      </div>\n    </section>\n'
            + directions_section(by_id)
            + "\n"
            + passenger_section(by_id)
        )
        head_line = headline(by_id)
    generated = datetime.fromisoformat(data["generated_at"])
    return TEMPLATE.format(
        meta=meta_tags(
            "Транспорт Казахстана: грузооборот, транзит, пассажирооборот",
            "Грузооборот и пассажирооборот Казахстана каждый месяц, транзит, экспорт и импорт грузов за год, пассажирооборот по регионам по данным БНС.",
            "/macroradar/transport/",
        ),
        style=STYLE
        + HEADER_STYLE
        + ACCESSIBILITY_STYLE
        + CTA_STYLE
        + NO_DATA_STYLE
        + HOUSING_STYLE,
        header=site_header("transport"),
        skip_link=skip_link(),
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
{meta}<title>Транспорт Казахстана</title><style>{style}</style></head><body>
{skip_link}{header}<div class="wrap"><header class="housing-hero"><h1>Транспорт Казахстана</h1>
<p class="lede">Грузооборот и пассажирооборот каждый месяц, транзит, экспорт и импорт грузов за год. Данные Бюро национальной статистики.</p>
{headline}
<p class="updated">Собрано <time datetime="{generated_iso}">{generated}</time></p></header>{issues}
<main id="main-content">
{body}{cta}</main>{footer}</div></body></html>"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build(json.loads(dataset.read_text(encoding="utf-8"))), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
