"""Сборка страницы jbs.finance/pulse из out/pulse.json.

Страница самодостаточна: инлайновый CSS, инлайновые SVG, ноль внешних запросов.
Открывается с диска и печатается.

Запуск: .venv/bin/python build_pulse.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "pulse.json"
DEFAULT_OUT = HERE / "out" / "index.html"

FX_ORDER = ["kz.fx.usd", "kz.fx.eur", "kz.fx.rub", "kz.fx.cny"]
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}

BNS_ORDER = ["kz.gdp.kzt", "kz.wage.avg", "kz.population.bns"]
MACRO_ORDER = [
    "kz.gdp.usd",
    "kz.gdp.pc.usd",
    "kz.cpi.yoy",
    "kz.unemployment",
    "kz.population",
]

MONTHS_RU = [
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


def fmt_num(value: float, digits: int = 2) -> str:
    """Русский формат: неразрывный пробел в разрядах, запятая в дробной части."""
    # Неразрывный пробел в разрядах: число не должно рваться переносом строки.
    return f"{value:,.{digits}f}".replace(",", "\u00a0").replace(".", ",")


def fmt_date(stamp: str) -> str:
    """Год, квартал, месяц и дата приходят из разных источников в разных формах."""
    if len(stamp) == 4:
        return stamp
    if "-Q" in stamp:
        year, quarter = stamp.split("-Q")
        return f"{ROMAN[int(quarter)]} квартал {year}"
    if len(stamp) == 7:
        year, month = stamp.split("-")
        return f"{MONTHS_RU[int(month) - 1]} {year}".capitalize()
    d = date.fromisoformat(stamp)
    return f"{d.day} {MONTHS_RU[d.month - 1]} {d.year}"


# Сколько точек назад лежит «год назад» для каждой периодичности.
YEAR_BACK = {"A": 1, "Q": 4, "M": 12}


def pct_change(series: dict, days_back: int) -> float | None:
    """Изменение за год. None если базы для сравнения нет."""
    obs = series["obs"]
    if len(obs) < 2:
        return None
    last = obs[-1]
    step = YEAR_BACK.get(series["freq"])
    if step:
        if len(obs) <= step:
            return None
        base = obs[-1 - step]
    else:
        target = date.fromisoformat(last["date"]).toordinal() - days_back
        base = min(
            obs[:-1],
            key=lambda o: abs(date.fromisoformat(o["date"]).toordinal() - target),
        )
    if not base["value"]:
        return None
    return (last["value"] - base["value"]) / base["value"] * 100


def spark(obs: list[dict], width: int = 320, height: int = 64) -> str:
    """Линия ряда в SVG. Ось Y растянута по фактическому размаху, не от нуля:
    задача показать форму движения, а не абсолютный масштаб.

    Ряд короче двух точек рисовать нечем: polyline из одной координаты браузер
    не отображает, и карточка получала пустой прямоугольник вместо графика."""
    values = [o["value"] for o in obs if o.get("value") is not None]
    if len(values) < 2:
        return (
            f'<svg class="spark spark-empty" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="данных для графика нет" focusable="false">'
            f'<text x="{width / 2:.0f}" y="{height / 2 + 4:.0f}" '
            f'text-anchor="middle">данных для графика нет</text>'
            f"</svg>"
        )
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    step = width / max(len(values) - 1, 1)
    pad = 6
    inner = height - pad * 2
    points = [
        f"{i * step:.1f},{pad + inner - (v - lo) / span * inner:.1f}"
        for i, v in enumerate(values)
    ]
    poly = " ".join(points)
    area = f"0,{height} {poly} {width},{height}"
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" role="img" aria-hidden="true" focusable="false">'
        f'<polygon class="spark-area" points="{area}"/>'
        f'<polyline class="spark-line" points="{poly}"/>'
        f"</svg>"
    )


def delta_markup(change: float | None, period: str) -> str:
    if change is None:
        return '<p class="delta delta-none">база для сравнения недоступна</p>'
    direction = "выше" if change > 0 else "ниже" if change < 0 else "без изменения"
    tone = "up" if change > 0 else "down" if change < 0 else "flat"
    sign = "+" if change > 0 else ""
    return (
        f'<p class="delta delta-{tone}">'
        f'<span class="delta-value">{sign}{fmt_num(change, 1)}%</span> '
        f'<span class="delta-note">{direction}, чем {period}</span></p>'
    )


def card(series: dict, digits: int, period_label: str, days_back: int) -> str:
    last = series["obs"][-1]
    stale = series.get("stale")
    badge = (
        '<span class="badge badge-stale">данные устарели</span>'
        if stale
        else '<span class="badge badge-fresh">актуально</span>'
    )
    return f"""      <article class="card">
        <header class="card-head">
          <h3>{html.escape(series["name_ru"])}</h3>
          {badge}
        </header>
        <p class="value"><span class="num">{fmt_num(last["value"], digits)}</span>
          <span class="unit">{html.escape(series["unit"])}</span></p>
        {delta_markup(pct_change(series, days_back), period_label)}
        {spark(series["obs"])}
        <p class="asof">на {fmt_date(last["date"])}, источник: {html.escape(series["source"])}</p>
      </article>"""


def fx_row(series: dict) -> str:
    """Строка курса. График скрыт до клика: на пульс смотрят ради текущего курса,
    а динамика нужна не всегда. Раскрытие на details, потому что скриптов на
    странице нет вовсе и добавлять их ради одного показа графика незачем."""
    last = series["obs"][-1]
    change = pct_change(series, 365)
    if change is None:
        arrow, tone, delta = "", "flat", "нет базы"
    else:
        arrow = "▲" if change > 0 else "▼" if change < 0 else ""
        tone = "up" if change > 0 else "down" if change < 0 else "flat"
        delta = f"{'+' if change > 0 else ''}{fmt_num(change, 1)}%"
    code = series["name_ru"].replace("Курс ", "")
    stale = ' <span class="badge badge-stale">устарело</span>' if series.get("stale") else ""
    return f"""        <details class="fx-row">
          <summary>
            <span class="fx-code">{html.escape(code)}{stale}</span>
            <span class="fx-rate">{fmt_num(last["value"], 2)}</span>
            <span class="fx-delta fx-{tone}"><span class="fx-arrow" aria-hidden="true">{arrow}</span>{delta}</span>
            <span class="fx-hint"></span>
          </summary>
          <div class="fx-chart">
            {spark(series["obs"])}
            <p class="asof">{len(series["obs"])} точек, последняя на {fmt_date(last["date"])},
              источник: {html.escape(series["source"])}</p>
          </div>
        </details>"""


def fx_table(rows: list[dict], as_of: str) -> str:
    body = "\n".join(fx_row(s) for s in rows)
    return f"""      <div class="fx">
        <div class="fx-head">
          <span>Валюта</span>
          <span class="fx-rate">Тенге за единицу</span>
          <span class="fx-delta">За год</span>
          <span></span>
        </div>
{body}
        <p class="fx-foot">Официальный курс Национального Банка РК на {as_of}.
          Нажмите на валюту, чтобы увидеть динамику.</p>
      </div>"""


def sources_rows(all_series: list[dict]) -> str:
    rows = []
    for s in sorted(all_series, key=lambda x: x["series_id"]):
        fetched = datetime.fromisoformat(s["fetched_at"]).strftime("%d.%m.%Y %H:%M UTC")
        status = "устарел" if s.get("stale") else "свежий"
        note = html.escape(s.get("note") or "")
        rows.append(
            f"<tr><td>{html.escape(s['name_ru'])}</td>"
            f"<td>{html.escape(s['source'])}</td>"
            f"<td class='num-cell'>{len(s['obs'])}</td>"
            f"<td class='num-cell'>{fmt_date(s['obs'][-1]['date'])}</td>"
            f"<td class='num-cell'>{fetched}</td>"
            f"<td>{status}{(': ' + note) if note else ''}</td></tr>"
        )
    return "\n".join(rows)


def digits_for(series_id: str) -> int:
    if series_id == "kz.fx.rub":
        return 2
    if series_id in ("kz.gdp.pc.usd", "kz.wage.avg"):
        return 0
    return 2


def build(data: dict) -> str:
    by_id = {s["series_id"]: s for s in data["series"]}
    generated = datetime.fromisoformat(data["generated_at"])

    fx_rows = [by_id[sid] for sid in FX_ORDER if sid in by_id]
    fx_as_of = fmt_date(fx_rows[0]["obs"][-1]["date"]) if fx_rows else ""
    fx_cards = fx_table(fx_rows, fx_as_of) if fx_rows else ""
    macro_cards = "\n".join(
        card(by_id[sid], digits_for(sid), "годом ранее", 365)
        for sid in MACRO_ORDER
        if sid in by_id
    )
    bns_cards = "\n".join(
        card(by_id[sid], digits_for(sid), "годом ранее", 365)
        for sid in BNS_ORDER
        if sid in by_id
    )
    issues = data.get("issues") or []
    issues_block = ""
    if issues:
        items = "".join(f"<li>{html.escape(i)}</li>" for i in issues)
        issues_block = (
            '<div class="notice" role="status"><p><strong>Часть рядов не обновилась '
            "в последнем прогоне.</strong> Показаны предыдущие значения.</p>"
            f"<ul>{items}</ul></div>"
        )

    return TEMPLATE.format(
        style=STYLE,
        generated_human=generated.strftime("%d.%m.%Y %H:%M UTC"),
        generated_iso=generated.isoformat(),
        fx_cards=fx_cards,
        macro_cards=macro_cards,
        bns_cards=bns_cards,
        issues_block=issues_block,
        sources_rows=sources_rows(data["series"]),
        year=date.today().year,
    )


STYLE = """
:root {
  --bg: #F5F0E8;
  --fg: #2C2420;
  --card: #FFFFFF;
  --muted: #E8DFD0;
  --muted-fg: #6E6256;
  --accent: #C0603D;
  --line: #9B8E82;
  --up: #2F6B4F;
  --down: #A03A2A;
  --sp: 1rem;
  --radius: 10px;
  --dur-in: 200ms;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: "Golos Text", ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
  font-size: 16px;
  line-height: 1.55;
  font-variant-numeric: tabular-nums;
}
.wrap { max-width: 1120px; margin-inline: auto; padding-inline: clamp(1rem, 4vw, 2.5rem); }
header.top { padding-block: clamp(2rem, 6vw, 3.5rem) 1.5rem; }
h1 { font-size: clamp(1.75rem, 4vw, 2.5rem); line-height: 1.15; margin: 0 0 0.5rem; }
.lede { max-width: 60ch; color: var(--muted-fg); margin: 0 0 0.75rem; }
.updated { font-size: 0.875rem; color: var(--muted-fg); margin: 0; }
h2 { font-size: 1.25rem; margin: 2.5rem 0 1rem; }
.fx { background: var(--card); border: 1px solid var(--muted); border-radius: var(--radius); overflow: hidden; }
.fx-head, .fx-row summary { display: grid; grid-template-columns: 1fr auto auto 1.5rem;
  gap: 0.75rem; align-items: center; padding: 0.6rem 1rem; }
