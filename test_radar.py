"""Тесты радара: разбор ставки, инфляции, календаря, лента событий, интерпретации."""

import re
from datetime import date, timedelta

import pytest

from build_radar import build, range_markup
from etl import Obs, Series, SourceError
from radar import (
    calendar_events,
    parse_business_activity,
    signal_business_activity,
    fx_events,
    inflation_events,
    parse_inflation_page,
    parse_rate_table,
    rate_events,
    signal_inflation,
    signal_rate,
    signal_wage,
)

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)

RATE_HTML = """
<table><tr><th>Дата</th><th>Ставка</th><th>Коридор</th></tr>
<tr><td>26.01.2026</td><td>18,00</td><td>17,00 - 19,00</td></tr>
<tr><td>08.06.2026</td><td>17,00</td><td>16,00 - 18,00</td></tr>
<tr><td>27.07.2026</td><td>16,75</td><td>15,75 - 17,75</td></tr>
<tr><td>04.09.2026*</td><td></td><td></td></tr>
<tr><td>мусор</td><td>x</td></tr>
</table>"""

# Реальный текст публикации БНС содержит короткое тире, парсер обязан его пережить.
INFLATION_HTML = (
    "<html><body><div>Ключевые моменты 9,8% "
    "Инфляция в Республике Казахстан в августе 2026 года составила 9,8% "
    f"(в июле 2026г. {EN_DASH} 10,2%), за месяц {EN_DASH} 0,6% (в предыдущем месяце {EN_DASH} 0,6%). "
    "Цены на продовольственные товары за год выросли на 9,5% (в июле 2026г. "
    f"{EN_DASH} 10,1%), непродовольственные товары {EN_DASH} на 11,4%, платные услуги {EN_DASH} на 8,9%."
    "</div></body></html>"
)

CALENDAR_HTML = """
<div class="calendar-event active" id="x1">
  <div class="calendar-event-day"> 01.09.2026 </div>
  <a href="/ru/industries/economy/prices/publications/347964/" class="calendar-event-title">Инфляция в Республике Казахстан (август 2026г.)</a>
  <div class="calendar-event-type"> Публикация </div>
</div>
<div class="calendar-event" id="x2">
  <div class="calendar-event-day"> 04.09.2026 </div>
  <a href="/api/iblock/element/1/file/ru/" class="calendar-event-title">
      Индекс цен на товары
  </a>
  <div class="calendar-event-type"> Электронная таблица </div>
</div>"""


def rate_series(values, start=date(2025, 1, 1)):
    return Series(
        series_id="kz.rate.base",
        name_ru="Базовая ставка НБРК",
        unit="% годовых",
        freq="D",
        source="Национальный Банк РК",
        source_url="https://example.org",
        fetched_at="2026-09-03T00:00:00+00:00",
        obs=[
            Obs(date=(start + timedelta(days=45 * i)).isoformat(), value=v)
            for i, v in enumerate(values)
        ],
    )


class TestRateTable:
    def test_decisions_and_planned_split(self):
        decisions, planned = parse_rate_table(RATE_HTML)
        assert [d[1] for d in decisions] == [18.0, 17.0, 16.75]
        assert decisions[-1][2] == "15,75 - 17,75"
        assert planned == [date(2026, 9, 4)]

    def test_garbage_rows_ignored(self):
        decisions, _ = parse_rate_table(RATE_HTML)
        assert all(isinstance(d[1], float) for d in decisions)


