# Macro Radar

Радар макроэкономики Казахстана: ETL открытых источников плюс сборка шести
статических страниц (обзор, макро, торговля, Нацфонд, бюджет, налоговые
ставки). Живой пример: https://jbs.finance/macroradar/

Источники, которые реально дёргает код: Всемирный банк (World Bank), Национальный
Банк РК (nationalbank.kz), Бюро национальной статистики (stat.gov.kz, интерфейс
Taldau), Комитет государственных доходов МФ РК (kgd.gov.kz), Министерство финансов
РК (портал gov.kz и его статистический бюллетень) и UN Comtrade.

## Как запустить у себя

### Требования

- Python 3.12 или новее. Ниже не собирается: `build_radar.py` использует
  f-строку с экранированной кавычкой внутри выражения, а такой синтаксис
  (PEP 701) Python принял только в 3.12. Проверено на 3.12.13, на 3.11.15
  сборка страницы падает `SyntaxError`.
- `curl` в PATH. Его вызывает `budget.py`: у kgd.gov.kz самоподписанный сертификат,
  стандартный клиент Python его отвергает, а отключать проверку сертификата для
  публичных цифр нельзя.
- Сторонних пакетов для сбора данных и сборки страниц не требуется, всё на
  стандартной библиотеке. Единственная внешняя зависимость это `pytest`, и нужна
  она только для тестов: `pip install pytest` или `uv pip install pytest`.

### 1. Собрать данные

Каждый источник это отдельный модуль, пишет свой JSON в `out/`. Порядок важен
только для `radar.py`: ему нужны уже собранные `pulse.json` и `trade.json`.

```
python3 etl.py out/pulse.json
python3 trade.py out/trade.json
python3 radar.py out/radar.json out/pulse.json out/trade.json
python3 budget.py out/budget.json
python3 minfin.py out/minfin.json
python3 oblast.py out/oblast.json
python3 tax.py out/tax.json
python3 national_fund.py out/national_fund.json
```

Каждая команда сама сообщает, что собралось, и печатает список проблем, если
источник ответил не полностью.

### 2. Собрать страницы

`page_check.py` (шаг 3) ждёт каталог, устроенный как раздача сайта: у хаба и
у каждой темы своя папка с `index.html`.

```
mkdir -p public/macroradar/macro public/macroradar/trade \
  public/macroradar/national-fund public/macroradar/budget public/macroradar/tax

python3 build_macroradar.py public/macroradar/index.html
python3 build_radar.py public/macroradar/macro/index.html out/radar.json out/pulse.json out/trade.json
python3 build_trade.py public/macroradar/trade/index.html out/trade.json
python3 build_national_fund.py public/macroradar/national-fund/index.html out/national_fund.json
python3 build_budget.py public/macroradar/budget/index.html out/minfin.json out/budget.json out/oblast.json
python3 build_tax.py public/macroradar/tax/index.html out/tax.json
```

### 3. Прогнать гейт

`page_check.py` проверяет не только разметку, но и наполнение: разметка бывает
целой, а секция при этом пустой. Для проверки наполнения ему нужны сырые
выгрузки рядом со страницами, под именами, которые он ищет:

```
cp out/radar.json public/macroradar/data.json
cp out/pulse.json public/macroradar/pulse.json
cp out/trade.json public/macroradar/trade/data.json
cp out/national_fund.json public/macroradar/national-fund/data.json
cp out/oblast.json public/macroradar/budget/oblast.json
cp out/tax.json public/macroradar/tax/data.json
cp out/budget.json public/macroradar/tax/budget.json
cp out/minfin.json public/macroradar/tax/minfin.json

python3 page_check.py public/macroradar
```

Нулевой код и строка «проверок наполнения пройдено» означают, что все шесть
страниц собраны и наполнены.

### 4. Тесты

```
python3 -m pytest -q
```

## Честные ограничения

- **nationalbank.kz недоступен из части сетей за пределами Казахстана**
  (например, не отвечает из сети Cloudflare). Сбор рядов Нацбанка (курсы,
  базовая ставка, активы и доходность Нацфонда) в проде гоняется на своём
  раннере в Казахстане: обычный облачный CI до этих адресов не достаёт.
- **Файлы КГД весят мегабайты и обновляются раз в месяц.** `budget.py`
  кэширует их в `raw/` (по умолчанию на 7 дней, `max_age_days` в `fetch_file`),
  чтобы не перекачивать одно и то же на каждом прогоне.
