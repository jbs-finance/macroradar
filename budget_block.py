"""Региональный разрез поступлений для страницы /radar/tax/.

Помесячный график с переключением по областям, рядом с ним сравнение регионов из
compare_block. Переключение сделано на радиокнопках и CSS: страница отдаётся с
запретом скриптов (CSP script-src 'none'), и ослаблять его ради интерактива нельзя.

Данные приходят из budget.py. Итог страны и разрез по видам налогов живут не здесь,
а в minfin_block: Минфин публикует их на год свежее, чем КГД.
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

CHART_W = 720
CHART_H = 250
PAD_L = 46
PAD_R = 8
PAD_T = 14
PAD_B = 26

BUDGET_STYLE = """

.drill { background: var(--card); border: 1px solid var(--muted); border-radius: var(--radius);
  overflow: hidden; margin-block: 1rem; }
.drill-radio { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.drill-tabs { display: flex; gap: 0.35rem; overflow-x: auto; padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--muted); scrollbar-width: thin; }
.drill-tabs label { flex: 0 0 auto; font-size: 0.8125rem; line-height: 1; padding: 0.45rem 0.7rem;
  border: 1px solid var(--muted); border-radius: 999px; cursor: pointer; white-space: nowrap;
  color: var(--muted-fg); background: var(--bg); transition: background 0.18s ease, color 0.18s ease,
  border-color 0.18s ease; }
.drill-tabs label:hover { border-color: var(--accent); color: var(--fg); }
.drill-stage { padding: 0.9rem 1rem 1.1rem; }
.series { display: none; }
.series-head { display: flex; flex-wrap: wrap; gap: 0.5rem 1.25rem; align-items: baseline;
  justify-content: space-between; margin-bottom: 0.6rem; }
.series-name { font-weight: 600; }
.series-sub { color: var(--muted-fg); font-size: 0.8125rem; }
.series-stats { display: flex; flex-wrap: wrap; gap: 0.15rem 1.1rem; margin: 0; }
.series-stats div { display: flex; gap: 0.35rem; align-items: baseline; }
.series-stats dt { color: var(--muted-fg); font-size: 0.75rem; margin: 0; }
.series-stats dd { margin: 0; font-size: 0.875rem; font-weight: 600;
  font-family: "JetBrains Mono", ui-monospace, monospace; }
