"""Сравнение регионов на одном экране для страницы /radar/tax/.

Три взгляда на один и тот же год, переключаются радиокнопками и CSS: сколько
собрал регион, насколько вырос и сколько дал общему приросту страны. Третий взгляд
здесь главный: по объёму рейтинг почти не меняется годами, а прирост показывает,
кто на самом деле двигает бюджет.

Рост и вклад считаются только по месяцам, закрытым в обоих годах: файл прошлого
года у источника бывает неполным, и сравнение целых лет завысило бы падение.
"""

from __future__ import annotations

import html

from budget_block import MONTH_CASE, build_series
from build_pulse import fmt_num

SPARK_W = 78
SPARK_H = 20

COMPARE_STYLE = """
.cmp { background: var(--card); border: 1px solid var(--muted); border-radius: var(--radius);
  overflow: hidden; margin-block: 1rem; }
.cmp-radio { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.cmp-tabs { display: flex; flex-wrap: wrap; gap: 0.35rem; padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--muted); }
.cmp-tabs label { font-size: 0.8125rem; line-height: 1; padding: 0.45rem 0.7rem;
  border: 1px solid var(--muted); border-radius: 999px; cursor: pointer; white-space: nowrap;
  color: var(--muted-fg); background: var(--bg);
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease; }
.cmp-tabs label:hover { border-color: var(--accent); color: var(--fg); }
.cmp-stage { padding: 0.9rem 1rem 1.1rem; }
.cmp-mode { display: none; }
.cmp-note { margin: 0 0 0.75rem; font-size: 0.875rem; color: var(--muted-fg); max-width: 72ch; }
.cmp-note b { color: var(--fg); font-weight: 600; }

.rank { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.3rem; }
.rank li { display: grid; align-items: center; gap: 0.6rem;
  grid-template-columns: 1.4rem minmax(7rem, 11rem) auto 1fr auto;
  padding: 0.2rem 0; font-size: 0.875rem; }
.rank-pos { color: var(--muted-fg); font-size: 0.75rem; text-align: right;
  font-family: "JetBrains Mono", ui-monospace, monospace; }
.rank-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-spark { display: block; }
.rank-spark .sp-line { fill: none; stroke: var(--muted-fg); stroke-width: 1.2; opacity: 0.55; }
.rank-bar { position: relative; height: 0.55rem; background: var(--muted); border-radius: 999px; }
.rank-bar i { position: absolute; top: 0; bottom: 0; border-radius: 999px;
  background: var(--accent); animation: rank-grow 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) both; }
.rank-bar i.pos { background: #2F7A4F; }
/* Ось нуля у знаковых метрик: без неё столбик влево читается как обычный. */
.rank-bar.split::before { content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px;
  width: 1px; background: var(--muted-fg); opacity: 0.45; }
.rank-val { font-family: "JetBrains Mono", ui-monospace, monospace; white-space: nowrap;
  text-align: right; font-size: 0.8125rem; min-width: 8.5rem; }
.rank-val b { font-weight: 600; }
.rank-val b.up { color: #2F7A4F; }
.rank-val b.down { color: var(--accent); }
.rank-val span { display: inline-block; min-width: 3.6rem; color: var(--muted-fg); }
.rank-none { color: var(--muted-fg); }

@keyframes rank-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (max-width: 44rem) {
  .rank li { grid-template-columns: 1.4rem 1fr auto; row-gap: 0.15rem; }
  .rank-spark { display: none; }
  .rank-bar { grid-column: 2 / -1; }
}

@media (prefers-reduced-motion: reduce) {
  .rank-bar i { animation: none; }
}
"""


def compare_rules(count: int) -> str:
    rules = []
    for i in range(count):
        rules.append(f"#md{i}:checked ~ .cmp-stage .cm{i} {{ display: block; }}")
        rules.append(
            f'#md{i}:checked ~ .cmp-tabs label[for="md{i}"] '
            f"{{ background: var(--accent); border-color: var(--accent); color: #fff; }}"
        )
        rules.append(
            f'#md{i}:focus-visible ~ .cmp-tabs label[for="md{i}"] '
            f"{{ outline: 2px solid var(--fg); outline-offset: 2px; }}"
        )
    return "\n" + "\n".join(rules) + "\n"