.fx-head { font-size: 0.75rem; color: var(--muted-fg); border-bottom: 1px solid var(--muted); }
/* Общее правило для details писалось под раскрывающийся блок с оговорками:
   рамка, скругление и внешний отступ. В таблице курсов строка не карточка. */
.fx-row { margin: 0; border: 0; border-bottom: 1px solid var(--muted); border-radius: 0;
  background: transparent; }
.fx-head .fx-rate, .fx-head .fx-delta { font-family: inherit; font-size: 0.75rem; }
.fx-row summary { cursor: pointer; list-style: none; transition: background var(--dur-in) var(--ease-out); }
.fx-row summary::-webkit-details-marker { display: none; }
.fx-row summary:hover { background: var(--bg); }
.fx-row summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.fx-code { font-weight: 600; }
.fx-rate, .fx-delta { font-family: "JetBrains Mono", ui-monospace, monospace; text-align: right;
  white-space: nowrap; }
.fx-rate { font-size: 1.0625rem; }
.fx-delta { font-size: 0.8125rem; }
.fx-arrow { margin-inline-end: 0.25rem; font-size: 0.6875rem; }
.fx-up { color: var(--up); }
.fx-down { color: var(--down); }
.fx-flat { color: var(--muted-fg); }
.fx-hint::after { content: ""; display: block; width: 7px; height: 7px; border-right: 2px solid var(--line);
  border-bottom: 2px solid var(--line); transform: rotate(-45deg); margin-inline-start: 2px;
  transition: transform var(--dur-in) var(--ease-out); }
