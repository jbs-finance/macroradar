"""Сборка страницы здравоохранения по областям из out/health.json.

Разметка та же, что у /macroradar/industry/: таблица область, значение, год,
свежесть на каждый показатель. Рендер секции переиспользуется из build_industry.

Запуск: .venv/bin/python build_health.py [путь_вывода.html] [путь_данных.json]
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from build_industry import INDUSTRY_STYLE, indicator_section
from build_pulse import STYLE
from health import HEALTH_SERIES
from layout import (
    ACCESSIBILITY_STYLE,
    CTA_STYLE,
    HEADER_STYLE,
    NO_DATA_STYLE,
    cta_block,
    detail_footer,
    issues_notice,
    meta_tags,
    no_data,
    site_header,
    skip_link,
)

HERE = Path(__file__).resolve().parent
DATASET = HERE / "out" / "health.json"
DEFAULT_OUT = HERE / "out" / "health.html"


def build(data: dict) -> str:
    by_id = {item.get("series_id"): item for item in data.get("series", [])}
    sections = "\n".join(
        indicator_section(spec, by_id, prefix="kz.health") for spec in HEALTH_SERIES
    )
    if not by_id:
        sections = no_data("ряды здравоохранения не собраны")
    generated = datetime.fromisoformat(data["generated_at"])
    return TEMPLATE.format(
        meta=meta_tags(
            "Здравоохранение Казахстана по областям: койки и врачи",
            "Больничные койки и врачи на 10 000 населения по двадцати областям Казахстана, данные Минздрава в БНС.",
            "/macroradar/health/",
        ),
        style=STYLE
        + HEADER_STYLE
        + ACCESSIBILITY_STYLE
        + CTA_STYLE
        + NO_DATA_STYLE
        + INDUSTRY_STYLE,
        header=site_header("health"),
        skip_link=skip_link(),
        generated=generated.strftime("%d.%m.%Y %H:%M UTC"),
        generated_iso=generated.isoformat(),
        issues=issues_notice(data.get("issues")),
        sections=sections,
        cta=cta_block(),
        footer=detail_footer(date.today().year),
    )


TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{meta}<title>Здравоохранение Казахстана по областям</title><style>{style}</style></head><body>
{skip_link}{header}<div class="wrap"><header class="industry-hero"><h1>Здравоохранение по областям</h1>
<p class="lede">Административные данные Минздрава, которые Бюро национальной статистики публикует по
областям. Последний доступный год 2023: источник выходит с лагом около двух лет, бейдж в каждой строке
показывает возраст данных. Показатели рассчитаны на 10 000 жителей, поэтому области сравнимы между собой
без поправки на численность.</p>
<p class="updated">Собрано <time datetime="{generated_iso}">{generated}</time></p></header>{issues}
<main id="main-content">{sections}{cta}</main>{footer}</div></body></html>"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build(json.loads(dataset.read_text(encoding="utf-8"))), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
