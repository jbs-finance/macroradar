"""Блок «Исполнение бюджета» для страницы /radar/tax/ по данным Минфина.

Четыре части: итог свежего периода, помесячные поступления против плана, разрез по
видам налогов с процентом исполнения и сравнение уровней бюджета. Скриптов нет,
страница отдаётся с запретом на них: всё, что здесь движется, движется на CSS.

Разбивки по областям в этих отчётах нет: отчёт по местным бюджетам сводный по
стране. Регионы берутся у КГД в budget_block, поэтому здесь уровни бюджета, а не
география.
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
        levels_section(data),
        oblast_section(data.get("oblast")),
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


LEVELS_STYLE = """
.lv { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  margin-block: 1rem; }
.lv-card { background: var(--card); border: 1px solid var(--muted); border-radius: var(--radius);
  padding: 0.9rem 1rem 1rem; }
.lv-card h4 { margin: 0 0 0.15rem; font-size: 0.9375rem; }
.lv-card .lv-sub { margin: 0 0 0.7rem; font-size: 0.75rem; color: var(--muted-fg); }
.lv-figures { display: flex; flex-wrap: wrap; gap: 0.15rem 1.25rem; margin: 0; }
.lv-figures div { display: flex; gap: 0.35rem; align-items: baseline; }
.lv-figures dt { margin: 0; font-size: 0.75rem; color: var(--muted-fg); }
.lv-figures dd { margin: 0; font-size: 0.9375rem; font-weight: 600;
  font-family: "JetBrains Mono", ui-monospace, monospace; }
.lv-bar { display: flex; height: 0.7rem; border-radius: 999px; overflow: hidden;
  margin-top: 0.8rem; background: var(--muted); }
.lv-bar i { display: block; animation: lv-grow 0.6s cubic-bezier(0.2, 0.7, 0.3, 1) both;
  transform-origin: left; }
