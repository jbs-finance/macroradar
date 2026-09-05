"""Статическая страница jbs.finance/macroradar/national-fund/."""

from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime
from pathlib import Path

from build_pulse import STYLE, fmt_num, spark
from layout import CTA_STYLE, HEADER_STYLE, cta_block, meta_tags, site_header

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "national_fund.json"
DEFAULT_OUT = HERE / "out" / "national_fund.html"

FUND_STYLE = """
.fund-hero { padding-block: clamp(2.5rem, 7vw, 5rem) 2rem; max-width: 760px; }
.fund-hero h1 { max-width: 12ch; font-family: Georgia, "Times New Roman", serif; font-size: clamp(2.5rem, 6vw, 4.8rem); letter-spacing: -0.045em; line-height: 0.98; }
.fund-hero .lede { max-width: 58ch; font-size: 1.1rem; line-height: 1.55; }
.fund-summary { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 1px; margin-bottom: 3rem; background: var(--muted); border: 1px solid var(--muted); }
.fund-stat { padding: clamp(1rem, 2.4vw, 1.65rem); background: var(--card); }
.fund-stat .label { margin: 0 0 0.65rem; color: var(--muted-fg); font-size: 0.8rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; }
.fund-stat .number { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.65rem, 3.4vw, 2.8rem); letter-spacing: -0.035em; line-height: 1; }
.fund-stat .note { margin: 0.65rem 0 0; color: var(--muted-fg); font-size: 0.85rem; }
.fund-stat--main { background: #273C37; color: #F6F0E7; }
.fund-stat--main .label, .fund-stat--main .note { color: #D7DDD3; }
.fund-chart { padding: clamp(1.15rem, 3vw, 2rem); margin: 1.5rem 0 3rem; background: #EDE4D5; border-top: 3px solid #2F6B4F; }
.fund-chart h2 { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.55rem, 3vw, 2.15rem); letter-spacing: -0.025em; }
.fund-chart .section-note { margin: 0.5rem 0 1.1rem; }
.fund-chart .spark { width: 100%; height: 145px; color: #2F6B4F; }
.fund-chart .spark-line { stroke: currentColor; stroke-width: 2.5; fill: none; }
.fund-chart .spark-area { fill: rgba(47, 107, 79, 0.13); }
.years { display: flex; justify-content: space-between; gap: 0.5rem; color: var(--muted-fg); font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 0.75rem; }
.availability { display: grid; grid-template-columns: 0.8fr 1.2fr; gap: clamp(1rem, 3vw, 2rem); align-items: start; padding: clamp(1.25rem, 3vw, 2rem); margin: 3rem 0; border: 1px solid var(--muted); }
.availability h2 { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: 1.8rem; line-height: 1.05; }
.availability dl { margin: 0; display: grid; gap: 1rem; }
.availability dt { font-weight: 700; }
.availability dd { margin: 0.2rem 0 0; color: var(--muted-fg); line-height: 1.45; }
.year-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.year-table th, .year-table td { padding: 0.7rem 0.5rem; border-bottom: 1px solid var(--muted); text-align: right; }
.year-table th:first-child, .year-table td:first-child { padding-left: 0; text-align: left; }
.year-table th { color: var(--muted-fg); font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
.year-table .negative { color: #A8522F; } .year-table .positive { color: #2F6B4F; }
@media (max-width: 640px) { .fund-summary, .availability { grid-template-columns: 1fr; } .fund-chart { margin-inline: -0.35rem; } }
"""


def annual_assets(points: list[dict]) -> list[dict]:
    """Последняя месячная точка каждого года, без искусственной агрегации."""
    by_year = {}
    for point in points:
        by_year[point["date"][:4]] = point
    return list(by_year.values())


def change(points: list[dict], months: int) -> float | None:
    if len(points) <= months:
        return None
    base = points[-1 - months]["value"]
    return (points[-1]["value"] / base - 1) * 100 if base else None


def signed(value: float | None) -> str:
    if value is None:
        return "нет сопоставимой базы"
    return f"{'+' if value > 0 else ''}{fmt_num(value, 1)}%"


def count_text(value: int, forms: tuple[str, str, str]) -> str:
    """Русское склонение небольших счётчиков на публичной странице."""
    tail = value % 100
    if 11 <= tail <= 14:
        form = forms[2]
    elif value % 10 == 1:
        form = forms[0]
    elif 2 <= value % 10 <= 4:
        form = forms[1]
    else:
        form = forms[2]
    return f"{value} {form}"


def table_rows(assets: list[dict], returns: list[dict]) -> str:
    returns_by_year = {point["date"]: point["value"] for point in returns}
    rows = []
    for point in reversed(annual_assets(assets)):
        yearly_return = returns_by_year.get(point["date"][:4])
        tone = "positive" if (yearly_return or 0) > 0 else "negative" if yearly_return is not None else ""
        rendered_return = "нет данных" if yearly_return is None else signed(yearly_return)
        rows.append(
            f"<tr><td>{html.escape(point['date'][:4])}</td>"
            f"<td>{fmt_num(point['value'], 2)}</td>"
            f"<td class=\"{tone}\">{rendered_return}</td></tr>"
        )
    return "\n".join(rows)


