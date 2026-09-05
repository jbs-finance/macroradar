"""Данные Национального фонда РК: валютные активы и доходность НБРК.

Валютные активы НБРК отдаёт помесячно через интерфейс своей статистической
страницы. Доходность публикуется отдельной годовой HTML-таблицей. Ряды не
смешиваются: первый показывает размер фонда в USD, второй результат управления
валютными активами в процентах.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
from datetime import date
from pathlib import Path

from etl import RAW, SourceError, _now, fetch

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / "out" / "national_fund.json"
ASSETS_PAGE = (
    "https://nationalbank.kz/ru/international-reserve-and-asset/"
    "mezhdunarodnye-rezervy-i-aktivy-nacionalnogo-fonda-rk"
)
ASSETS_RECORDS_URL = f"{ASSETS_PAGE}/records"
RETURNS_URL = "https://nationalbank.kz/ru/page/NF-investment-management"
HISTORY_YEARS = 10
ASSET_FIELD = "national_fund_republic_of_kazakhstan_volume_million_dollar"


def _plain(markup: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()


def history_start(last_stamp: str) -> str:
    """Начало десятилетнего окна от последней доступной месячной точки."""
    return f"{int(last_stamp[:4]) - HISTORY_YEARS}-{last_stamp[5:7]}"


def parse_assets(payload: object, today: date) -> list[dict]:
    """Проверяет контракт JSON НБРК и нормализует USD млн в USD млрд."""
    if not isinstance(payload, list):
        raise SourceError("НБРК: ответ активов не является списком")
    points: dict[str, float] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        stamp = str(row.get("reporting_date") or "")[:7]
        raw_value = row.get(ASSET_FIELD)
        if not re.fullmatch(r"\d{4}-\d{2}", stamp) or raw_value is None:
            continue
        try:
            value = float(raw_value) / 1000
        except (TypeError, ValueError):
            continue
        if not 1 <= value <= 300:
            raise SourceError(f"НБРК: активы {value:.2f} млрд USD вне ожидаемого диапазона")
        points[stamp] = value
    eligible = [
        (stamp, value)
        for stamp, value in sorted(points.items())
        if stamp <= today.strftime("%Y-%m")
    ]
    if not eligible:
        raise SourceError("НБРК: нет точек до текущего месяца")
    start = history_start(eligible[-1][0])
    result = [
        {"date": stamp, "value": value}
        for stamp, value in eligible
        if stamp >= start
    ]
    if len(result) < 96:
        raise SourceError(f"НБРК: в 10-летнем окне только {len(result)} месячных точек")
    return result


def parse_returns(markup: str, start_year: int) -> list[dict]:
    """Берёт первый процент из строк годовой таблицы доходности НБРК."""
    result = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", markup, re.DOTALL | re.IGNORECASE):
        cells = [_plain(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE)]
        if len(cells) < 2 or not re.fullmatch(r"\d{4}\*?", cells[0]):
            continue
        year = int(cells[0][:4])
        match = re.fullmatch(r"(-?\d+(?:[.,]\d+)?)%", cells[1].replace(" ", ""))
        if year < start_year or match is None:
            continue
        value = float(match.group(1).replace(",", "."))
        if not -100 <= value <= 100:
            raise SourceError(f"НБРК: доходность {value:.2f}% за {year} вне ожидаемого диапазона")
        result.append({"date": str(year), "value": value})
    if len(result) < 8:
        raise SourceError(f"НБРК: в таблице доходности только {len(result)} точек")
    return result


def _previous(dataset: Path) -> dict:
    try:
        return json.loads(dataset.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build(dataset: Path = DEFAULT_DATASET, today: date | None = None) -> dict:
    today = today or date.today()
    previous = _previous(dataset)
    issues: list[str] = []
    assets: list[dict] = []
    returns: list[dict] = []
    assets_stale = returns_stale = False
    query = urllib.parse.urlencode(
        {
            "beginMount": 1,
            "beginYear": today.year - HISTORY_YEARS,
            "endMount": today.month,
            "endYear": today.year,
        }
    )
    try:
        payload = json.loads(fetch(f"{ASSETS_RECORDS_URL}?{query}", "national_fund_assets.json"))
        assets = parse_assets(payload, today)
    except (SourceError, json.JSONDecodeError) as exc:
        assets = previous.get("assets") or []
        assets_stale = bool(assets)
        issues.append(f"активы НБРК не обновились ({exc})")
    try:
        markup = fetch(RETURNS_URL, "national_fund_returns.html").decode("utf-8", "ignore")
        returns = parse_returns(markup, today.year - HISTORY_YEARS)
    except SourceError as exc:
        returns = previous.get("returns") or []
        returns_stale = bool(returns)
        issues.append(f"доходность НБРК не обновилась ({exc})")
    if not assets:
        raise SourceError("Нацфонд: нет ни свежего, ни сохранённого ряда активов")
    if not returns:
        raise SourceError("Нацфонд: нет ни свежего, ни сохранённого ряда доходности")
    return {
        "generated_at": _now(),
        "assets": assets,
        "assets_stale": assets_stale,
        "assets_source": ASSETS_PAGE,
        "returns": returns,
        "returns_stale": returns_stale,
        "returns_source": RETURNS_URL,
        "issues": issues,
        "availability": {
            "assets": "ежемесячно, JSON НБРК, 1993 год по настоящее время",
            "returns": "ежегодно, HTML-таблица НБРК, 2001 год по настоящее время",
            "operations": "ежемесячно, но единого машинного ряда за 10 лет нет",
        },
    }


def main() -> None:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    data = build(dataset)
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Нацфонд: активов {len(data['assets'])}, доходностей {len(data['returns'])}")
    for issue in data["issues"]:
        print(f"  проблема: {issue}")
    print(f"Записано: {dataset}")


if __name__ == "__main__":
    main()