.series-stats dd.up { color: #2F7A4F; }
.series-stats dd.down { color: var(--accent); }
/* На узком экране график не сжимается до нечитаемых подписей, а прокручивается:
   двенадцать месяцев на 375 пикселях иначе превращаются в кашу. */
.chart-scroll { overflow-x: auto; margin-inline: -0.25rem; padding-inline: 0.25rem; }
.chart { width: 100%; min-width: 480px; height: auto; display: block; overflow: visible; }
.chart .grid { stroke: var(--muted); stroke-width: 1; }
.chart .axis { fill: var(--muted-fg); font-size: 11px;
  font-family: "JetBrains Mono", ui-monospace, monospace; }
.chart .bar-now { fill: var(--accent); }
.chart .bar-prev { fill: var(--muted); }
.chart .bar-now, .chart .bar-prev { transform-box: fill-box; transform-origin: bottom; }
.series-legend { display: flex; gap: 1rem; margin: 0.5rem 0 0; font-size: 0.75rem;
  color: var(--muted-fg); }
.series-legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
.series-legend i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.series-legend .k-now { background: var(--accent); }
.series-legend .k-prev { background: var(--muted); }


@keyframes bar-rise { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes series-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

/* На широком экране все регионы видны сразу, на узком остаётся полоса прокрутки:
   перенос двадцати двух кнопок в столбик съел бы весь экран. */
@media (min-width: 48rem) {
  .drill-tabs { flex-wrap: wrap; overflow-x: visible; }
}

@media (prefers-reduced-motion: reduce) {
  .chart .bar-now, .chart .bar-prev, .series { animation: none !important; }
}
"""


def drill_rules(count: int) -> str:
    """Правила показа выбранной серии и подсветки её вкладки.

    Пишутся отдельно от основного CSS, потому что зависят от числа регионов."""
    rules = []
    for i in range(count):
        rules.append(
            f"#rg{i}:checked ~ .drill-stage .s{i} {{ display: block; "
            f"animation: series-in 0.25s ease both; }}"
        )
        rules.append(
            f'#rg{i}:checked ~ .drill-tabs label[for="rg{i}"] '
            f"{{ background: var(--accent); border-color: var(--accent); color: #fff; }}"
        )
        rules.append(
            f'#rg{i}:focus-visible ~ .drill-tabs label[for="rg{i}"] '
            f"{{ outline: 2px solid var(--fg); outline-offset: 2px; }}"
        )
    return "\n" + "\n".join(rules) + "\n"


def normalize(name: str) -> str:
    """Имена регионов между годами пишутся по-разному: «г.Алматы» и «г. Алматы»."""
    return (
        name.lower()
        .replace("ё", "е")
        .replace("г.", "")
        .replace("область", "")
        .replace(" ", "")
        .replace("-", "")
        .strip()
    )


def nice_step(top: float) -> float:
    """Шаг сетки: круглое число, которое даёт 3-5 линий."""
    raw = top / 4
    magnitude = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 0.1
    for mult in (1, 2, 2.5, 5, 10):
        if magnitude * mult >= raw:
            return magnitude * mult
    return magnitude * 10


def chart_svg(
    values: list[float | None],
    prev: list[float | None],
    label: str,
    year: int,
    prev_year: int | None,
) -> str:
    """Сгруппированные столбики: бледный прошлый год, насыщенный текущий."""
    points = [v for v in list(values) + list(prev) if v]
    top = max(points) if points else 1
    step = nice_step(top)
    top = step * (int(top / step) + 1)
    inner_w = CHART_W - PAD_L - PAD_R
    inner_h = CHART_H - PAD_T - PAD_B
    group = inner_w / 12
    bar = group * 0.34

    parts = [
        f'<svg class="chart" viewBox="0 0 {CHART_W} {CHART_H}" role="img" '
        f'aria-label="{html.escape(label)}">'
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

    for i in range(12):
        x0 = PAD_L + group * i
        parts.append(
            f'<text class="axis" x="{x0 + group / 2:.1f}" y="{CHART_H - 8}" '
            f'text-anchor="middle">{MONTH_SHORT[i]}</text>'
        )
        for kind, series, offset, series_year in (
            ("prev", prev, group * 0.13, prev_year),
            ("now", values, group * 0.5, year),
        ):
            value = series[i] if i < len(series) else None
            if not value:
                continue
            height = value / top * inner_h
            y = PAD_T + inner_h - height
            delay = i * 0.03
            parts.append(
                f'<rect class="bar-{kind}" x="{x0 + offset:.1f}" y="{y:.1f}" '
                f'width="{bar:.1f}" height="{height:.1f}" rx="2" '
                f'style="animation: bar-rise 0.45s cubic-bezier(0.2,0.7,0.3,1) {delay:.2f}s both">'
                f"<title>{MONTH_CASE[i]} {series_year}: {fmt_num(value, 0)} млрд тенге"
                f"</title></rect>"
            )
    parts.append("</svg>")
    return "".join(parts)


def series_stats(
    values: list[float | None], prev: list[float | None], share: float | None
) -> str:
    total = sum(v for v in values if v)
    peak_i = max(range(len(values)), key=lambda i: values[i] or 0)
    pairs = [
        (v, p) for v, p in zip(values, prev) if v and p
    ]  # сравниваем только месяцы, закрытые в обоих годах
    yoy = None
    if pairs:
        base = sum(p for _, p in pairs)
        yoy = (sum(v for v, _ in pairs) / base - 1) * 100 if base else None

    cells = [("За год", f"{fmt_num(total, 0)}", "")]
    cells.append((f"Пик · {MONTH_CASE[peak_i]}", fmt_num(values[peak_i] or 0, 0), ""))
    if yoy is not None:
        sign = "+" if yoy > 0 else ""
        tone = "up" if yoy > 0 else "down" if yoy < 0 else ""
        cells.append(
            (f"К прошлому году · {len(pairs)} мес.", f"{sign}{fmt_num(yoy, 1)}%", tone)
        )
    if share is not None:
        cells.append(("Доля в стране", f"{fmt_num(share, 1)}%", ""))

    body = "".join(
        f"<div><dt>{html.escape(name)}</dt>"
        f"<dd{f' class="{tone}"' if tone else ''}>{value}</dd></div>"
        for name, value, tone in cells
    )
    return f'<dl class="series-stats">{body}</dl>'


REGION_LABEL = {"КГД МФ РК": "КГД, центральный аппарат"}


def build_series(dynamics: dict) -> list[dict]:
    """Республика первой, дальше регионы по убыванию поступлений."""
    prev = dynamics.get("previous") or {}
    prev_total = prev.get("total") or [None] * 12
    prev_by_region = {
        normalize(r["name"]): r["values"] for r in prev.get("regions", [])
    }

    country = sum(v for v in dynamics["total"] if v)
    out = [
        {
            "name": "Республика",
            "values": dynamics["total"],
            "prev": prev_total,
            "share": 100.0 if country else None,
        }
    ]
    regions = sorted(
        dynamics["regions"], key=lambda r: -sum(v for v in r["values"] if v)
    )
    for region in regions:
        total = sum(v for v in region["values"] if v)
        out.append(
            {
                "name": REGION_LABEL.get(
                    region["name"].strip(), region["name"].strip()
                ),
                "values": region["values"],
                "prev": prev_by_region.get(normalize(region["name"]), [None] * 12),
                "share": total / country * 100 if country else None,
            }
        )
    return out


def drill_block(dynamics: dict) -> tuple[str, str]:
    series = build_series(dynamics)
    year = dynamics["year"]
    prev_year = (dynamics.get("previous") or {}).get("year")

    inputs = "".join(
        f'<input class="drill-radio" type="radio" name="drill-region" id="rg{i}"'
        f"{' checked' if i == 0 else ''}>"
        for i in range(len(series))
    )
    tabs = "".join(
        f'<label for="rg{i}">{html.escape(s["name"])}</label>'
        for i, s in enumerate(series)
    )
    legend = (
        f'<p class="series-legend"><span><i class="k-now"></i>{year}</span>'
        + (f'<span><i class="k-prev"></i>{prev_year}</span>' if prev_year else "")
        + "</p>"
    )
    stages = []
    for i, s in enumerate(series):
        label = f"{s['name']}: поступления по месяцам {year} года, млрд тенге"
        stages.append(
            f'<div class="series s{i}">'
            f'<div class="series-head"><div><span class="series-name">'
            f"{html.escape(s['name'])}</span> "
            f'<span class="series-sub">{year}, млрд тенге</span></div>'
            f"{series_stats(s['values'], s['prev'], s['share'])}</div>"
            f'<div class="chart-scroll">'
            f"{chart_svg(s['values'], s['prev'], label, year, prev_year)}</div>"
            f"{legend}</div>"
        )
    block = (
        '<div class="drill">'
        + inputs
        + f'<div class="drill-tabs" role="tablist">{tabs}</div>'
        + '<div class="drill-stage">'
        + "".join(stages)
        + "</div></div>"
    )
    return block, drill_rules(len(series))


def budget_section(budget: dict) -> tuple[str, str]:
    """Региональный разрез: HTML блока и CSS-правила под число регионов.

    Итог страны и разрез по видам налогов сюда не входят: они берутся у Минфина,
    который публикует их на год свежее. У КГД остаётся то, чего больше нигде нет,
    разбивка по областям."""
    dynamics = budget.get("dynamics")
    if not dynamics:
        return "", ""
    from compare_block import compare_block  # цикл на уровне модуля: он берёт build_series

    drill, rules = drill_block(dynamics)
    compare, compare_rules_css = compare_block(dynamics)
    year = dynamics["year"]
    parts = [
        "<h2>Кто платит: регионы</h2>",
        '<p class="lede">Разбивку по областям публикует только Комитет государственных '
        f"доходов, и его последний такой файл за {year} год. Цифры страны выше свежее: "
        "они из ежемесячных отчётов Минфина.</p>",
        f"<h3>Помесячно, {year} год</h3>",
        '<p class="lede">Выберите регион. Столбик поменьше это тот же месяц прошлого года, '
        "наведение показывает точную сумму.</p>",
        drill,
    ]
    if compare:
        parts += [
            "<h3>Все регионы сразу</h3>",
            '<p class="lede">Один и тот же год в трёх разрезах: сколько собрал регион, '
            "насколько вырос и сколько дал общему приросту страны.</p>",
            compare,
        ]
        rules += compare_rules_css
    notes = [
        "<li>Суммы приведены в млрд тенге, источник публикует тысячи.</li>",
        "<li>Строка «КГД, центральный аппарат» это не регион, а платежи, "
        "администрируемые центральным аппаратом комитета.</li>",
        "<li>Рост и вклад в прирост считаются только по месяцам, закрытым в обоих "
        "годах: файл прошлого года у источника бывает неполным.</li>",
    ]
    parts.append(
        "<details><summary>Как читать эти цифры</summary>"
        f'<div class="details-body"><ul>{"".join(notes)}</ul></div></details>'
    )
    return "\n".join(parts), rules