- **Источник не ответил: страница получает прошлое значение вместо дыры.** В `etl.py`,
  `trade.py`, `budget.py` и `minfin.py` ряд или раздел, который не собрался,
  берётся из прошлого снапшота `out/*.json`, помечается `"stale": true` и
  получает `note` с причиной. Если ряда нет ни свежего, ни в прошлом
  снапшоте, сборка падает ненулевым кодом вместо публикации пустоты, поэтому
  первый прогон на чистом `out/` для части рядов будет строже последующих.
- **Базовая ставка НБРК читается по хардкоженным id рубрик.** `radar.py`
  держит словарь `RATE_RUBRICS` с id страницы для каждого года (2020-2026
  сейчас). Id новой рубрики не выводится из предыдущего, поэтому раз в год
  его нужно дописать руками, иначе новый год просто не запросится.
- **Бюллетень Минфина (`oblast.py`) сам себе противоречит.** Заголовок файла
  может быть от другого месяца, чем факт публикации, подпись листа внутри
  файла расходится с его именем, а в названиях строк встречается мусор вида
  `_x000D_`. Период определяет содержимое файла: на заголовок и на имя файла
  полагаться нельзя.

## Как устроено

Сбор и сборка разделены: каждый источник это отдельный модуль (`etl.py`,
`trade.py`, `budget.py`, `minfin.py`, `oblast.py`, `tax.py`,
`national_fund.py`), который пишет JSON в `out/`. Каждая страница это
отдельный `build_*.py`, который читает нужные JSON и отдаёт готовый HTML.
Общая оболочка (шапка, вкладки, мета-теги, CTA) вынесена в `layout.py`,
общий CSS и форматирование чисел в `build_pulse.py`.

Страницы статические: ни одного запроса из браузера, CSS инлайн,
переключение регионов и уровней бюджета сделано на радиокнопках и CSS
(`budget_block.py`, `compare_block.py`), без JavaScript. Отсюда
`Content-Security-Policy: script-src 'none'` в `build_macroradar.py`: скрипт
странице не нужен, поэтому он запрещён явно, и лазейки не остаётся.

Разбор источников детерминированный: только стандартная библиотека
(`urllib`, `xml.etree`, `zipfile` для xlsx, `html.parser`), ни одной
языковой модели в конвейере. Цифра на странице обязана быть воспроизводима:
тот же вход даёт тот же результат.

`page_check.py` гоняет два независимых набора проверок: структурные
(разметка, перелинковка между вкладками, canonical) и по наполнению (в
выгрузке действительно есть данные: пустой массив гейт не пропустит). Обе валят
прогон, но пишут отдельно, что именно сломалось.

## Свой радар

- **Список источников** живёт в начале каждого модуля сбора: `WB_SERIES`,
  `FX_SERIES`, `BNS_SERIES` в `etl.py`, `TRADE_WB_SERIES` в `trade.py`,
  адреса КГД в `budget.py`, адреса gov.kz в `minfin.py` и `oblast.py`,
  `RATE_RUBRICS` и `NBK_HOST` в `radar.py`.
- **Интерпретация** каждого показателя (выше нормы, ниже нормы, что это
  значит для бизнеса) это отдельные функции `signal_*` в `radar.py`, у
  каждой свой порог в коде. Налоговые ставки и пороги, включая всё, что
  считается от МРП и МЗП, живут в `tax.py`.
- **Вёрстка**, общая для всех страниц, в `layout.py` (шапка, вкладки, CTA,
  мета-теги) и в `build_pulse.py` (базовый CSS, форматирование чисел). Своя
  часть каждой страницы (карточки, таблицы, графики) в её `build_*.py` и в
  отдельных `*_block.py`.

Радар под другую страну, отрасль или свою компанию собирается заменой
источников в этих модулях. Адрес, формат ответа и кусок HTML-разбора у
каждого источника свои, поэтому переносится подход к сбору: реализацию
модуля под новый источник пишут заново.

## Помощь

Поднять радар самому можно бесплатно по инструкции выше. Если нужна
настройка под источники клиента или радар под другую отрасль или рынок и
разбираться самому не хочется, этим занимается JB Solutions: страница
продукта https://jbs.finance/ai/macroradar/, контакты
https://jbs.finance/ru/contacts.

## Лицензия

MIT, полный текст в [LICENSE](LICENSE).
