"""Сборка страницы jbs.finance/macroradar/tax/ из out/tax.json.

Оформление берётся из build_pulse: страницы одного сайта не должны расходиться.
Своё здесь только таблица справочника и оговорки, без которых публиковать
налоговые ставки нельзя.

Запуск: .venv/bin/python build_tax.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from layout import CTA_STYLE, HEADER_STYLE, cta_block, meta_tags, site_header
from build_pulse import STYLE, fmt_date

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "tax.json"
DEFAULT_OUT = HERE / "out" / "tax.html"

TAX_STYLE = """
.tax-group { background: var(--card); border: 1px solid var(--muted); border-radius: var(--radius);
  overflow: hidden; margin-block: 1rem; }
.tax-group h3 { margin: 0; padding: 0.9rem 1rem 0.3rem; font-size: 1rem; }
.tax-note { margin: 0; padding: 0 1rem 0.8rem; font-size: 0.8125rem; color: var(--muted-fg);
  max-width: 70ch; }
/* Блок скругляет углы через overflow: hidden, поэтому широкая таблица иначе
   обрезалась бы по краю вместо прокрутки. Прокрутка живёт на своей обёртке. */
.tax-scroll { overflow-x: auto; }
.tax-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; min-width: 460px; }
.tax-table th { text-align: left; font-weight: 600; color: var(--muted-fg); font-size: 0.75rem;
  padding: 0.5rem 1rem; border-block: 1px solid var(--muted); }
.tax-table td { padding: 0.6rem 1rem; border-bottom: 1px solid var(--muted); vertical-align: top; }
.tax-table tr:last-child td { border-bottom: 0; }
.tax-value { font-family: "JetBrains Mono", ui-monospace, monospace; white-space: nowrap; }
.tax-was { color: var(--muted-fg); font-size: 0.8125rem; }
.tax-base { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }
.tax-base .card { gap: 0.15rem; }
.tax-base .num { font-size: 1.375rem; }
.cross { background: var(--muted); border-radius: var(--radius); padding: 0.9rem 1.15rem;
  margin-block: 1.5rem; font-size: 0.875rem; }
.cross p { margin: 0; }
.cross a { color: var(--accent); }
.disclaimer { background: var(--muted); border-radius: var(--radius); padding: 1rem 1.15rem;
  margin-block: 1.5rem; font-size: 0.875rem; }