def spark(values: list[float | None]) -> str:
    """Линия сезонности: форма важнее уровня, поэтому ось растянута по размаху ряда."""
    points = [v for v in values if v]
    if len(points) < 2:
        return f'<svg class="rank-spark" width="{SPARK_W}" height="{SPARK_H}"></svg>'
    lo, hi = min(points), max(points)
    span = hi - lo or 1
    step = SPARK_W / max(len(points) - 1, 1)
    coords = " ".join(
        f"{i * step:.1f},{SPARK_H - 2 - (v - lo) / span * (SPARK_H - 4):.1f}"
        for i, v in enumerate(points)
    )
    return (
        f'<svg class="rank-spark" width="{SPARK_W}" height="{SPARK_H}" '
        f'viewBox="0 0 {SPARK_W} {SPARK_H}" aria-hidden="true" focusable="false">'
        f'<polyline class="sp-line" points="{coords}"/></svg>'
    )


def region_stats(series: list[dict]) -> list[dict]:
    """Годовой итог, рост и вклад в прирост по каждому региону."""
    out = []
    for s in series[1:]:
        pairs = [(v, p) for v, p in zip(s["values"], s["prev"]) if v and p]
        now = sum(v for v, _ in pairs)
        was = sum(p for _, p in pairs)
        out.append(
            {
                "name": s["name"],
                "values": s["values"],
                "total": sum(v for v in s["values"] if v),
                "share": s["share"],
                "months": len(pairs),
                "growth": (now / was - 1) * 100 if pairs and was else None,
                "delta": now - was if pairs else None,
            }
        )
    return out


def bar(width_pct: float, positive: bool, split: bool) -> str:
    """Полоса от левого края или от середины, если у метрики есть знак."""
    width = max(min(abs(width_pct), 50.0 if split else 100.0), 0.6)
    if not split:
        return f'<span class="rank-bar"><i style="width: {width:.1f}%"></i></span>'
    side = "left: 50%" if positive else "right: 50%"
    tone = " pos" if positive else ""
    return (
        f'<span class="rank-bar split"><i class="{tone.strip()}" '
        f'style="{side}; width: {width:.1f}%"></i></span>'
    )


def rank_rows(items: list[dict], metric: str) -> str:
    if metric == "total":
        top = max((i["total"] for i in items), default=1) or 1
    elif metric == "growth":
        top = (
            max((abs(i["growth"]) for i in items if i["growth"] is not None), default=1)
            or 1
        )
    else:
        top = (
            max((abs(i["delta"]) for i in items if i["delta"] is not None), default=1)
            or 1
        )

    rows = []
    for n, item in enumerate(items, 1):
        if metric == "total":
            value = f"<b>{fmt_num(item['total'], 0)}</b> "
            value += f"<span>{fmt_num(item['share'] or 0, 1)}%</span>"
            line = bar(item["total"] / top * 100, True, False)
        elif metric == "growth":
            if item["growth"] is None:
                value = '<b class="rank-none">нет базы</b> <span></span>'
                line = '<span class="rank-bar split"></span>'
            else:
                sign = "+" if item["growth"] > 0 else ""
                tone = "up" if item["growth"] > 0 else "down"
                value = (
                    f'<b class="{tone}">{sign}{fmt_num(item["growth"], 1)}%</b> '
                    f"<span>{fmt_num(item['total'], 0)}</span>"
                )
                line = bar(item["growth"] / top * 50, item["growth"] > 0, True)
        else:
            if item["delta"] is None:
                value = '<b class="rank-none">нет базы</b> <span></span>'
                line = '<span class="rank-bar split"></span>'
            else:
                sign = "+" if item["delta"] > 0 else ""
                tone = "up" if item["delta"] > 0 else "down"
                value = (
                    f'<b class="{tone}">{sign}{fmt_num(item["delta"], 0)}</b> '
                    f"<span>млрд</span>"
                )
                line = bar(item["delta"] / top * 50, item["delta"] > 0, True)
        rows.append(
            f'<li><span class="rank-pos">{n}</span>'
            f'<span class="rank-name">{html.escape(item["name"])}</span>'
            f"{spark(item['values'])}{line}"
            f'<span class="rank-val">{value}</span></li>'
        )
    return f'<ol class="rank">{"".join(rows)}</ol>'


