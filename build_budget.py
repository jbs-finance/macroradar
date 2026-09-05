"""Сборка страницы jbs.finance/macroradar/budget/ из out/minfin.json и out/budget.json.

Дашборд поступлений: сколько собрано, как исполняется план, кто платит по регионам.
Норма налогов живёт отдельно, на странице ставок: справочник читают, чтобы посчитать
налог, а дашборд смотрят, чтобы понять, что происходит с бюджетом. Смешивать эти два
режима чтения на одной странице значит мешать обоим.

Запуск: .venv/bin/python build_budget.py [вывод.html] [minfin.json] [budget.json]
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from budget_block import BUDGET_STYLE, budget_section
from build_pulse import STYLE
from compare_block import COMPARE_STYLE
from layout import (
    CTA_STYLE,
    HEADER_STYLE,
    cta_block,
    dataset_jsonld,
    meta_tags,
    site_header,
)
from minfin_block import (
    LEVELS_STYLE,
    MINFIN_STYLE,
    OBLAST_STYLE,
    minfin_section,
    period_label,
)

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "out" / "budget.html"
MINFIN = HERE / "out" / "minfin.json"
OBLAST = HERE / "out" / "oblast.json"
BUDGET = HERE / "out" / "budget.json"

BUDGET_PAGE_STYLE = """
.cross { background: var(--muted); border-radius: var(--radius); padding: 0.9rem 1.15rem;
  margin-block: 1.5rem; font-size: 0.875rem; }
.cross p { margin: 0; }
.cross a { color: var(--accent); }
"""


def headline(minfin: dict | None) -> str:
    latest = (minfin or {}).get("latest")
    if not latest:
        return "Бюджет Казахстана"
    return f"Бюджет Казахстана: {period_label(latest['year'], latest['months'])}"


def page_jsonld(minfin: dict | None, budget: dict | None, generated: datetime) -> str:
    sources, parts = [], []
    if minfin and minfin.get("latest"):
        sources.append("Министерство финансов РК")
        parts.append(
            f"исполнение государственного бюджета за {minfin['latest']['period']} "
            "с планом и фактом по видам налогов"
        )
    if budget and budget.get("dynamics"):
        sources.append("Комитет государственных доходов МФ РК")
        parts.append(
            f"помесячные поступления по областям за {budget['dynamics']['year']} год"
        )
    if not sources:
        return ""
    return dataset_jsonld(
        generated.isoformat(),
        sources,
        name="Поступления налогов в бюджет Казахстана",
        description="Налоговые поступления Казахстана: " + ", ".join(parts) + ".",
        path="/macroradar/budget/",
    )


def build(
    minfin: dict | None = None,
    budget: dict | None = None,
    oblast: dict | None = None,
) -> str:
    generated = datetime.now()
    if minfin and oblast:
        minfin = {**minfin, "oblast": oblast}
    regions_html, drill_rules = budget_section(budget) if budget else ("", "")
    latest = (minfin or {}).get("latest")
    period = (
        period_label(latest["year"], latest["months"]) if latest else "последний период"
    )
    return TEMPLATE.format(
        meta=meta_tags(
            "Бюджет Казахстана: сколько собрано налогов и как исполняется план",
            "Налоговые поступления в бюджет Казахстана помесячно: факт против плана, "
            "исполнение по видам налогов, разбивка по регионам и уровням бюджета. "
            "Данные Минфина и Комитета госдоходов, обновляются ежедневно.",
            "/macroradar/budget/",
        )
        + page_jsonld(minfin, budget, generated),
        header=site_header("budget"),
        cta=cta_block(),
        style=STYLE
        + HEADER_STYLE
        + CTA_STYLE
        + MINFIN_STYLE
        + LEVELS_STYLE
        + OBLAST_STYLE
        + BUDGET_STYLE
        + COMPARE_STYLE
        + BUDGET_PAGE_STYLE
        + drill_rules,
        title=headline(minfin),
        period=period,
        minfin=minfin_section(minfin),
        regions=regions_html,
        generated_human=generated.strftime("%d.%m.%Y %H:%M"),
        generated_iso=generated.isoformat(timespec="seconds"),
        current_year=date.today().year,
    )


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}
<title>{title}</title>
<style>{style}</style>
</head>
<body>
{header}
<div class="wrap">
  <header class="top">
    <h1>{title}</h1>
    <p class="lede">Сколько налогов собрано, насколько это совпало с планом и кто
      платит. Цифры страны из ежемесячных отчётов Министерства финансов, разбивка
      по областям из данных Комитета государственных доходов.</p>
    <p class="updated">Страница собрана
      <time datetime="{generated_iso}">{generated_human}</time></p>
  </header>

  <main>
{minfin}

{regions}

    <div class="cross">
      <p>Ставки, пороги и сроки уплаты собраны отдельно, в
        <a href="/macroradar/tax/">справочнике налогов</a>: там норма, здесь факт.</p>
    </div>
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
    minfin_path = Path(sys.argv[2]) if len(sys.argv) > 2 else MINFIN
    budget_path = Path(sys.argv[3]) if len(sys.argv) > 3 else BUDGET
    oblast_path = Path(sys.argv[4]) if len(sys.argv) > 4 else OBLAST

    minfin = None
    if minfin_path.exists():
        minfin = json.loads(minfin_path.read_text(encoding="utf-8"))
        if not minfin.get("latest"):
            minfin = None
    budget = None
    if budget_path.exists():
        budget = json.loads(budget_path.read_text(encoding="utf-8"))
        if not budget.get("dynamics"):
            budget = None

    oblast = None
    if oblast_path.exists():
        oblast = json.loads(oblast_path.read_text(encoding="utf-8"))
        if not oblast.get("regions"):
            oblast = None

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(minfin, budget, oblast), encoding="utf-8")
    print(f"Страница собрана: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