.disclaimer p { margin: 0 0 0.5rem; }
.disclaimer p:last-child { margin-bottom: 0; }
"""


def base_cards(items: list[dict]) -> str:
    return "\n".join(
        f"""        <article class="card">
          <h3>{html.escape(item["name"])}</h3>
          <p class="value"><span class="num">{html.escape(item["value"])}</span></p>
          <p class="asof">основание: {html.escape(item["basis"])}</p>
        </article>"""
        for item in items
    )


def group_block(group: dict) -> str:
    rows = "\n".join(
        f"""            <tr><td>{html.escape(item["name"])}</td>"""
        f"""<td class="tax-value">{html.escape(item["value"])}</td>"""
        f"""<td class="tax-was">{html.escape(item.get("was") or "")}</td></tr>"""
        for item in group["items"]
    )
    note = (
        f'<p class="tax-note">{html.escape(group["note"])}</p>'
        if group.get("note")
        else ""
    )
    return f"""      <section class="tax-group" id="{html.escape(group["id"])}">
        <h3>{html.escape(group["title"])}</h3>
        {note}
        <div class="tax-scroll">
        <table class="tax-table">
          <thead>
            <tr><th scope="col">Показатель</th><th scope="col">Значение</th>
              <th scope="col">Что изменилось</th></tr>
          </thead>
          <tbody>
{rows}
          </tbody>
        </table>
        </div>
      </section>"""


def simple_table(title: str, items: list[dict], columns: tuple[str, str]) -> str:
    rows = "\n".join(
        f"""            <tr><td>{html.escape(i["name"])}</td>"""
        f"""<td class="tax-value">{html.escape(i["value"])}</td>"""
        + (
            f"""<td class="tax-was">{html.escape(i["effect"])}</td>"""
            if "effect" in i
            else ""
        )
        + "</tr>"
        for i in items
    )
    third = '<th scope="col">Последствие</th>' if items and "effect" in items[0] else ""
    return f"""      <section class="tax-group">
        <h3>{html.escape(title)}</h3>
        <div class="tax-scroll">
        <table class="tax-table">
          <thead><tr><th scope="col">{columns[0]}</th><th scope="col">{columns[1]}</th>{third}</tr></thead>
          <tbody>
{rows}
          </tbody>
        </table>
        </div>
      </section>"""


def build(data: dict) -> str:
    generated = datetime.fromisoformat(data["generated_at"])
    return TEMPLATE.format(
        meta=meta_tags(
            'Налоги Казахстана 2026: ставки, пороги и сроки по Налоговому кодексу',
            'Ставки НДС, КПН, ИПН, соцплатежей и спецрежимов на 2026 год с порогами '
            'в тенге и сроками отчётности. Справочник сверен с первоисточниками, '
            'дата сверки на странице.',
            '/macroradar/tax/',
        )
        ,
        header=site_header('tax'),
        cta=cta_block(),
        style=STYLE + HEADER_STYLE + CTA_STYLE + TAX_STYLE,
        year=data["year"],
        generated_human=generated.strftime("%d.%m.%Y %H:%M UTC"),
        generated_iso=generated.isoformat(),
        reviewed_human=fmt_date(data["reviewed_at"]),
        source=html.escape(data["source"]),
        base_cards=base_cards(data["base"]),
        groups="\n".join(group_block(g) for g in data["groups"]),
        calendar=simple_table(
            "Сроки отчётности и уплаты", data["calendar"], ("Налог или форма", "Срок")
        ),
        enforcement=simple_table(
            "Меры при налоговой задолженности",
            data["enforcement"],
            ("Размер долга", "Сумма"),
        ),
        current_year=date.today().year,
    )


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}
<title>Налоги Казахстана {year}</title>
<style>{style}</style>
</head>
<body>
{header}
<div class="wrap">
  <header class="top">
    <h1>Налоги Казахстана {year}</h1>
    <p class="lede">Ставки, пороги и сроки по действующему Налоговому кодексу.
      Величины, выраженные в МРП и МЗП, пересчитаны в тенге.</p>
    <p class="updated">Сверено с первоисточниками {reviewed_human}.
      Страница собрана <time datetime="{generated_iso}">{generated_human}</time></p>
  </header>

  <main>
    <h2>Базовые величины</h2>
    <div class="tax-base">
{base_cards}
    </div>

    <div class="cross">
      <p>Сколько этих налогов собрано на самом деле, как исполняется план и кто
        платит по регионам, показано в
        <a href="/macroradar/budget/">дашборде бюджета</a>.</p>
    </div>

    <h2>Ставки</h2>
{groups}

    <h2>Сроки и санкции</h2>
{calendar}
{enforcement}

    <div class="disclaimer">
      <p><strong>Это справочник, а не налоговая консультация.</strong> Он не заменяет
        расчёт по конкретной ситуации и не подтверждает позицию перед налоговым органом.
        Ответственность за поданную отчётность остаётся на налогоплательщике.</p>
      <p>Ставка зависит от вида деятельности, режима, статуса контрагента и даты операции.
        Перед применением сверяйтесь с первоисточником: {source}.</p>
      <p>Налоговый кодекс меняется в течение года. Дата сверки указана вверху страницы:
        если она давняя, считайте цифры устаревшими и проверьте норму заново.</p>
    </div>

    <details>
      <summary>Что здесь намеренно не показано</summary>
      <div class="details-body">
        <ul>
          <li>Отраслевые льготы и специальные территории (СЭЗ, МФЦА, Astana Hub):
            там свои режимы, и короткая строка в таблице ввела бы в заблуждение.</li>
          <li>Акцизы, недропользование, рента: они касаются узкого круга плательщиков
            и требуют отдельного разбора.</li>
          <li>Схемы снижения налога дроблением бизнеса или переквалификацией выплат.
            Такие варианты не приводятся.</li>
          <li>Расчёт зарплаты от суммы на руки: это не ставка, а модель, она зависит
            от вычетов и статуса работника.</li>
        </ul>
      </div>
    </details>
{cta}
  </main>

  <footer>
    <p>Служебная страница JB Solutions. Данные приводятся без гарантии пригодности
      для конкретного решения.</p>
    <p>&copy; {current_year} JB Solutions</p>
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
