"""Блок «Исполнение бюджета» для страницы /radar/tax/ по данным Минфина.

Три части: итог свежего периода, помесячные поступления против плана и разрез по
видам налогов с процентом исполнения. Скриптов нет, страница отдаётся с запретом
на них: всё, что здесь движется, движется на CSS.
"""

from __future__ import annotations

import html

from build_pulse import fmt_num

MONTH_SHORT = [
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
]
MONTH_CASE = [
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
]
MONTH_GEN = [
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
]

# Наименования в отчёте занимают строку целиком, для рейтинга нужны короткие.
SHORT_NAME = {
    "01": "Подоходный налог",
    "03": "Социальный налог",
    "04": "Налоги на собственность",
    "05": "НДС, акцизы и прочие внутренние",
    "06": "Налоги на международную торговлю",
    "07": "Прочие налоги",
    "08": "Госпошлина и обязательные платежи",
}

CHART_W = 720
CHART_H = 230
PAD_L = 46
PAD_R = 8
PAD_T = 16
PAD_B = 34

MINFIN_STYLE = """
.mf-cards { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  margin-block: 1rem; }
.mf-cards .card { gap: 0.15rem; }
.mf-cards .num { font-size: 1.375rem; }
/* Название налога это не число: крупный моноширинный кегль рвал его на три строки. */
.mf-cards .num.text { font-size: 1.0625rem; font-family: inherit; font-weight: 600;
  line-height: 1.3; }
.mf-cards .num.up { color: #2F7A4F; }
.mf-cards .num.down { color: var(--accent); }

.mf-chart-box { background: var(--card); border: 1px solid var(--muted);
  border-radius: var(--radius); padding: 0.9rem 1rem 1.1rem; margin-block: 1rem; }
.mf-scroll { overflow-x: auto; margin-inline: -0.25rem; padding-inline: 0.25rem; }
.mf-chart { width: 100%; min-width: 520px; height: auto; display: block; }
.mf-chart .grid { stroke: var(--muted); stroke-width: 1; }
.mf-chart .axis { fill: var(--muted-fg); font-size: 11px;
  font-family: "JetBrains Mono", ui-monospace, monospace; }
.mf-chart .axis.year { font-size: 10px; opacity: 0.75; }
.mf-chart .bar { fill: var(--accent); transform-box: fill-box; transform-origin: bottom;
  animation: mf-rise 0.45s cubic-bezier(0.2, 0.7, 0.3, 1) both; }
.mf-chart .bar.under { fill: #C99A86; }
.mf-chart .plan { stroke: var(--fg); stroke-width: 2; }
.mf-chart .gap { fill: var(--muted-fg); font-size: 10px; opacity: 0.7; }
.mf-legend { display: flex; flex-wrap: wrap; gap: 1rem; margin: 0.6rem 0 0;
  font-size: 0.75rem; color: var(--muted-fg); }
.mf-legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
.mf-legend i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.mf-legend i.k-fact { background: var(--accent); }
.mf-legend i.k-under { background: #C99A86; }
.mf-legend i.k-plan { width: 12px; height: 2px; border-radius: 0; background: var(--fg); }

.plan-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.plan-table th { text-align: right; font-weight: 600; color: var(--muted-fg);
  font-size: 0.75rem; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--muted); }
.plan-table th:first-child, .plan-table td:first-child { text-align: left; }
.plan-table td { padding: 0.55rem 0.6rem; border-bottom: 1px solid var(--muted);
  text-align: right; font-family: "JetBrains Mono", ui-monospace, monospace; }
.plan-table td:first-child { font-family: inherit; }
.plan-table tr:last-child td { border-bottom: 0; }
.plan-table tfoot td { font-weight: 600; border-top: 1px solid var(--muted); }
.plan-pct { display: inline-flex; align-items: center; gap: 0.4rem; justify-content: flex-end; }
.plan-pct b { font-weight: 600; min-width: 3.6rem; text-align: right; }
.plan-pct b.none { min-width: 0; color: var(--muted-fg); font-weight: 400; }
.plan-pct u { display: block; width: 3.2rem; height: 0.45rem; border-radius: 999px;
  background: var(--muted); position: relative; overflow: hidden; text-decoration: none; }
.plan-pct u i { position: absolute; inset: 0 auto 0 0; background: var(--accent);
  border-radius: 999px; animation: plan-grow 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) both; }
.plan-pct u i.done { background: #2F7A4F; }
.plan-scroll { overflow-x: auto; background: var(--card); border: 1px solid var(--muted);
  border-radius: var(--radius); padding: 0.25rem 1rem; margin-block: 1rem; }

@keyframes mf-rise { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes plan-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (prefers-reduced-motion: reduce) {
  .mf-chart .bar, .plan-pct u i { animation: none; }
}
"""