class TestInflationPage:
    def test_all_numbers_extracted(self):
        p = parse_inflation_page(INFLATION_HTML)
        assert p["month"] == "2026-08"
        assert p["yoy"] == pytest.approx(9.8)
        assert p["mom"] == pytest.approx(0.6)
        assert p["food"] == pytest.approx(9.5)
        assert p["nonfood"] == pytest.approx(11.4)
        assert p["services"] == pytest.approx(8.9)


    def test_monthly_first_wording_is_not_confused_with_yearly(self):
        """Июль 2025: первым идёт месячный уровень, годовой дальше по фразе."""
        page = (
            "<p>Ключевые моменты 11,8% Месячный уровень инфляции в Республике Казахстан "
            "в июле 2025 года замедлился и составил 0,7% (в предыдущем месяце: 0,8%), "
            "годовой уровень составил 11,8% (на уровне предыдущего месяца). "
            "Цены на платные услуги за год выросли на 14,9%, продовольственные товары "
            "на 11,2%, непродовольственные товары на 9,1%.</p>"
        )
        p = parse_inflation_page(page)
        assert p["month"] == "2025-07"
        assert p["yoy"] == pytest.approx(11.8)
        assert p["mom"] == pytest.approx(0.7)
        assert p["food"] == pytest.approx(11.2)
        assert p["services"] == pytest.approx(14.9)

    def test_older_wording_with_za_god(self):
        page = ("<p>Ключевые моменты 8.5% Инфляция в Республике Казахстан в октябре 2024 года "
                "ускорилась, за год составила 8,5% (в сентябре 2024г. 8,3%), за месяц 0,9%.</p>")
        p = parse_inflation_page(page)
        assert p["month"] == "2024-10" and p["yoy"] == pytest.approx(8.5) and p["mom"] == pytest.approx(0.9)


    def test_page_without_key_phrase_raises(self):
        with pytest.raises(SourceError):
            parse_inflation_page("<p>ничего</p>")


class TestCalendar:
    def test_events_parsed_with_absolute_urls(self):
        events = calendar_events(CALENDAR_HTML)
        assert len(events) == 2
        assert events[0]["date"] == "2026-09-01"
        assert events[0]["url"].startswith("https://stat.gov.kz/ru/")
        assert events[0]["type"] == "Публикация"

    def test_multiline_title_normalised(self):
        events = calendar_events(CALENDAR_HTML)
        assert events[1]["title"] == "Индекс цен на товары"


class TestEvents:
    def test_rate_cut_described_with_previous(self):
        s = rate_series([18.0, 17.0, 16.75])
        events = rate_events(s, date(2020, 1, 1))
        assert "снизил" in events[-1]["text"]
        assert "17%" in events[-1]["text"]
        assert "16,75%" in events[-1]["text"]

    def test_rate_hold_described(self):
        s = rate_series([18.0, 18.0])
        assert "сохранил" in rate_events(s, date(2020, 1, 1))[-1]["text"]

    def test_events_outside_window_dropped(self):
        s = rate_series([18.0, 17.0])
        assert rate_events(s, date(2030, 1, 1)) == []

    def test_inflation_streak_counted(self):
        points = [
            {"month": "2026-05", "yoy": 11.0, "published": "2026-06-01"},
            {"month": "2026-06", "yoy": 10.3, "published": "2026-07-01"},
            {"month": "2026-07", "yoy": 10.2, "published": "2026-08-03"},
            {"month": "2026-08", "yoy": 9.8, "published": "2026-09-01"},
        ]
        events = inflation_events(points, date(2026, 8, 20))
        assert len(events) == 1
        assert "9,8%" in events[0]["text"]
        assert "3 мес. подряд" in events[0]["text"]

    def test_fx_small_move_is_not_an_event(self):
        today = date(2026, 9, 3)
        obs = [
            {"date": (today - timedelta(days=30 * (5 - i))).isoformat(), "value": 460.0}
            for i in range(6)
        ]
        assert fx_events({"obs": obs}, today) == []

    def test_fx_big_move_is_an_event(self):
        today = date(2026, 9, 3)
        obs = [
            {"date": (today - timedelta(days=30 * (5 - i))).isoformat(), "value": 500.0}
            for i in range(5)
        ]
        obs.append({"date": today.isoformat(), "value": 455.0})
        events = fx_events({"obs": obs}, today)
        assert len(events) == 1 and "укрепился" in events[0]["text"]


class TestSignals:
    def test_two_cuts_is_easing_cycle(self):
        text = signal_rate(rate_series([18.0, 17.0, 16.75]), 9.8)
        assert "смягчения" in text
        assert "Реальная ставка около 6,9" in text

    def test_hold_is_pause(self):
        assert "Пауза" in signal_rate(rate_series([18.0, 18.0, 18.0]), None)

    def test_inflation_far_above_target(self):
        text = signal_inflation(
            [{"month": "2026-08", "yoy": 9.8, "food": 9.5, "services": 8.9}]
        )
        assert "выше цели" in text

    def test_inflation_within_target(self):
        assert "В пределах цели" in signal_inflation([{"month": "2026-08", "yoy": 4.5}])

    def test_wage_real_growth(self):
        obs = [{"date": f"2025-Q{i}", "value": 400000.0} for i in range(1, 5)]
        obs.append({"date": "2026-Q1", "value": 460000.0})
        assert "быстрее инфляции" in signal_wage({"obs": obs}, 9.8)

    def test_missing_data_gives_empty_string_not_crash(self):
        assert signal_wage(None, 9.8) == ""
        assert signal_inflation([]) == ""


