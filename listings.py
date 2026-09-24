"""Цены предложения на площадках объявлений: kn.kz (продажа квартир) и korter.kz (новостройки).

Дополнение к статистике БНС на странице жилья, отдельный тип доверия: это цены
предложения, не сделок и не выборочного наблюдения. Разбор перенесён из
github.com/jbs-finance/realty-mcp (разведка 23-24.09.2026):

1. kn.kz: серверный HTML, 30 объявлений на страницу, «Найдено N объявлений». Комнаты
   фильтруются только SEO-адресом (`prodazha-dvuhkomnatnyh-kvartir`), параметр room[]
   сайт игнорирует. robots: Crawl-delay 2, поэтому пауза между запросами 3 секунды.
2. korter.kz: window.INITIAL_STATE, средняя цена м² новостроек по другим городам
   (secondaryGeoObjects). Со страниц Алматы и Астаны вместе выходит около 20 городов.
3. krisha.kz не используется: п.5.3 соглашения запрещает автосбор без разрешения Kolesa.

Сбой площадки не останавливает публикацию: пишется в issues, секция показывает
«нет данных». Персональные данные продавцов не извлекаются.

Запуск: .venv/bin/python listings.py [out/listings.json]
"""

from __future__ import annotations

import html
import json
import re
import statistics
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from etl import SourceError, fetch

DATASET = Path(__file__).resolve().parent / "out" / "listings.json"
KN = "https://www.kn.kz"
KORTER = "https://korter.kz"
PAUSE = 3.0
PAGES = 3
KN_CITIES = [("Алматы", "almaty"), ("Астана", "astana")]
KN_ROOMS = {
    1: "odnokomnatnyh",
    2: "dvuhkomnatnyh",
    3: "trehkomnatnyh",
    4: "chetyrehkomnatnyh",
}
KORTER_PAGES = [("Алматы", "/новостройки-алматы"), ("Астана", "/новостройки-астаны")]


def _num(s: str) -> float | None:
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _text(fragment: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", fragment, flags=re.DOTALL)
    t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", t)))
    return re.sub(r"(\s*\|\s*)+", "|", t)


def parse_kn_search(page: str) -> dict:
    """Всего объявлений и цена за м² каждой карточки. Площадь для случая без цены за м²."""
    total = re.search(r"Найдено\s+([\d\s\xa0]+)\s+объявлен", page)
    prices = []
    for block in page.split('data-object-id="')[1:]:
        t = _text(block.split('<div class="row kn-p-20 border-top')[0])
        m2 = re.search(r"\|/ ([\d\s]+) ₸ за м²", t)
        if m2:
            prices.append(_num(m2[1]))
            continue
        price = re.search(r"\|([\d\s]+) ₸[^|]*\|", t)
        area = re.search(r"\|площадь:\|([\d.,]+) м²", t)
        if price and area and _num(area[1]):
            prices.append(_num(price[1]) / _num(area[1]))
    return {
        "total": int(_num(total[1])) if total else None,
        "cards": len(page.split('data-object-id="')) - 1,
        "price_m2": [p for p in prices if p],
    }


def parse_korter_cities(page: str) -> dict[str, float]:
    i = page.find("window.INITIAL_STATE = ")
    if i < 0:
        raise SourceError("korter.kz: нет window.INITIAL_STATE, вёрстка изменилась")
    state, _ = json.JSONDecoder().raw_decode(page[i + len("window.INITIAL_STATE = ") :])
    avg = state["buildingListingStore"].get("geoObjectsAvgPrices") or {}
    geo = (avg.get("secondaryGeoObjects") or {}).get("geoObjects", [])
    return {g["nominative"]: g["averagePrice"] for g in geo if g.get("averagePrice")}


def quartiles(xs: list[float]) -> dict[str, int] | None:
    if len(xs) < 5:
        return None
    q = statistics.quantiles(sorted(xs), n=4, method="inclusive")
    return {"q1": round(q[0]), "median": round(q[1]), "q3": round(q[2])}


def collect_kn(get: Callable[[str, str], str], issues: list[str]) -> list[dict]:
    rows = []
    for city, slug in KN_CITIES:
        for rooms, room_slug in KN_ROOMS.items():
            url = f"{KN}/{slug}/prodazha-{room_slug}-kvartir"
            prices: list[float] = []
            total = None
            try:
                for page in range(1, PAGES + 1):
                    parsed = parse_kn_search(
                        get(
                            url + (f"?page={page}" if page > 1 else ""),
                            f"kn_{slug}_{rooms}_{page}.html",
                        )
                    )
                    total = total if total is not None else parsed["total"]
                    prices += parsed["price_m2"]
                    if parsed["cards"] < 30:
                        break
            except SourceError as exc:
                issues.append(f"kn.kz {city} {rooms}-комн.: {exc}")
            stats = quartiles(prices)
            if stats is None:
                if not any(city in i and f"{rooms}-комн" in i for i in issues):
                    issues.append(
                        f"kn.kz {city} {rooms}-комн.: мало объявлений с ценой ({len(prices)})"
                    )
                continue
            rows.append(
                {
                    "city": city,
                    "rooms": rooms,
                    "listings_on_site": total,
                    "sample": len(prices),
                    "url": url,
                    **stats,
                }
            )
    return rows


def collect_korter(get: Callable[[str, str], str], issues: list[str]) -> list[dict]:
    cities: dict[str, float] = {}
    for own, path in KORTER_PAGES:
        try:
            cities.update(
                parse_korter_cities(get(KORTER + quote(path), f"korter_{own}.html"))
            )
        except (SourceError, KeyError, ValueError) as exc:
            issues.append(f"korter.kz {own}: {exc}")
    return [
        {"city": name, "avg_price_m2": round(value), "url": KORTER}
        for name, value in sorted(cities.items())
    ]


def polite_fetch() -> Callable[[str, str], str]:
    last = [0.0]

    def get(url: str, raw_name: str) -> str:
        wait = PAUSE - (time.monotonic() - last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            body = fetch(url, "listings_" + raw_name).decode("utf-8", "replace")
        finally:
            last[0] = time.monotonic()
        # Антибот не обходим: капча считается отказом источника.
        if re.search(r"captcha|safeline|cf-chl", body[:5000], re.IGNORECASE):
            raise SourceError(f"{url}: площадка показала проверку на робота")
        return body

    return get


def build(
    get: Callable[[str, str], str] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    get = get or polite_fetch()
    issues: list[str] = []
    return {
        "generated_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "kn": collect_kn(get, issues),
        "korter": collect_korter(get, issues),
        "issues": issues,
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"listings: kn {len(data['kn'])} срезов, korter {len(data['korter'])} городов, проблем {len(data['issues'])}"
    )


if __name__ == "__main__":
    main()