.lv-bar i.own { background: var(--accent); }
.lv-bar i.transfer { background: #8C7B6B; }
.lv-bar i.other { background: #D8C7AE; }
.lv-legend { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 0.5rem 0 0;
  font-size: 0.75rem; color: var(--muted-fg); }
.lv-legend span { display: inline-flex; align-items: center; gap: 0.3rem; }
.lv-legend i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.lv-legend i.own { background: var(--accent); }
.lv-legend i.transfer { background: #8C7B6B; }
.lv-legend i.other { background: #D8C7AE; }

@keyframes lv-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (prefers-reduced-motion: reduce) {
  .lv-bar i { animation: none; }
}
"""


def is_tax_category(item: dict) -> bool:
    """«Неналоговые поступления» содержат в себе слово «налоговые»: сравнение по
    подстроке засчитывало их как налоги и завышало долю."""
    return item.get("code") == "1" or item["name"].lower().startswith("налоговые")


def income_split(income: list[dict]) -> dict:
    """Доходы уровня: собственные, трансферты и всё остальное."""
    total = sum(i["fact"] for i in income) or 1
    transfers = sum(i["fact"] for i in income if "рансферт" in i["name"])
    taxes = sum(i["fact"] for i in income if is_tax_category(i))
    return {
        "total": total,
        "taxes": taxes,
        "transfers": transfers,
        "other": total - taxes - transfers,
    }


def level_card(title: str, subtitle: str, latest: dict) -> str:
    split = income_split(latest.get("income") or [])
    total = latest["total"]
    pct = total["pct"] or (total["fact"] / total["plan"] * 100 if total["plan"] else 0)
    figures = [
        ("Налоги", fmt_num(total["fact"], 0)),
        ("Исполнение", f"{fmt_num(pct, 1)}%"),
        ("Все доходы", fmt_num(split["total"], 0)),
    ]
    body = "".join(
        f"<div><dt>{name}</dt><dd>{value}</dd></div>" for name, value in figures
    )
    shares = [
        ("own", split["taxes"], "налоги"),
        ("other", split["other"], "прочие доходы"),
        ("transfer", split["transfers"], "трансферты"),
    ]
    bar = "".join(
        f'<i class="{cls}" style="width: {value / split["total"] * 100:.1f}%; '
        f'animation-delay: {n * 0.08:.2f}s" title="{label}: '
        f'{fmt_num(value / split["total"] * 100, 1)}%"></i>'
        for n, (cls, value, label) in enumerate(shares)
        if value > 0
    )
    return (
        f'<article class="lv-card"><h4>{title}</h4>'
        f'<p class="lv-sub">{subtitle}</p>'
        f'<dl class="lv-figures">{body}</dl>'
        f'<div class="lv-bar">{bar}</div></article>'
    )


def levels_section(data: dict) -> str:
    """Сколько из собранного остаётся на местах и чем живут местные бюджеты."""
    state, local = data.get("latest"), data.get("local")
    if not state or not local:
        return ""
    label = period_label(local["year"], local["months"])
    local_split = income_split(local.get("income") or [])
    share_of_taxes = (
        local["total"]["fact"] / state["total"]["fact"] * 100
        if state["total"]["fact"]
        else 0
    )
    transfer_share = local_split["transfers"] / local_split["total"] * 100
    return "\n".join(
        [
            "<h3>Республика и места</h3>",
            '<p class="lede">Из всех собранных налогов местным бюджетам достаётся '
            f"<b>{fmt_num(share_of_taxes, 1)}%</b>, а <b>{fmt_num(transfer_share, 1)}%</b> "
            "их доходов приходит трансфертами из республиканского бюджета. "
            f"Оба отчёта за {label}.</p>",
            '<div class="lv">'
            + level_card(
                "Государственный бюджет",
                "республиканский и местные вместе",
                state,
            )
            + level_card(
                "Местные бюджеты",
                "области, города республиканского значения и столица",
                local,
            )
            + "</div>",
            '<p class="lv-legend"><span><i class="own"></i>налоги</span>'
            '<span><i class="other"></i>прочие доходы</span>'
            '<span><i class="transfer"></i>трансферты</span></p>',
        ]
    )


OBLAST_STYLE = """
.obl { display: grid; gap: 0.5rem; margin-block: 1rem; }
.obl-row { background: var(--card); border: 1px solid var(--muted); border-radius: var(--radius);
  padding: 0.7rem 0.9rem; display: grid; gap: 0.5rem 1rem; align-items: center;
  grid-template-columns: minmax(9rem, 14rem) 1fr minmax(8rem, 12rem); }
.obl-name { font-weight: 600; font-size: 0.9375rem; }
.obl-name span { display: block; font-weight: 400; font-size: 0.75rem; color: var(--muted-fg); }
.obl-mix { display: flex; height: 0.7rem; border-radius: 999px; overflow: hidden;
  background: var(--muted); }
.obl-mix i { display: block; animation: lv-grow 0.6s cubic-bezier(0.2, 0.7, 0.3, 1) both;
  transform-origin: left; }
.obl-mix i.own { background: var(--accent); }
.obl-mix i.transfer { background: #8C7B6B; }
.obl-figures { text-align: right; font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 0.8125rem; }
.obl-figures b { display: block; font-size: 0.9375rem; }
.obl-figures span { color: var(--muted-fg); }
.obl-mix.partial i.own { background: repeating-linear-gradient(135deg,
  var(--accent), var(--accent) 5px, #D8C7AE 5px, #D8C7AE 10px); }
.obl-legend { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 0.6rem 0 0.3rem;
  font-size: 0.75rem; color: var(--muted-fg); }
.obl-legend span { display: inline-flex; align-items: center; gap: 0.3rem; }
.obl-legend i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.obl-legend i.own { background: var(--accent); }
.obl-legend i.transfer { background: #8C7B6B; }
.obl-legend i.partial { background: repeating-linear-gradient(135deg,
  var(--accent), var(--accent) 3px, #D8C7AE 3px, #D8C7AE 6px); }
.obl-note { font-size: 0.8125rem; color: var(--muted-fg); }

@media (max-width: 40rem) {
  .obl-row { grid-template-columns: 1fr auto; }
  .obl-mix { grid-column: 1 / -1; }
}

@media (prefers-reduced-motion: reduce) {
  .obl-mix i { animation: none; }
}
"""


def plural(count: int, one: str, many: str, few: str) -> str:
    """Русское склонение при числе: 1 региона, 2 региона, 5 регионов."""
    tail = count % 100
    if 11 <= tail <= 14:
        word = many
    elif count % 10 == 1:
        word = one
    elif count % 10 in (2, 3, 4):
        word = few
    else:
        word = many
    return f"{count} {word}"


def oblast_row(region: dict) -> str:
    """Строка региона. Полнота отчётов разная, поэтому и подпись разная.

    Полная форма даёт структуру доходов, у части управлений публикуется только
    налоговая часть, а у части вообще текстовая справка с двумя числами. Выдавать
    их за одно и то же нельзя: полоса рисуется только там, где известны обе доли."""
    kind = region.get("kind", "full")
    period = period_label(region["year"], region["months"])
    stale = " · прошлый сбор" if region.get("stale") else ""
    total = region["total"] or 1
    pct = region.get("pct")
    plan_note = f", план {fmt_num(pct, 0)}%" if pct else ""

    if kind == "full":
        own = max(total - region["transfers"], 0)
        own_share = own / total * 100
        middle = (
            f'<span class="obl-mix">'
            f'<i class="own" style="width: {own_share:.1f}%"></i>'
            f'<i class="transfer" style="width: {100 - own_share:.1f}%; '
            f'animation-delay: 0.08s"></i></span>'
        )
        figures = (
            f'<b>{fmt_num(region["total"], 0)} млрд</b>'
            f'<span>своих {fmt_num(own_share, 0)}%{plan_note}</span>'
        )
    elif kind == "taxes":
        middle = '<span class="obl-mix partial"><i class="own" style="width: 100%"></i></span>'
        figures = (
            f'<b>{fmt_num(region["taxes"], 0)} млрд</b>'
            f"<span>только налоги{plan_note}</span>"
        )
    else:
        middle = '<span class="obl-mix partial"><i class="own" style="width: 100%"></i></span>'
        own = region.get("taxes")
        note = f"своих {fmt_num(own, 0)} млрд" if own else "справкой, без разреза"
        figures = f'<b>{fmt_num(region["total"], 0)} млрд</b><span>{note}{plan_note}</span>'

    return (
        f'<div class="obl-row">'
        f'<span class="obl-name">{html.escape(region["name"])}'
        f"<span>{period}{stale}</span></span>"
        f'{middle}<span class="obl-figures">{figures}</span></div>'
    )


def oblast_section(data: dict | None) -> str:
    """Свежие отчёты областей: у каждой свой период, поэтому это список, а не рейтинг.

    Собрать полную картину по стране из этих отчётов нельзя: часть управлений
    финансов публикует форму, которую невозможно прочитать машиной, часть отстала
    на годы. Поэтому здесь честный список тех, кто отчитался, а сопоставимый разрез
    по всем областям остаётся за данными КГД."""
    regions = (data or {}).get("regions") or []
    if not regions:
        return ""
    full = sum(1 for r in regions if r.get("kind", "full") == "full")
    return "\n".join(
        [
            "<h3>Свежие отчёты областей</h3>",
            '<p class="lede">Каждое областное управление финансов публикует своё '
            "исполнение бюджета отдельно и в свой срок. Полоса показывает, какую долю "
            "доходов регион собирает сам, а какую получает трансфертами.</p>",
            f'<div class="obl">{"".join(oblast_row(r) for r in regions)}</div>',
            '<p class="obl-legend"><span><i class="own"></i>свои доходы</span>'
            '<span><i class="transfer"></i>трансферты</span>'
            '<span><i class="partial"></i>разрез не опубликован</span></p>',
            f'<p class="obl-note">Отчёт нашёлся у '
            f"{plural(len(regions), 'региона', 'регионов', 'региона')} из двадцати, "
            f"со структурой доходов у {plural(full, 'региона', 'регионов', 'региона')}. "
            "Остальные публикуют форму без доходной части, презентацию для граждан "
            "или отстают на годы: их цифры сюда не попадают, чтобы не смешивать "
            "периоды и разные показатели.</p>",
        ]
    )