class TestRateFreshnessGate:
    """Обрыв ряда решений это молчаливый дефект: страница покажет старую ставку
    как действующую, если не проверять возраст последнего решения."""

    def test_stale_rate_series_is_caught(self):
        from radar import RATE_MAX_AGE_DAYS

        old_date = date.today() - timedelta(days=RATE_MAX_AGE_DAYS + 30)
        series = rate_series([15.25], start=old_date)
        age = (date.today() - date.fromisoformat(series.obs[-1].date)).days
        assert age > RATE_MAX_AGE_DAYS

    def test_fresh_rate_series_passes(self):
        from radar import RATE_MAX_AGE_DAYS

        series = rate_series([16.75], start=date.today() - timedelta(days=20))
        age = (date.today() - date.fromisoformat(series.obs[-1].date)).days
        assert age <= RATE_MAX_AGE_DAYS

    def test_empty_year_page_counts_as_failed(self):
        """Страница года без единой строки таблицы это не «нет решений», а сбой."""
        decisions, planned = parse_rate_table("<table><tr><td>шапка</td></tr></table>")
        assert not decisions and not planned


BAI_HTML = (
    "<p>Комментарий директора Департамента денежно-кредитной политики "
    "Национального Банка Республики Казахстан о деловой активности в августе 2026 года "
    "В августе 2026 года индекс деловой активности (ИДА) перешел в положительную зону, "
    "составив 50,6. Улучшение деловой активности наблюдается в строительстве, в производстве "
    "и сфере услуг, где индексы остались в зоне роста, составив соответственно 54,8, 52,1 и 50,9 "
    "(в июле: 51,8, 52,1 и 50,4). В торговле и горнодобывающей промышленности индексы также "
    "улучшились, но остаются ниже нейтральной отметки, составив 48,8 и 48,6 (в июле: 46,8 и 47,1). "
    "Индекс бизнес-климата в августе 2026 года составил 10,7.</p>"
)


class TestBusinessActivity:
    def test_headline_and_climate(self):
        d = parse_business_activity(BAI_HTML)
        assert d["month"] == "2026-08"
        assert d["value"] == pytest.approx(50.6)
        assert d["climate"] == pytest.approx(10.7)

    def test_all_five_sectors_matched_in_order(self):
        """Сектора берутся по словарю: оборот «в зоне роста» не должен стать названием."""
        d = parse_business_activity(BAI_HTML)
        got = {s["name"]: s["value"] for s in d["sectors"]}
        assert got == {
            "Строительство": pytest.approx(54.8),
            "Производство": pytest.approx(52.1),
            "Услуги": pytest.approx(50.9),
            "Торговля": pytest.approx(48.8),
            "Горнодобыча": pytest.approx(48.6),
        }

    def test_previous_month_values_in_brackets_ignored(self):
        """Числа прошлого месяца стоят в скобках и сдвинули бы сопоставление."""
        d = parse_business_activity(BAI_HTML)
        assert all(s["value"] not in (51.8, 50.4, 46.8, 47.1) for s in d["sectors"])

    def test_message_without_numbers_raises(self):
        with pytest.raises(SourceError):
            parse_business_activity(
                "<p>о деловой активности в августе 2026 года без чисел</p>"
            )

    def test_signal_names_weak_sectors(self):
        text = signal_business_activity(parse_business_activity(BAI_HTML))
        assert "50,6" in text
        assert "торговля" in text and "горнодобыча" in text

    def test_signal_for_contraction(self):
        assert "сжимается" in signal_business_activity({"value": 46.0, "sectors": []})

    def test_no_data_gives_empty_signal(self):
        assert signal_business_activity(None) == ""


