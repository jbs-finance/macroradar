"""Сборка страницы jbs.finance/macroradar/trade/ из out/trade.json.

Оформление и карточки рядов переиспользуются из build_pulse: две страницы одного
сайта обязаны выглядеть одинаково, а не расходиться в две конвенции. Своё здесь
только то, чего нет на пульсе: рейтинг партнёров и товарных групп.

Запуск: .venv/bin/python build_trade.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from layout import CTA_STYLE, HEADER_STYLE, cta_block, meta_tags, site_header
from build_pulse import STYLE, card, fmt_num

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "trade.json"
DEFAULT_OUT = HERE / "out" / "trade.html"

FLOW_ORDER = ["kz.exports.usd", "kz.imports.usd", "kz.trade.balance"]
INVEST_ORDER = ["kz.fdi.usd", "kz.trade.openness"]
BREAKDOWN_ORDER = ["exports.partners", "imports.partners", "exports.commodities"]

RANKING_STYLE = """
.rank { background: var(--card); border: 1px solid var(--muted); border-radius: var(--radius);
  padding: 1.1rem 1.15rem 1rem; }
.rank h3 { font-size: 0.9375rem; font-weight: 600; margin: 0 0 0.15rem; color: var(--muted-fg); }
.rank .asof { margin: 0 0 0.8rem; }
.rank ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
.rank li { display: grid; grid-template-columns: 1fr auto; gap: 0.2rem 0.75rem; align-items: baseline; }
.rank .bar { grid-column: 1 / -1; height: 6px; border-radius: 3px; background: var(--muted); overflow: hidden; }
.rank .bar span { display: block; height: 100%; background: var(--accent); border-radius: 3px;
  transform-origin: left center; }
.rank .label { font-size: 0.875rem; }
.rank .amount { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 0.875rem;
  white-space: nowrap; }
"""


def ranking(breakdown: dict) -> str:
    items = breakdown.get("items") or []
    top = max((i["value"] for i in items), default=1) or 1
    badge = (
        '<span class="badge badge-stale">данные устарели</span>'
        if breakdown.get("stale")
        else '<span class="badge badge-fresh">актуально</span>'
    )
    rows = "\n".join(
        f'          <li><span class="label">{html.escape(str(i["label"]))}</span>'
        f'<span class="amount">{fmt_num(i["value"], 2)}</span>'
        f'<span class="bar"><span style="width: {max(i["value"] / top * 100, 1):.1f}%"></span></span></li>'
        for i in items
    )
    return f"""      <article class="rank">
        <header class="card-head">
          <h3>{html.escape(breakdown["name_ru"])}</h3>
          {badge}
        </header>
        <p class="asof">{breakdown["year"]} год, {html.escape(breakdown["unit"])},
          источник: {html.escape(breakdown["source"])}</p>
        <ol>
{rows}
        </ol>
      </article>"""


def build(data: dict) -> str:
    by_id = {s["series_id"]: s for s in data["series"]}
    by_key = {b["id"]: b for b in data.get("breakdowns", [])}
    generated = datetime.fromisoformat(data["generated_at"])

    flow_cards = "\n".join(
        card(by_id[sid], 2, "годом ранее", 365) for sid in FLOW_ORDER if sid in by_id
    )
    invest_cards = "\n".join(
        card(by_id[sid], 2, "годом ранее", 365) for sid in INVEST_ORDER if sid in by_id
    )
    rankings = "\n".join(
        ranking(by_key[key]) for key in BREAKDOWN_ORDER if key in by_key
    )

    issues = data.get("issues") or []
    issues_block = ""
    if issues:
        items = "".join(f"<li>{html.escape(i)}</li>" for i in issues)
        issues_block = (
            '<div class="notice" role="status"><p><strong>Часть данных не обновилась '
            "в последнем прогоне.</strong> Показаны предыдущие значения.</p>"
            f"<ul>{items}</ul></div>"
        )

    return TEMPLATE.format(
        meta=meta_tags('Внешняя торговля Казахстана: экспорт, импорт, партнёры и товарные группы', 'Экспорт и импорт Казахстана, сальдо, прямые инвестиции и структура торговли по странам и товарным группам. Данные World Bank и UN Comtrade с автоматическим обновлением.', '/macroradar/trade/'),
        header=site_header('trade'),
        cta=cta_block(),
        style=STYLE + HEADER_STYLE + CTA_STYLE + RANKING_STYLE,
        generated_human=generated.strftime("%d.%m.%Y %H:%M UTC"),
        generated_iso=generated.isoformat(),
        flow_cards=flow_cards,
        invest_cards=invest_cards,
        rankings=rankings,
        issues_block=issues_block,
        year=date.today().year,
    )


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}
<title>Внешняя торговля Казахстана</title>
<style>{style}</style>
</head>
<body>
{header}
<div class="wrap">
  <header class="top">
    <h1>Внешняя торговля Казахстана</h1>
    <p class="lede">Объёмы торговли и прямые инвестиции, структура экспорта и импорта
      по странам и товарным группам. Каждая цифра подписана источником и годом.</p>
    <p class="updated">Обновлено <time datetime="{generated_iso}">{generated_human}</time></p>
  </header>

  {issues_block}

  <main>
    <h2>Товарооборот</h2>
    <div class="grid">
{flow_cards}
    </div>

    <h2>Инвестиции и открытость</h2>
    <div class="grid">
{invest_cards}
    </div>

    <h2>Структура торговли</h2>
    <p class="section-note">Первая десятка по стоимости. Данные таможенной статистики
      ООН, поэтому суммы по странам не совпадают с итогом выше: там торговля товарами,
      здесь товары и услуги по методологии платёжного баланса.</p>
    <div class="grid">
{rankings}
    </div>

    <details>
      <summary>Как читать эти цифры</summary>
      <div class="details-body">
        <ul>
          <li>Экспорт и импорт приведены по методологии платёжного баланса и включают
            услуги. Структура по странам и товарам считается по таможенной статистике,
            где услуг нет, поэтому суммы двух блоков сходиться не обязаны.</li>
          <li>Сальдо торгового баланса рассчитано как разница экспорта и импорта за те
            годы, где известны обе стороны. Это не официальная публикация, а расчёт.</li>
          <li>Прямые иностранные инвестиции показаны как чистый приток. Отрицательное
            значение означает, что вывод капитала превысил ввод, и это нормальная
            величина для отдельного года, а не ошибка.</li>
          <li>Структура торговли обновляется раз в неделю: открытый доступ к таможенной
            базе ООН ограничен по числу запросов, а годовые данные за неделю не меняются.</li>
          <li>Страны, для которых нет русского названия в справочнике, показаны кодом
            или английским именем. Выдумывать перевод хуже, чем показать код.</li>
        </ul>
      </div>
    </details>
{cta}
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