def note_total(items: list[dict]) -> str:
    top3 = sum(i["share"] or 0 for i in items[:3])
    half = 0.0
    count = 0
    for item in items:
        if half >= 50:
            break
        half += item["share"] or 0
        count += 1
    return (
        f"Три первых региона дают <b>{fmt_num(top3, 1)}%</b> всех поступлений страны, "
        f"половину бюджета собирают <b>{count}</b> из {len(items)}. "
        "Столбик показывает объём относительно лидера, линия рядом это сезонность года."
    )


def note_growth(items: list[dict]) -> str:
    known = [i for i in items if i["growth"] is not None]
    if not known:
        return "Прошлый год недоступен, сравнивать не с чем."
    best, worst = known[0], known[-1]
    grew = sum(1 for i in known if i["growth"] > 0)
    months = known[0]["months"]
    return (
        f"Быстрее всех <b>{html.escape(best['name'])}</b> "
        f"({'+' if best['growth'] > 0 else ''}{fmt_num(best['growth'], 1)}%), "
        f"слабее всех <b>{html.escape(worst['name'])}</b> "
        f"({'+' if worst['growth'] > 0 else ''}{fmt_num(worst['growth'], 1)}%). "
        f"В плюсе <b>{grew}</b> регионов из {len(known)}. "
        f"Сравниваются {months} месяцев, закрытых в обоих годах."
    )


def note_delta(items: list[dict]) -> str:
    known = [i for i in items if i["delta"] is not None]
    if not known:
        return "Прошлый год недоступен, вклад в прирост посчитать не из чего."
    gain = sum(i["delta"] for i in known if i["delta"] > 0)
    if not gain:
        return "Прироста в этом году не было."
    top3 = sum(i["delta"] for i in known[:3] if i["delta"] > 0)
    losers = [i for i in known if i["delta"] < 0]
    tail = (
        f" Ниже прошлого года собрали <b>{len(losers)}</b> регионов." if losers else ""
    )
    return (
        f"Из всего прироста <b>{fmt_num(gain, 0)}</b> млрд тенге три первых региона "
        f"дали <b>{fmt_num(top3 / gain * 100, 0)}%</b>. Рейтинг по объёму почти не "
        f"меняется годами, а здесь видно, кто двигает бюджет прямо сейчас.{tail}"
    )


MODES = [
    ("Объём за год", "total", note_total, lambda i: -i["total"]),
    (
        "Рост к прошлому году",
        "growth",
        note_growth,
        lambda i: -(i["growth"] if i["growth"] is not None else -1e9),
    ),
    (
        "Вклад в прирост",
        "delta",
        note_delta,
        lambda i: -(i["delta"] if i["delta"] is not None else -1e9),
    ),
]


def compare_block(dynamics: dict) -> tuple[str, str]:
    items = region_stats(build_series(dynamics))
    if not items:
        return "", ""
    inputs = "".join(
        f'<input class="cmp-radio" type="radio" name="cmp-metric" id="md{i}"'
        f"{' checked' if i == 0 else ''}>"
        for i in range(len(MODES))
    )
    tabs = "".join(
        f'<label for="md{i}">{title}</label>' for i, (title, *_) in enumerate(MODES)
    )
    stages = []
    for i, (_, metric, note, order) in enumerate(MODES):
        ordered = sorted(items, key=order)
        stages.append(
            f'<div class="cmp-mode cm{i}"><p class="cmp-note">{note(ordered)}</p>'
            f"{rank_rows(ordered, metric)}</div>"
        )
    block = (
        '<div class="cmp">'
        + inputs
        + f'<div class="cmp-tabs">{tabs}</div>'
        + '<div class="cmp-stage">'
        + "".join(stages)
        + "</div></div>"
    )
    return block, compare_rules(len(MODES))