.fx-row[open] .fx-hint::after { transform: rotate(45deg); }
.fx-chart { padding: 0 1rem 0.9rem; animation: fx-reveal 220ms var(--ease-out); }
.fx-foot { margin: 0; padding: 0.7rem 1rem; font-size: 0.75rem; color: var(--muted-fg); }
@keyframes fx-reveal { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }

.section-note { max-width: 70ch; color: var(--muted-fg); font-size: 0.875rem; margin: -0.5rem 0 1rem; }
.grid { display: grid; gap: var(--sp); grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }
.card {
  background: var(--card);
  border: 1px solid var(--muted);
  border-radius: var(--radius);
  padding: 1.1rem 1.15rem 0.9rem;
  display: flex; flex-direction: column; gap: 0.35rem;
  transition: transform var(--dur-in) var(--ease-out), border-color var(--dur-in) var(--ease-out);
}
.card:hover { transform: translateY(-2px); border-color: var(--line); }
.card-head { display: flex; align-items: start; justify-content: space-between; gap: 0.5rem; }
.card h3 { font-size: 0.9375rem; font-weight: 600; margin: 0; color: var(--muted-fg); }
.badge { font-size: 0.6875rem; padding: 0.1rem 0.45rem; border-radius: 999px; white-space: nowrap; }
.badge-fresh { background: var(--muted); color: var(--muted-fg); }
.badge-stale { background: #F6E2DC; color: var(--down); }
.value { margin: 0.2rem 0 0; display: flex; align-items: baseline; gap: 0.4rem; flex-wrap: wrap; }
.num {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 1.75rem; font-weight: 500; letter-spacing: -0.01em;
}
.unit { font-size: 0.8125rem; color: var(--muted-fg); }
.delta { margin: 0; font-size: 0.8125rem; }
.delta-value { font-family: "JetBrains Mono", ui-monospace, monospace; font-weight: 500; }
.delta-up .delta-value { color: var(--up); }
.delta-down .delta-value { color: var(--down); }
.delta-note, .delta-none { color: var(--muted-fg); }
.spark { width: 100%; height: 64px; margin-top: 0.4rem; display: block; }
.spark-empty text { fill: var(--muted-fg); font-size: 12px; }
.spark-line { fill: none; stroke: var(--accent); stroke-width: 1.75; vector-effect: non-scaling-stroke;
  stroke-linejoin: round; stroke-linecap: round; }
.spark-area { fill: var(--accent); opacity: 0.08; }
.asof { margin: 0.15rem 0 0; font-size: 0.75rem; color: var(--muted-fg); }
.notice {
  background: #F6E2DC; border: 1px solid var(--down); border-radius: var(--radius);
  padding: 0.9rem 1.1rem; margin-block: 1.5rem;
}
.notice p { margin: 0 0 0.4rem; }
.notice ul { margin: 0; padding-inline-start: 1.2rem; font-size: 0.875rem; }
.table-wrap { overflow-x: auto; border: 1px solid var(--muted); border-radius: var(--radius); background: var(--card); }
table { border-collapse: collapse; width: 100%; font-size: 0.875rem; min-width: 640px; }
th, td { text-align: left; padding: 0.6rem 0.8rem; border-bottom: 1px solid var(--muted); vertical-align: top; }
thead th { position: sticky; top: 0; background: var(--card); font-weight: 600; color: var(--muted-fg); }
tbody tr:last-child td { border-bottom: 0; }
.num-cell { font-family: "JetBrains Mono", ui-monospace, monospace; text-align: right; white-space: nowrap; }
details { margin-block: 1.5rem; border: 1px solid var(--muted); border-radius: var(--radius); background: var(--card); }
summary { cursor: pointer; padding: 0.8rem 1rem; font-weight: 600; }
summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
details[open] summary { border-bottom: 1px solid var(--muted); }
.details-body { padding: 0.9rem 1rem; }
.details-body ul { margin: 0; padding-inline-start: 1.2rem; }
.details-body li { margin-bottom: 0.4rem; }
a { color: var(--accent); }
footer { padding-block: 2rem 3rem; font-size: 0.8125rem; color: var(--muted-fg); }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { transition-duration: 1ms !important; animation-duration: 1ms !important; }
  .card:hover { transform: none; }
}
@media print {
  body { background: #fff; }
  .card, .table-wrap, details { break-inside: avoid; border-color: #ccc; }
  thead th { position: static; }
  a::after { content: " (" attr(href) ")"; font-size: 0.75em; }
  details { break-inside: avoid; }
  details:not([open]) > summary::after { content: " (раздел свёрнут в печатной версии)"; font-weight: 400; }
}
"""


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Макро-пульс Казахстана</title>
<style>{style}</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>Макро-пульс Казахстана</h1>
    <p class="lede">Ключевые макропоказатели и официальные курсы валют, собранные
      автоматически из первоисточников. Каждая цифра подписана источником и датой.</p>
    <p class="updated">Обновлено <time datetime="{generated_iso}">{generated_human}</time></p>
  </header>

  {issues_block}

  <main>
    <h2>Официальные курсы валют</h2>
    <div class="grid">
{fx_cards}
    </div>

    <h2>Экономика</h2>
    <div class="grid">
{macro_cards}
    </div>

    <h2>Данные Бюро национальной статистики</h2>
    <p class="section-note">Национальный источник, в тенге и людях. Значения свежее, чем
      у международной базы, но приходят округлёнными до целых, поэтому проценты на этой
      странице взяты из международной базы, а не из БНС.</p>
    <div class="grid">
{bns_cards}
    </div>

    <h2>Источники и свежесть данных</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th scope="col">Показатель</th><th scope="col">Источник</th>
            <th scope="col">Точек</th><th scope="col">Последняя</th>
            <th scope="col">Забрано</th><th scope="col">Статус</th></tr>
        </thead>
        <tbody>
{sources_rows}
        </tbody>
      </table>
    </div>

    <details>
      <summary>Как читать эти цифры</summary>
      <div class="details-body">
        <ul>
          <li>Курсы валют официальные, по данным Национального Банка РК на первое число
            каждого месяца и на дату сборки. Это не среднемесячный курс и не биржевой курс KASE.</li>
          <li>Годовые показатели приходят из базы World Bank, поэтому последний доступный год
            отстаёт от текущего примерно на год. Это лаг источника, а не ошибка сборки.</li>
          <li>Инфляция это индекс потребительских цен год к году по методологии World Bank.
            Оценка Бюро национальной статистики за тот же период может отличаться.</li>
          <li>Показаны последние 20 лет. Гиперинфляция девяностых в окно не входит намеренно:
            она сжимает свежие годы в плоскую линию.</li>
          <li>График показывает форму движения, ось значений растянута по размаху ряда
            и не начинается от нуля.</li>
          <li>Численность населения приведена дважды и цифры не совпадают: у БНС это
            среднегодовая численность, у международной базы оценка на середину года.
            Расхождение около полумиллиона человек это разница методик, а не ошибка.</li>
          <li>ВВП тоже приведён дважды: в тенге по данным БНС и в долларах по данным
            международной базы. Пересчёт по курсу между ними не сойдётся, потому что
            долларовая оценка считается по среднегодовому курсу своей методики.</li>
          <li>Данные БНС приходят из Талдау округлёнными до целых. Для тенге и людей это
            незаметно, поэтому проценты сюда не берутся: уровень безработицы там
            превращается в «5», а индекс цен в «101».</li>
          <li>Если ряд не удалось обновить, показывается прошлое значение с пометкой
            «данные устарели», а не пустой график.</li>
        </ul>
      </div>
    </details>
  </main>

  <footer>
    <p>Служебная страница JB Solutions. Данные собираются автоматически из открытых
      источников и приводятся без гарантии пригодности для конкретного решения.
      Для расчётов и отчётности сверяйтесь с первоисточником.</p>
    <p>&copy; {year} JB Solutions</p>
  </footer>
</div>
</body>
</html>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else DATASET
    data = json.loads(dataset.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data), encoding="utf-8")
    print(f"Страница собрана: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
