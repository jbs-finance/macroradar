import json
from datetime import UTC, datetime

import listings
from build_housing import build
from etl import SourceError
from test_build_housing import dataset

# Синтетическая карточка по вёрстке kn.kz 24.09.2026, без текстов продавцов.
KN_CARD = """<div class="row kn-p-20 border-top kn-shadow-2" data-object-id="{id}">
<a href="/card/{id}" class="kn-fs-18 kn-lh-20">2-комнатная квартира, ул. Тестовая, 1</a>
<div><span class="fw-bold">5/12</span><span>этаж</span></div>
<div><span>площадь:</span><span class="fw-bold">{area} м²</span></div>
<div>Частное лицо</div><div>{price} ₸</div>{m2}
"""


def kn_page(cards: list[tuple[int, str, str]], total: str = "6 840") -> str:
    body = "".join(
        KN_CARD.format(
            id=3700000 + i,
            area=area,
            price=price,
            m2=f"<div>/ {m2} ₸ за м²</div>" if m2 else "",
        )
        for i, (area, price, m2) in enumerate(cards)
    )
    return f"<p>Найдено {total} объявлений</p>{body}"


KORTER = (
    "<script>window.INITIAL_STATE = "
    + json.dumps(
        {
            "buildingListingStore": {
                "geoObjectsAvgPrices": {
                    "secondaryGeoObjects": {
                        "geoObjects": [
                            {"nominative": "Астана", "averagePrice": 598527},
                            {"nominative": "Конаев (Капшагай)", "averagePrice": 384000},
                            {"nominative": "Косшы", "averagePrice": 0},
                        ]
                    }
                }
            }
        },
        ensure_ascii=False,
    )
    + ";</script>"
)


def test_kn_parse_takes_price_per_m2_and_falls_back_to_price_over_area():
    page = kn_page([("42", "28 500 000", "678 571"), ("50", "30 000 000", "")])
    parsed = listings.parse_kn_search(page)
    assert parsed["total"] == 6840 and parsed["cards"] == 2
    assert parsed["price_m2"] == [678571.0, 600000.0]


def test_korter_parse_skips_zero_average():
    assert listings.parse_korter_cities(KORTER) == {
        "Астана": 598527,
        "Конаев (Капшагай)": 384000,
    }


def test_collect_survives_source_failure_and_stops_on_short_page():
    calls = []

    def get(url, raw_name):
        calls.append(url)
        if "korter" in url:
            raise SourceError("korter.kz недоступен")
        # Короткая страница: дальше листать не нужно.
        return kn_page(
            [(str(40 + i), "30 000 000", f"{700000 + i * 1000}") for i in range(10)]
        )

    data = listings.build(get, now=datetime(2026, 9, 24, 4, tzinfo=UTC))
    assert len(data["kn"]) == 8
    assert data["kn"][0] == {
        "city": "Алматы",
        "rooms": 1,
        "listings_on_site": 6840,
        "sample": 10,
        "url": "https://www.kn.kz/almaty/prodazha-odnokomnatnyh-kvartir",
        "q1": 702250,
        "median": 704500,
        "q3": 706750,
    }
    assert sum("kn.kz" in u for u in calls) == 8  # по одной странице на срез
    assert data["korter"] == [] and len(data["issues"]) == 2


def test_captcha_is_a_source_failure(monkeypatch):
    monkeypatch.setattr(
        listings, "fetch", lambda url, name: b"<html>SafeLine challenge</html>"
    )
    monkeypatch.setattr(listings, "PAUSE", 0)
    get = listings.polite_fetch()
    try:
        get("https://www.kn.kz/almaty/prodazha-kvartir", "x.html")
    except SourceError as exc:
        assert "проверку на робота" in str(exc)
    else:
        raise AssertionError("капча должна считаться отказом источника")


def test_page_section_compares_with_bns_and_labels_trust():
    data = {
        "generated_at": "2026-09-24T04:00:00+00:00",
        "kn": [
            {
                "city": "Алматы",
                "rooms": 2,
                "listings_on_site": 6840,
                "sample": 90,
                "url": "u",
                "q1": 653055,
                "median": 749591,
                "q3": 867882,
            }
        ],
        "korter": [
            {"city": "Конаев (Капшагай)", "avg_price_m2": 384000, "url": "u"},
            {"city": "Бесагаш", "avg_price_m2": 495000, "url": "u"},
        ],
        "issues": [],
    }
    page = build(dataset(), data).replace("\xa0", " ")
    assert "Цены предложения на площадках" in page and "Срез на 24.09.2026" in page
    assert "цены сделок они не заменяют" in page
    assert "749 591" in page and "653 055 … 867 882" in page
    assert (
        "Для сравнения, БНС: Алматы: новые 625 435, вторичка 625 435 ₸/м² (август 2026)"
        in page
    )
    # Конаев сопоставлен с городом БНС, у Бесагаша пары нет.
    assert "<td>Конаев</td><td>384 000</td><td>625 435</td><td>−38,6%</td>" in page
    assert "Бесагаш" not in page


def test_page_without_listings_says_no_data():
    page = build(dataset(), None)
    assert "площадки объявлений не ответили" in page


def avi_page(cards: list[tuple[str, str, str]]) -> str:
    """Синтетические карточки по вёрстке avi.kz 24.09.2026: (id, заголовок, цена)."""
    return "".join(
        f'<div class="sr-2-list-item-n"><a href="https://avi.kz/almaty/prodazha-kvartiry-{ad}.html">x</a>'
        f'<div class="sr-2-list-item-n-cat-box">Вторичный рынок</div>'
        f'<div class="sr-2-list-item-n-title">{title}</div><div class="sr-2-list-item-n-price">{price}</div></div>'
        for ad, title, price in cards
    )


def test_avi_parse_reads_rooms_and_area_from_title():
    page = avi_page(
        [
            ("1", "2 комнатная квартира, 50 м<sup>2</sup>", "55 000 000 тг"),
            ("2", "3-комн. квартира, 58.2 кв.м", "43 500 000 тг"),
            ("3", "Квартира без комнат в заголовке", "10 000 000 тг"),
        ]
    )
    cards = listings.parse_avi_page(page)
    assert [(c["id"], c["rooms"], round(c["price_m2"])) for c in cards] == [
        ("1", 2, 1100000),
        ("2", 3, 747423),
    ]


def test_avi_stops_when_site_repeats_last_page(monkeypatch):
    first = avi_page([(str(i), "2 комнатная квартира, 50 м", f"{30 + i} 000 000 тг") for i in range(12)])
    calls = []

    def get(url, raw_name):
        calls.append(url)
        # Любая страница после первой повторяет её: так сайт отвечает за последней страницей.
        return first

    rows = listings.collect_avi(get, [])
    assert sum("almaty" in u for u in calls) == 2
    assert rows[0]["city"] == "Алматы" and rows[0]["rooms"] == 2 and rows[0]["sample"] == 12