def period_label(year: int, months: int) -> str:
    """«январь-июль 2026», а для одного месяца просто «январь 2026»."""
    if months == 1:
        return f"{MONTH_CASE[0]} {year}"
    return f"{MONTH_CASE[0]}-{MONTH_CASE[months - 1]} {year}"


def clean_name(item: dict) -> str:
    """Короткое имя по коду: в отчёте наименования занимают целую строку."""
    name = SHORT_NAME.get(item["code"])
    if name:
        return name
    # В отчёте встречается латинская H в начале русских слов.
    return item["name"].replace("H", "Н").strip()


def nice_step(top: float) -> float:
    raw = top / 4
    magnitude = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 0.1
    for mult in (1, 2, 2.5, 5, 10):
        if magnitude * mult >= raw:
            return magnitude * mult
    return magnitude * 10


def month_chart(monthly: list[dict]) -> str:
    """Столбик факта и риска плана над ним: сразу видно, добрали или нет.

    Пропущенные источником месяцы остаются пустыми: разность за два месяца сразу
    нельзя разложить обратно, а рисовать её как один месяц значит врать."""
    if not monthly:
        return ""
    first, last = monthly[0], monthly[-1]
    span = (last["year"] - first["year"]) * 12 + last["month"] - first["month"] + 1
    slots = [
        (
            first["year"] + (first["month"] - 1 + i) // 12,
            (first["month"] - 1 + i) % 12 + 1,
        )
        for i in range(span)
    ]
    by_period = {(m["year"], m["month"]): m for m in monthly}
    top = max(max(m["value"], m["plan"]) for m in monthly)
    step = nice_step(top)
    top = step * (int(top / step) + 1)

    inner_w = CHART_W - PAD_L - PAD_R
    inner_h = CHART_H - PAD_T - PAD_B
    group = inner_w / len(slots)
    width = group * 0.52

    parts = [
        f'<svg class="mf-chart" viewBox="0 0 {CHART_W} {CHART_H}" role="img" '
        f'aria-label="Поступления по месяцам против плана, млрд тенге">'
    ]
    line = 0.0
    while line <= top + 1e-9:
        y = PAD_T + inner_h - line / top * inner_h
        parts.append(
            f'<line class="grid" x1="{PAD_L}" y1="{y:.1f}" x2="{CHART_W - PAD_R}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'<text class="axis" x="{PAD_L - 6}" y="{y + 3:.1f}" text-anchor="end">'
            f"{fmt_num(line, 0)}</text>"
        )
        line += step

    for i, (year, month) in enumerate(slots):
        x0 = PAD_L + group * i
        centre = x0 + group / 2
        parts.append(
            f'<text class="axis" x="{centre:.1f}" y="{CHART_H - 18}" text-anchor="middle">'
            f"{MONTH_SHORT[month - 1]}</text>"
        )
        if month == 1 or i == 0:
            parts.append(
                f'<text class="axis year" x="{centre:.1f}" y="{CHART_H - 5}" '
                f'text-anchor="middle">{year}</text>'
            )
        point = by_period.get((year, month))
        if not point:
            # Подпись ставится один раз на всю череду пропусков: у соседних месяцев
            # тексты налезали друг на друга.
            previous_missing = i > 0 and slots[i - 1] not in by_period
            run = 1
            while i + run < len(slots) and slots[i + run] not in by_period:
                run += 1
            if not previous_missing:
                parts.append(
                    f'<text class="gap" x="{x0 + group * run / 2:.1f}" '
                    f'y="{PAD_T + inner_h - 6}" text-anchor="middle">нет отчёта</text>'
                )
            continue
        height = point["value"] / top * inner_h
        y = PAD_T + inner_h - height
        under = point["plan"] and point["value"] < point["plan"]
        delay = i * 0.03
        share = point["value"] / point["plan"] * 100 if point["plan"] else 0
        parts.append(
            f'<rect class="bar{" under" if under else ""}" x="{x0 + (group - width) / 2:.1f}" '
            f'y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="2" '
            f'style="animation-delay: {delay:.2f}s">'
            f"<title>{MONTH_CASE[month - 1]} {year}: собрано {fmt_num(point['value'], 0)} "
            f"из {fmt_num(point['plan'], 0)} млрд, {fmt_num(share, 0)}% плана</title></rect>"
        )
        if point["plan"]:
            py = PAD_T + inner_h - point["plan"] / top * inner_h
            parts.append(
                f'<line class="plan" x1="{x0 + (group - width) / 2 - 2:.1f}" y1="{py:.1f}" '
                f'x2="{x0 + (group + width) / 2 + 2:.1f}" y2="{py:.1f}"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


def summary_cards(data: dict) -> str:
    latest = data["latest"]
    total = latest["total"]
    label = period_label(latest["year"], latest["months"])
    gap = total["fact"] - total["plan"]
    pct = total["pct"] or (total["fact"] / total["plan"] * 100 if total["plan"] else 0)
    cards = [
        (
            f"Собрано за {label}",
            f"{fmt_num(total['fact'], 0)} млрд ₸",
            "налоговые поступления в государственный бюджет",
            "",
        ),
        (
            "Исполнение плана",
            f"{fmt_num(pct, 1)}%",
            (
                f"{'перевыполнение' if gap > 0 else 'недобор'} "
                f"{fmt_num(abs(gap), 0)} млрд к плану на период"
            ),
            "up" if gap >= 0 else "down",
        ),
    ]
    year_ago = latest.get("year_ago")
    if year_ago and year_ago["fact"]:
        change = (total["fact"] / year_ago["fact"] - 1) * 100
        cards.append(
            (
                "К прошлому году",
                f"{'+' if change > 0 else ''}{fmt_num(change, 1)}%",
                f"против {fmt_num(year_ago['fact'], 0)} млрд за тот же отрезок "
                f"{year_ago['period'][:4]} года",
                "up" if change > 0 else "down",
            )
        )
    if latest["items"]:
        top = latest["items"][0]
        share = top["fact"] / total["fact"] * 100 if total["fact"] else 0
        cards.append(
            (
                "Главный источник",
                html.escape(clean_name(top)),
                f"{fmt_num(share, 1)}% налоговых поступлений",
                "text",
            )
        )
    return (
        '<div class="mf-cards">'
        + "".join(
            f'<article class="card"><h3>{title}</h3>'
            f'<p class="value"><span class="num{" " + tone if tone else ""}">{value}</span></p>'
            f'<p class="asof">{note}</p></article>'
            for title, value, note, tone in cards
        )
        + "</div>"
    )


def plan_table(latest: dict) -> str:
    total = latest["total"]
    rows = []
    for item in latest["items"]:
        pct = item["pct"]
        if pct is None:
            pct = item["fact"] / item["plan"] * 100 if item["plan"] else 0
        gap = item["fact"] - item["plan"]
        # План около нуля даёт бессмысленные проценты вроде 2400%.
        showable = item["plan"] > total["plan"] * 0.005
        fill = min(pct, 100.0) if showable else 0.0
        done = " done" if showable and pct >= 100 else ""
        pct_cell = (
            f'<span class="plan-pct"><b>{fmt_num(pct, 1)}%</b>'
            f'<u><i class="{done.strip()}" style="width: {fill:.1f}%"></i></u></span>'
            if showable
            else '<span class="plan-pct"><b class="none">плана нет</b></span>'
        )
        rows.append(
            f"<tr><td>{html.escape(clean_name(item))}</td>"
            f"<td>{fmt_num(item['plan'], 0)}</td>"
            f"<td>{fmt_num(item['fact'], 0)}</td>"
            f"<td>{'+' if gap > 0 else ''}{fmt_num(gap, 0)}</td>"
            f"<td>{pct_cell}</td></tr>"
        )
    total_gap = total["fact"] - total["plan"]
    total_pct = total["pct"] or 0
    return (
        '<div class="plan-scroll"><table class="plan-table">'
        "<thead><tr><th>Налог</th><th>План</th><th>Собрано</th><th>Отклонение</th>"
        "<th>Исполнение</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody><tfoot><tr><td>Все налоговые поступления</td>"
        f"<td>{fmt_num(total['plan'], 0)}</td><td>{fmt_num(total['fact'], 0)}</td>"
        f"<td>{'+' if total_gap > 0 else ''}{fmt_num(total_gap, 0)}</td>"
        f'<td><span class="plan-pct"><b>{fmt_num(total_pct, 1)}%</b></span></td>'
        "</tr></tfoot></table></div>"
    )


def minfin_section(data: dict | None) -> str:
    if not data or not data.get("latest"):
        return ""
    latest = data["latest"]
    label = period_label(latest["year"], latest["months"])
    monthly = data.get("monthly") or []
    missing = []
    if monthly:
        have = {(m["year"], m["month"]) for m in monthly}
        first, last = monthly[0], monthly[-1]
        span = (last["year"] - first["year"]) * 12 + last["month"] - first["month"] + 1
        for i in range(span):
            year = first["year"] + (first["month"] - 1 + i) // 12
            month = (first["month"] - 1 + i) % 12 + 1
            if (year, month) not in have:
                missing.append(f"{MONTH_CASE[month - 1]} {year}")

    parts = [
        "<h2>Сколько собирают на самом деле</h2>",
        '<p class="lede">Ставки в таблицах ниже это норма. Здесь фактическое '
        "исполнение государственного бюджета по отчётам Министерства финансов: "
        f"свежие данные за {label}, план и факт рядом.</p>",
        summary_cards(data),
    ]
    if monthly:
        parts += [
            "<h3>Помесячно, факт против плана</h3>",
            '<p class="lede">Столбик это собранное за месяц, риска над ним плановое '
            "задание на тот же месяц. Наведение показывает точные суммы.</p>",
            '<div class="mf-chart-box"><div class="mf-scroll">'
            + month_chart(monthly)
            + "</div>"
            '<p class="mf-legend"><span><i class="k-fact"></i>план выполнен</span>'
            '<span><i class="k-under"></i>ниже плана</span>'
            '<span><i class="k-plan"></i>план месяца</span></p></div>',
        ]
    parts += [
        f"<h3>Исполнение плана по видам налогов, {label}</h3>",
        '<p class="lede">Нарастающим итогом с начала года, млрд тенге. План это '
        "сводный план поступлений на отчётный период, а не годовой бюджет.</p>",
        plan_table(latest),
    ]
    notes = [
        "<li>Помесячные суммы вычислены как разности накопительных отчётов: "
        "источник публикует их только нарастающим итогом.</li>",
        "<li>Проценты исполнения взяты из самого отчёта, а не пересчитаны.</li>",
    ]
    if missing:
        notes.append(
            "<li>Пропущены месяцы, за которые отчёт не публиковался: "
            f"{html.escape(', '.join(missing))}. Разность за два месяца сразу нельзя "
            "разложить обратно, поэтому эти столбики пустые.</li>"
        )
    if latest.get("stale"):
        notes.append(
            "<li>Свежий отчёт получить не удалось, показан прошлый собранный срез.</li>"
        )
    parts.append(
        "<details><summary>Как это посчитано</summary>"
        f'<div class="details-body"><ul>{"".join(notes)}</ul></div></details>'
    )
    return "\n".join(parts)
