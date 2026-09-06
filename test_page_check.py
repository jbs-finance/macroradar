"""Гейт наполнения: страница может быть структурно целой и при этом пустой.

Регресс, который эти тесты обязаны ловить: вырезанный main, обнулённая секция,
схлопнувшаяся разбивка по регионам, нерезолвленный код страны в публикации,
протухшие или пропавшие выгрузки. Раньше всё это проезжало гейт с кодом 0 и
сообщением «страниц проверено: 6», а пользователь видел пустые блоки.

Здоровые страницы берутся из публикации public/macroradar: только там рядом с
HTML лежат JSON-выгрузки, а фикстуры собирают голую разметку.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from page_check import DATASETS, content_problems, parse_stamp, problems

HERE = Path(__file__).resolve().parent
LIVE = Path(
    os.environ.get(
        "MACRORADAR_PUBLIC",
        HERE.parent / "jbs-finance" / "public" / "macroradar",
    )
)

# Расхождения, которые на живых страницах уже есть и чинятся в данных, а не в
# гейте. Тесты следят, чтобы к ним не добавилось новых: список должен пустеть.
KNOWN: tuple[str, ...] = ()


def known(line: str) -> bool:
    return any(mark in line for mark in KNOWN)


@pytest.fixture
def live() -> Path:
    if not (LIVE / "index.html").exists():
        pytest.skip(f"нет публикации {LIVE}")
    return LIVE


@pytest.fixture
def sandbox(live: Path, tmp_path: Path) -> Path:
    """Копия публикации: ломать будем её, а не рабочий каталог."""
    base = tmp_path / "macroradar"
    shutil.copytree(live, base)
    return base


def moment(base: Path) -> datetime:
    """Момент проверки: час после самой свежей выгрузки.

    Иначе тест начнёт падать на пороге свежести через сутки после сборки.
    """
    stamps = []
    for relpath in DATASETS:
        path = base / relpath
        if path.exists():
            stamp = parse_stamp(
                str(json.loads(path.read_text(encoding="utf-8")).get("generated_at"))
            )
            if stamp:
                stamps.append(stamp)
    return max(stamps) + timedelta(hours=1)


def fresh(base: Path) -> list[str]:
    """Проблемы наполнения без уже известных расхождений в данных."""
    return [
        line for line in content_problems(base, now=moment(base)) if not known(line)
    ]


def read(base: Path, relpath: str) -> str:
    return (base / relpath).read_text(encoding="utf-8")


def write(base: Path, relpath: str, document: str) -> None:
    (base / relpath).write_text(document, encoding="utf-8")


def test_live_pages_pass_structural_gate(live: Path):
    assert problems(live) == []


def test_live_pages_have_no_unknown_content_problems(live: Path):
    assert fresh(live) == []


def test_live_content_problems_are_only_the_known_data_gaps(live: Path):
    for line in content_problems(live, now=moment(live)):
        assert known(line), line


def test_cut_main_is_caught(sandbox: Path):
    document = read(sandbox, "macro/index.html")
    cut = re.sub(r"<main>.*</main>", "", document, flags=re.S)
    assert cut != document
    write(sandbox, "macro/index.html", cut)
    found = fresh(sandbox)
    assert any("нет <main>" in line for line in found), found
    # Разметка при этом цела: старый гейт такую страницу пропускал.
    assert problems(sandbox) == []


def test_emptied_section_is_caught(sandbox: Path):
    document = read(sandbox, "macro/index.html")
    start = document.index('<h2 class="section" id="fx"')
    end = document.index("<h2", document.index(">", start))
    head = document[: document.index(">", start) + 1]
    write(sandbox, "macro/index.html", head + document[end:])
    found = fresh(sandbox)
    assert any("официальные курсы валют" in line for line in found), found


def test_sections_stripped_from_page_are_caught(sandbox: Path):
    document = read(sandbox, "national-fund/index.html")
    flat = re.sub(r"</?section[^>]*>", "", document)
    write(sandbox, "national-fund/index.html", flat)
    found = fresh(sandbox)
    assert any("ключевые показатели фонда" in line for line in found), found


def test_collapsed_regions_in_dump_are_caught(sandbox: Path):
    path = sandbox / "tax" / "budget.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["dynamics"]["regions"] = payload["dynamics"]["regions"][:3]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    found = fresh(sandbox)
    assert any("областей в разбивке КГД" in line for line in found), found


def test_collapsed_regions_on_page_are_caught(sandbox: Path):
    """Порог абсолютный: схлопывание разметки ловится при целой выгрузке."""
    document = read(sandbox, "budget/index.html")
    kept = 0

    def drop(match):
        nonlocal kept
        kept += 1
        return match.group(0) if kept <= 4 else ""

    thin = re.sub(r'<input[^>]*name="drill-region"[^>]*>', drop, document)
    write(sandbox, "budget/index.html", thin)
    found = fresh(sandbox)
    assert any("в разбивке КГД" in line for line in found), found


def test_unresolved_country_code_is_caught(sandbox: Path):
    document = read(sandbox, "tax/index.html")
    write(sandbox, "tax/index.html", document.replace("<h1>", "<h1>код 251 ", 1))
    found = content_problems(sandbox, now=moment(sandbox))
    assert any(
        line.startswith("tax/index.html") and "код страны без названия" in line
        for line in found
    ), found


def test_none_in_visible_text_is_caught(sandbox: Path):
    document = read(sandbox, "tax/index.html")
    write(sandbox, "tax/index.html", document.replace("<h1>", "<h1>None nan ", 1))
    found = fresh(sandbox)
    assert any("None" in line for line in found), found
    assert any("nan" in line for line in found), found


def test_missing_dumps_are_caught(sandbox: Path):
    for relpath in DATASETS:
        (sandbox / relpath).unlink()
    found = content_problems(sandbox, now=datetime.now(timezone.utc))
    for relpath in DATASETS:
        assert any(
            line.startswith(f"{relpath}: выгрузки нет") for line in found
        ), relpath


def test_stale_dumps_are_caught(live: Path):
    late = moment(live) + timedelta(days=3)
    found = [line for line in content_problems(live, now=late) if not known(line)]
    assert any("при пороге 24 ч" in line for line in found), found


def test_empty_chart_is_caught(sandbox: Path):
    document = read(sandbox, "national-fund/index.html")
    bare = re.sub(r"<(path|polyline|polygon|circle|rect|line)\b[^>]*/?>", "", document)
    write(sandbox, "national-fund/index.html", bare)
    found = fresh(sandbox)
    assert any("график без фигур" in line for line in found), found


def test_single_point_series_is_caught(sandbox: Path):
    document = read(sandbox, "macro/index.html")
    flat = re.sub(r'(<polyline[^>]*points=")[^"]*"', r'\g<1>0,0"', document, count=1)
    write(sandbox, "macro/index.html", flat)
    found = fresh(sandbox)
    assert any("точек в графике" in line for line in found), found


def test_empty_path_is_caught(sandbox: Path):
    document = read(sandbox, "national-fund/index.html")
    hollow = '<svg class="spark"><path d="M0 0"/></svg>'
    broken = document.replace("</main>", hollow + "</main>", 1)
    write(sandbox, "national-fund/index.html", broken)
    found = fresh(sandbox)
    assert any("пустая линия" in line for line in found), found


def test_table_without_data_rows_is_caught(sandbox: Path):
    document = read(sandbox, "tax/index.html")
    bare = re.sub(
        r"<tbody>.*?</tbody>", "<tbody></tbody>", document, count=1, flags=re.S
    )
    write(sandbox, "tax/index.html", bare)
    found = fresh(sandbox)
    assert any("таблица без строк" in line for line in found), found


def test_future_date_in_past_events_is_caught_and_curable(sandbox: Path):
    document = read(sandbox, "macro/index.html")
    events = document.index('id="events"')
    tail = document[events:]
    past = re.sub(r'datetime="20\d\d-\d\d-\d\d"', 'datetime="2020-01-01"', tail)
    fixed = document[:events] + past
    write(sandbox, "macro/index.html", fixed)
    lines = content_problems(sandbox, now=moment(sandbox))
    assert not any("дата из будущего" in line for line in lines), lines

    # Решение по ставке объявляют заранее, поэтому его дата помечена data-upcoming
    # и от проверки освобождена. Подставляется именно непомеченная дата.
    ahead = document[:events] + re.sub(
        r'datetime="20\d\d-\d\d-\d\d"( data-upcoming)?',
        'datetime="2030-01-01"',
        tail,
        count=1,
    )
    write(sandbox, "macro/index.html", ahead)
    lines = content_problems(sandbox, now=moment(sandbox))
    assert any("дата из будущего" in line for line in lines), lines


def test_caption_against_fact_is_caught(sandbox: Path):
    document = read(sandbox, "budget/index.html")
    assert "12 регионов из двадцати" in document
    lie = document.replace("12 регионов из двадцати", "40 регионов из двадцати")
    write(sandbox, "budget/index.html", lie)
    lines = content_problems(sandbox, now=moment(sandbox))
    found = [line for line in lines if "спорят" not in line]
    assert any("больше целого" in line for line in found), found


def test_shrunken_breakdown_under_caption_is_caught(sandbox: Path):
    """Подпись обещает 12 областей, а строк осталось три."""
    document = read(sandbox, "budget/index.html")
    start = document.index('<div class="obl-row">')
    end = document.index('<p class="obl-legend">')
    rows = document[start:end].split('<div class="obl-row">')[1:]
    assert len(rows) >= 8
    kept = "".join('<div class="obl-row">' + row for row in rows[:3])
    short = document[:start] + kept + "</div>" + document[end:]
    write(sandbox, "budget/index.html", short)
    found = fresh(sandbox)
    assert any("подпись обещает" in line for line in found), found


def test_structural_checks_survive(sandbox: Path):
    document = read(sandbox, "tax/index.html")
    spoiled = document.replace('rel="canonical"', 'rel="author"')
    write(sandbox, "tax/index.html", spoiled)
    assert any("canonical" in line for line in problems(sandbox))


def test_content_problems_stay_out_of_the_structural_list(sandbox: Path):
    """Дефект наполнения виден только в своей категории: разметка при нём цела."""
    document = read(sandbox, "trade/index.html")
    write(sandbox, "trade/index.html", document.replace("Франция", "код 251"))
    assert problems(sandbox) == []
    assert any("код страны без названия" in line for line in content_problems(sandbox))


def test_cli_reports_both_categories_and_fails(sandbox: Path):
    document = read(sandbox, "macro/index.html")
    broken = re.sub(r"<main>.*</main>", "", document, flags=re.S)
    spoiled = broken.replace('rel="canonical"', 'rel="author"')
    write(sandbox, "macro/index.html", spoiled)
    run = subprocess.run(
        [sys.executable, str(HERE / "page_check.py"), str(sandbox)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "структура собрана неверно:" in run.stdout
    assert "наполнение неполное:" in run.stdout
    assert "нет <main>" in run.stdout
