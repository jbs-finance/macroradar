from datetime import UTC, datetime

import pytest

import deals
from build_housing import build
from etl import SourceError
from test_build_housing import dataset

ND = chr(0x2013)  # типографское тире из текста БНС

# Фрагменты релизов БНС 2026 года: у каждого своя формулировка.
JANUARY = (
    "<p>В январе 2026 года количество зарегистрированных сделок купли-продажи жилья составило 27 745, "
    "из них 6 020 по индивидуальным домам и 21 725 по квартирам в многоквартирных домах. Лидерами по "
    f"количеству сделок остаются города Астана (5 375 {ND} 19,4%) и Алматы (5 191 {ND} 18,7%).</p>"
    "<p>Всего в январе 2026 года по квартирам было совершено 21 725 сделок, что составляет 78,3% от общего числа сделок.</p>"
)
APRIL = (
    "<p>В апреле 2026 года количество зарегистрированных сделок купли-продажи жилья составило 35 154, "
    "что на 23,4% больше. Наибольшая активность сохраняется в Алматы<span>-</span>6 498 сделок (18,5%), "
    "Астане<span>-</span>6 193 сделки (17,6%).</p><p>Всего было зарегистрировано 27 331 сделка с квартирами, "
    "что составляет 77,7% от общего объема сделок.</p>"
)
JULY = (
    "<p>В июле 2026 года зарегистрировано 37 158 сделок купли-продажи жилья.</p><p>Наибольшее количество "
    "сделок пришлось на города Алматы (7 263, или 19,5%) и Астана (6 999, или 18,8%).</p><p>Всего в июле "
    "зарегистрировано 28 575 сделок с квартирами, что составляет 76,9% от общего числа.</p>"
)
# Декабрь 2025: другой оборот в начале и «это X% от общего показателя».
DECEMBER = (
    "<p>В декабре 2025 года зарегистрировано рекордное количество сделок по купле-продаже жилья за последние "
    f"три года {ND} 53 128 сделок. Лидеры: Астана {ND} 11 674 сделки, Алматы {ND} 9 013 сделок.</p>"
    f"<p>Всего в декабре 2025 года по квартирам совершено 41 177 сделок {ND} это 77,5% от общего показателя.</p>"
)
# Август: числа и слова порезаны строчными тегами, как на сайте.
AUGUST = (
    "<p>В <span>августе</span> 2026 года количество зарегистрированных сделок купли-продажи жилья составило 35 807. "
    f"Лидерами остаются города Алматы (<span>7 690</span>{ND} 21,5%) и Астана (<span>6 398</span>{ND} 1<span>7,9</span>%).</p>"
    "<p>Всего в <span>августе</span> 2026 года по квартирам  совершено 2<span>7 719</span> сдел<span>ок</span>, "
    "что составляет 77,4% от общего числа сделок.</p>"
)


@pytest.mark.parametrize(
    "page, expected",
    [
        (
            JANUARY,
            {
                "date": "2026-01",
                "total": 27745,
                "flats": 21725,
                "houses": 6020,
                "almaty": 5191,
                "astana": 5375,
            },
        ),
        (
            APRIL,
            {
                "date": "2026-04",
                "total": 35154,
                "flats": 27331,
                "houses": 7823,
                "almaty": 6498,
                "astana": 6193,
            },
        ),
        (
            DECEMBER,
            {
                "date": "2025-12",
                "total": 53128,
                "flats": 41177,
                "houses": 11951,
                "almaty": 9013,
                "astana": 11674,
            },
        ),
        (
            JULY,
            {
                "date": "2026-07",
                "total": 37158,
                "flats": 28575,
                "houses": 8583,
                "almaty": 7263,
                "astana": 6999,
            },
        ),
    ],
)
def test_release_wordings(page, expected):
    assert deals.parse_release(page) == expected


def test_numbers_split_by_inline_tags_are_glued():
    row = deals.parse_release(AUGUST)
    assert (row["total"], row["flats"], row["almaty"], row["astana"]) == (
        35807,
        27719,
        7690,
        6398,
    )


def test_share_mismatch_rejects_release():
    with pytest.raises(ValueError, match="доля квартир не сходится"):
        deals.parse_release(JULY.replace("76,9%", "70,0%"))


def test_build_skips_broken_release_and_orders_months():
    news = (
        '<a href="/ru/news/kolichestvo-sdelok-kupli-prodazhi-zhilya-uvelichilos-na-23-4-/">x</a>'
        '<a href="/ru/news/kolichestvo-sdelok-kupli-prodazhi-zhilya-v-mae/">x</a>'
        '<a href="/ru/news/kolichestvo-sdelok-kupli-prodazhi-zhilya-umenshilos-na-47-8-/">x</a>'
        '<a href="/ru/news/drugaya-novost/">x</a>'
    )

    def get(url, raw_name):
        if "PAGEN_1=1" in url:
            return news
        if "PAGEN_1" in url:
            raise SourceError("конец ленты")
        if url.endswith("23-4-/"):
            return APRIL
        if url.endswith("47-8-/"):
            return JANUARY
        return "<p>другой шаблон</p>"

    data = deals.build(get, now=datetime(2026, 9, 24, tzinfo=UTC))
    assert [o["date"] for o in data["obs"]] == ["2026-01", "2026-04"]
    assert len(data["issues"]) == 2  # релиз без разбора и конец ленты


def test_page_section_shows_latest_month_and_change():
    obs = [
        {**deals.parse_release(JULY), "url": "https://stat.gov.kz/ru/news/a/"},
        {**deals.parse_release(AUGUST), "url": "https://stat.gov.kz/ru/news/b/"},
    ]
    page = build(dataset(), None, {"obs": obs, "issues": []}).replace("\xa0", " ")
    assert "Сделки купли-продажи жилья" in page and "35 807" in page
    assert "за месяц <b>" + chr(0x2212) + "3,6%</b>" in page
    assert "квартиры <b>77,4%</b>" in page
    assert "пресс-релиз за август 2026" in page


def test_page_without_deals_says_no_data():
    assert "релизы БНС о сделках не разобраны" in build(dataset(), None, None)