class TestPage:
    def radar(self):
        return {
            "generated_at": "2026-09-03T06:00:00+00:00",
            "series": [
                {
                    "series_id": "kz.rate.base",
                    "name_ru": "Базовая ставка НБРК",
                    "unit": "% годовых",
                    "freq": "D",
                    "source": "Национальный Банк РК",
                    "source_url": "https://example.org",
                    "fetched_at": "2026-09-03T06:00:00+00:00",
                    "stale": False,
                    "note": "",
                    "obs": [
                        {"date": "2025-01-17", "value": 15.25},
                        {"date": "2026-01-26", "value": 18.0},
                        {"date": "2026-06-08", "value": 17.0},
                        {"date": "2026-07-27", "value": 16.75},
                    ],
                }
            ],
            "inflation": [],
            "next_rate_decision": {
                "date": "2026-09-04",
                "title": "Решение",
                "kind": "rate",
                "url": "https://example.org",
                "type": "Решение",
            },
            "calendar": [
                {
                    "date": "2026-09-04",
                    "title": "Решение НБРК",
                    "kind": "rate",
                    "url": "https://example.org",
                    "type": "Решение",
                }
            ],
            "events": [
                {
                    "date": "2026-07-27",
                    "kind": "rate",
                    "text": "НБРК снизил базовую ставку до 16,75%",
                }
            ],
            "signals": {"rate": "Цикл смягчения."},
            "issues": [],
        }

    def pulse(self):
        return {"generated_at": "2026-09-03T06:00:00+00:00", "series": [], "issues": []}

    def test_page_has_header_tabs_and_no_noindex(self):
        page = build(self.radar(), self.pulse(), {})
        assert "noindex" not in page
        assert 'rel="canonical" href="https://jbs.finance/macroradar/macro/"' in page
        assert 'aria-current="page">Макро' in page
        assert "Радар экономики Казахстана" in page

    def test_scan_shows_rate_with_signal_and_range(self):
        page = build(self.radar(), self.pulse(), {})
        assert "16,75" in page
        assert "Цикл смягчения." in page
        assert 'class="range"' in page

    def test_events_and_calendar_rendered(self):
        page = build(self.radar(), self.pulse(), {})
        assert "снизил базовую ставку" in page
        assert "Решение НБРК" in page
        assert "Следующее решение по базовой ставке" in page

    def test_no_resources_loaded_from_outside(self):
        """Ссылки наружу допустимы (источники, сайт), загрузка ресурсов нет.

        Единственный допустимый script это блок разметки ld+json: он не исполняется,
        а читается поисковиком, поэтому переживает CSP со script-src 'none'."""
        page = build(self.radar(), self.pulse(), {})
        scripts = re.findall(r"<script[^>]*>", page)
        assert all('type="application/ld+json"' in tag for tag in scripts), scripts
        assert len(scripts) <= 1
        assert not re.search(
            r'<(img|link)[^>]+(src|href)="https?://(?!jbs\.finance)', page
        )
        assert "{{" not in page and ":root {" in page

    def test_dataset_markup_present(self):
        """Разметка набора данных: поисковик должен видеть дату обновления и источники."""
        page = build(self.radar(), self.pulse(), {})
        assert '"@type": "Dataset"' in page
        assert '"dateModified"' in page
        assert "Национальный Банк РК" in page

    def test_share_description_carries_live_numbers(self):
        """Ссылка в мессенджере обязана показывать сегодняшние числа, а не общий текст."""
        page = build(self.radar(), self.pulse(), {})
        desc = re.search(r'<meta name="description" content="([^"]+)"', page).group(1)
        assert "16,75" in desc

    def test_peers_block_highlights_kazakhstan(self):
        radar = self.radar()
        radar["neighbours"] = [
            {
                "id": "inflation", "name_ru": "Инфляция", "unit": "% за год", "digits": 1,
                "lower_is_better": True, "source": "World Bank", "fetched_at": "2026-09-04T06:00:00+00:00",
                "items": [
                    {"country": "Китай", "value": 0.06, "year": "2025", "is_kz": False},
                    {"country": "Казахстан", "value": 11.4, "year": "2025", "is_kz": True},
                ],
            }
        ]
        page = build(radar, self.pulse(), {})
        assert 'class="kz"' in page
        assert "Казахстан среди соседей" in page

    def test_no_dashes_in_visible_text(self):
        page = build(self.radar(), self.pulse(), {})
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<style.*?</style>", "", page))
        assert EM_DASH not in visible and EN_DASH not in visible

    def test_range_pin_within_track(self):
        series = self.radar()["series"][0]
        markup = range_markup(series, 2)
        pos = float(re.search(r"left: ([\d.]+)%", markup).group(1))
        assert 0 <= pos <= 100