def build(data: dict) -> str:
    assets = data["assets"]
    returns = data["returns"]
    latest_assets = assets[-1]
    latest_return = returns[-1]
    annual = annual_assets(assets)
    issues = data.get("issues") or []
    issue_block = ""
    if issues:
        issue_block = '<div class="notice" role="status"><p><strong>Часть данных не обновилась.</strong> Показан сохранённый срез.</p><ul>' + "".join(f"<li>{html.escape(item)}</li>" for item in issues) + "</ul></div>"
    return TEMPLATE.format(
        meta=meta_tags(
            "Нацфонд Казахстана: активы и доходность за 10 лет",
            "Ежемесячные валютные активы Национального фонда РК и ежегодная доходность по данным НБРК.",
            "/macroradar/national-fund/",
        ),
        header=site_header("fund"),
        style=STYLE + HEADER_STYLE + CTA_STYLE + FUND_STYLE,
        generated=datetime.fromisoformat(data["generated_at"]).strftime("%d.%m.%Y %H:%M UTC"),
        asset_value=fmt_num(latest_assets["value"], 2),
        asset_date=html.escape(latest_assets["date"]),
        annual_change=signed(change(assets, 12)),
        return_value=signed(latest_return["value"]),
        return_date=html.escape(latest_return["date"]),
        spark=spark(annual, width=900, height=145),
        first_year=annual[0]["date"][:4],
        last_year=annual[-1]["date"][:4],
        asset_count=count_text(len(assets), ("точка", "точки", "точек")),
        asset_start=html.escape(assets[0]["date"]),
        return_count=count_text(len(returns), ("наблюдение", "наблюдения", "наблюдений")),
        return_start=html.escape(returns[0]["date"]),
        return_end=html.escape(returns[-1]["date"]),
        rows=table_rows(assets, returns),
        asset_source=html.escape(data["assets_source"], quote=True),
        return_source=html.escape(data["returns_source"], quote=True),
        issue_block=issue_block,
        cta=cta_block(),
        year=date.today().year,
    )


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}
<title>Нацфонд Казахстана: радар</title>
<style>{style}</style>
</head>
<body>
{header}
<div class="wrap">
  <header class="fund-hero">
    <h1>Нацфонд Казахстана</h1>
    <p class="lede">Размер валютных активов и результат их управления. Здесь только сопоставимые ряды НБРК с названным покрытием, без подмены активов бюджетными потоками.</p>
    <p class="updated">Собрано {generated}</p>
  </header>
{issue_block}
  <main>
    <section class="fund-summary" aria-label="Ключевые показатели Национального фонда">
      <article class="fund-stat fund-stat--main"><p class="label">Валютные активы</p><p class="number">{asset_value}</p><p class="note">млрд USD, на конец {asset_date}</p></article>
      <article class="fund-stat"><p class="label">Изменение за 12 месяцев</p><p class="number">{annual_change}</p><p class="note">по ежемесячному ряду валютных активов</p></article>
      <article class="fund-stat"><p class="label">Доходность</p><p class="number">{return_value}</p><p class="note">за {return_date} год, не доход бюджета</p></article>
    </section>

    <section class="fund-chart" aria-labelledby="assets-title">
      <h2 id="assets-title">Валютные активы: 10 лет</h2>
      <p class="section-note">Последняя доступная точка каждого года, млрд USD. Полный месячный ряд собирается из первичного JSON НБРК.</p>
      {spark}
      <div class="years"><span>{first_year}</span><span>{last_year}</span></div>
    </section>

    <section class="availability" aria-labelledby="availability-title">
      <h2 id="availability-title">Доступность данных</h2>
      <dl>
        <div><dt>Валютные активы: доступны</dt><dd>НБРК публикует месячный JSON. В радаре {asset_count} с {asset_start} до последней публикации.</dd></div>
        <div><dt>Доходность: доступна</dt><dd>НБРК обновляет годовую таблицу. В радаре {return_count} за {return_start}-{return_end} годы.</dd></div>
        <div><dt>Операции и трансферты: пока не включены</dt><dd>НБРК публикует свежие операции ежемесячно, но нет единого машиночитаемого ряда на 10 лет. Сводить архивные таблицы без отдельной сверки было бы недостоверно.</dd></div>
      </dl>
    </section>

    <section aria-labelledby="history-title">
      <h2 id="history-title">Годовые точки</h2>
      <p class="section-note">Активы: последняя опубликованная месяцем точка года. Доходность: отдельный годовой ряд НБРК.</p>
      <table class="year-table"><thead><tr><th>Год</th><th>Активы, млрд USD</th><th>Доходность</th></tr></thead><tbody>{rows}</tbody></table>
    </section>

    <details><summary>Что важно при сравнении</summary><div class="details-body"><ul>
      <li>Валютные активы показаны в USD, на конец периода. Это не активы в тенге и не сумма годовых поступлений в бюджет.</li>
      <li>С 1 февраля 2024 года НБРК отражает валютные активы за вычетом обязательств по целевым требованиям программы «Нацфонд-детям». Сравнение с ранними периодами требует этой оговорки.</li>
      <li>Доходность отражает управление валютными активами. Она не равна поступлениям от нефтяного сектора или трансфертам в бюджет.</li>
    </ul></div></details>
    <p class="section-note">Источники: <a href="{asset_source}">НБРК, валютные активы</a> и <a href="{return_source}">НБРК, доходность активов</a>.</p>
{cta}
  </main>
  <footer><p>Служебная страница JB Solutions. Данные из открытых источников, не инвестиционная рекомендация.</p><p>&copy; {year} JB Solutions</p></footer>
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
    print(f"Страница Нацфонда собрана: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
