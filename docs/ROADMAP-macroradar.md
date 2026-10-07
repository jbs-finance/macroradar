# Roadmap: Macro Radar, прошлое, будущее и доверие к данным

Статус: draft for decision
Дата: 12.09.2026
Владелец решения: Bagdat
Основной PRD: `docs/PRD-macroradar.md`
Статус реализации на 23.09.2026: фазы 1-5 не начаты, из фазы 0 сделан source registry. Отраслевые candidates из Gate D отгружаются облегчённым путём, статус каждого в разделе «Порядок candidates».

## Решение по порядку

Интерактивный график не является первым шагом. Сначала Macro Radar получает проверяемый контракт источников, даты наблюдения и publish gates. После этого команда собирает один vertical slice «Стоимость денег для бизнеса». Расширение на остальные темы допускается только после прохода evidence gate на этом срезе.

Оценки указаны относительными effort bands:

- S: локальное изменение одного контура с существующими primitives;
- M: несколько связанных компонентов и новые contract tests;
- L: новый data lifecycle, хранилище или заметная продуктовая поверхность.

Это не календарные обещания.

## Low-token execution policy

Каждая фаза начинается с Bash, Python, `jq`, `rg` и project tests. Эти инструменты строят inventory, source probes, schema diffs и raw evidence без model tokens. Локальные модели получают bounded tasks и точный allowlist файлов. Kimi Code выполняет ограниченные coding lanes. Сильная модель принимает архитектуру, source trust, финансовую семантику, security и итоговый diff.

MacBook Air M5 с 10 cores и 16 GB RAM имеет локальные `qwen3.5:9b` Q4_K_M, `qwen3:4b-instruct` и `kazllm:8b`. Размер Ollama image `qwen3.5:9b` около 6.6 GB, но peak RAM, latency и качество на proposed lanes ещё не измерены. Перед регулярным запуском нужен benchmark gate на типовом brief. Предлагаемая маршрутизация: `qwen3.5:9b` для классификации, drafts registry и fixtures, cleanup документации и простых tests; `qwen3:4b-instruct` для boilerplate и extraction; `kazllm:8b` для RU/KZ текста после фиксации фактов. Эти модели не принимают автономные архитектурные решения и не ведут сложную multi-repo orchestration.

Kimi Code CLI 0.28.0 уже установлен. Он называется Kimi Code, не `Kimi3`. Gemini CLI сейчас не установлен и остаётся optional: large-context read-only audit или frontend draft только при записанной причине.

Cloud models не получают secrets или client data. Автор lane не self-approves. Приёмка выполняется другим reviewer по diff и raw command output.

### Task brief minimum

Каждый brief фиксирует: цель, точные файлы, no-go zones, требуемый artifact, команды проверки, acceptance criteria, data boundary и review owner.

### Маршрутизация по фазам

| Фаза | Первый проход | Ограниченный model lane | Обязательная сильная приёмка |
|---|---|---|---|
| 0 | Scripts для inventory, schema diff, source probes и false-fresh matrix | Локальный Qwen готовит registry и fixture drafts, Kimi Code делает integration edits | Storage architecture, source trust, publish policy, secrets и final evidence |
| Gate D | Deterministic source probes и локальный prototype | NotebookLM только с official public sources, локальная модель классифицирует evidence | Feasibility decision, product inference и data rights |
| 1 | Existing tests, DOM inventory, network и CSP probes | Kimi Code или обоснованный Gemini frontend draft, локальные модели для repetitive fixtures | CSP, accessibility, data semantics и final UI acceptance |
| 2 | Vintage diff scripts и revision fixtures | Kimi Code для ETL и storage integration, локальная модель для repetitive tests | Revision semantics, formula integrity и user-facing meaning |
| 3 | Calendar matching fixtures и forecast expiry tests | Kimi Code для ETL и storage integration | Trust taxonomy, forecast semantics и legal boundary |
| 4 | Usage evidence и source scorecards | Kimi Code для approved slice reuse | Scope, comparability и publish decision |
| 5 | Monitoring scripts, recovery drill и evidence collection | Локальная модель для runbook cleanup, Kimi Code для bounded operations edits | SLO, security, recovery и final operational gate |

До первого model lane локальный benchmark меряет peak RAM, latency и acceptance quality на одном representative brief для `qwen3.5:9b` и `qwen3:4b-instruct`. FAIL оставляет задачу детерминированному script или переводит её в bounded Kimi lane. Локальная модель не self-approves.

### Execution metrics

Фазы измеряют долю детерминированных шагов, primary-agent token use, rework rate, test pass rate и evidence completeness. Target задаётся после baseline. Экономия tokens не компенсирует rework или неполную доказательную базу.

## Карта приоритетов

| Приоритет | Результат | Фазы |
|---|---|---|
| P0 | Источник можно проверить, старый факт нельзя выдать за свежий, один slice работает без JavaScript и с интерактивом | 0, 1 |
| P1 | История пересмотров, backward analysis и официальный forward layer | 2, 3 |
| P2 | Новые темы, alerts, export, consensus после лицензии и операционное масштабирование | 4, 5 |

## Рекомендуемый первый slice

`/macroradar/macro/cost-of-money/`:

- базовая ставка НБРК;
- инфляция год к году БНС;
- производный policy gap с маркировкой `JBS calc`;
- решения НБРК и публикации инфляции на временной оси;
- следующая официальная дата решения и дата публикации;
- действующий официальный прогноз НБРК, если он прошёл source gate.

Consensus в первый slice не входит.

## Фаза 0. Source truth и надёжность pipeline

### Цель

Сделать дату, источник, версию преобразования и статус свежести проверяемыми до работы над графиком.

### Effort

L

### Dependencies

- доступ к production workflow и отдельному репозиторию `jbs-finance/macroradar`;
- полный inventory всех уже опубликованных серий и наборов;
- критерии выбора private object storage: стоимость, retention, portability, recovery и access control;
- назначенный data owner для ручного справочника налогов.

### Задачи

#### P0

1. Создать source registry для всех уже опубликованных серий и наборов со стабильными `source_id`, cadence, единицами, freshness rules и owner.
2. Для всех уже опубликованных серий и наборов ввести поля `generated_at`, `fetched_at`, `observed_period`, `source_published_at`, `next_expected_at`, `transform_version` и `status`.
3. Считать freshness по observation period и official release cadence для каждого опубликованного ряда и набора.
4. Зафиксировать ETL commit SHA или release tag в workflow вместо изменяемого `ref: main`.
5. Запускать unit tests ETL до production build.
6. Добавить negative false-fresh fixtures для каждой опубликованной серии и каждого набора с учётом их cadence.
7. Задать max observation age для Нацфонда, КГД, Минфина, областного бюллетеня и остальных опубликованных наборов.
8. Определить publish policy для `fresh`, `due`, `late`, `stale`, `blocked`, `manual_review`.
9. Сохранять `raw_sha256`, raw artifacts и normalized vintages для серий первого vertical slice.
10. Добавить внешний heartbeat на scheduled collection и deploy.
11. Развести ручной `reviewed_at` и технический `generated_at` для налогового справочника.
12. Подготовить decision memo `R2 vs alternative`. R2 является рекомендацией, а не текущим хранилищем.
13. Утвердить bucket prefixes `raw/`, `normalized/`, `manifests/revisions/`, `runs/` и lifecycle для каждого класса artifacts.
14. Хранить revision manifest первой версии как JSON в private object storage. D1 отложить до наблюдаемой query потребности.
15. Проверить public/private boundary: bucket без public hostname, credentials только в CI, browser получает только latest validated artifacts.

#### P1

1. Добавить last known good fallback для областного бюллетеня с явным статусом.
2. Добавить dual-source reconciliation для критичных значений.
3. Синхронизировать operational README с фактическим runner.

### Acceptance evidence

- schema registry содержит каждую уже опубликованную series и dataset;
- negative fixtures с новым `generated_at` и старым `observed_period` покрывают все опубликованные серии и наборы, получают `late` или `blocked` и применяют утверждённую publish policy;
- workflow artifact содержит ETL commit SHA;
- намеренно сломанный ETL unit test останавливает job до изменения `public/macroradar`;
- raw artifacts серий первого vertical slice имеют checksum, повторный transform воспроизводит normalized JSON;
- storage decision memo сравнивает R2 и минимум одну альтернативу по стоимости, retention, portability, recovery и access control;
- integration fixture пишет raw, normalized vintage и revision manifest по утверждённым prefixes;
- lifecycle table назначает retention и owner каждому prefix;
- negative access test подтверждает отсутствие public bucket access и credentials в browser bundle;
- первая версия revision manifest восстанавливается из JSON без D1 binding;
- missed scheduled run создаёт test alert;
- ручной налоговый fixture сохраняет старый `reviewed_at` и не получает статус `fresh` после пересборки;
- `git diff --check`, unit tests ETL и существующий `pnpm test:macroradar` проходят.

### Stop/go gate

GO в фазу 1 только если registry и observation-age freshness покрывают все уже опубликованные серии и наборы, а все negative false-fresh tests проходят. Любая опубликованная серия или набор без registry, freshness rule или negative fixture означает STOP. Mutable ETL version тоже означает STOP. Для серий первого vertical slice обязательны утверждённое private storage, prefixes, lifecycle, checksums и JSON revision manifest. D1 не является условием GO и остаётся deferred.

### Owner role

Data engineer. Product owner утверждает source policy. Security reviewer принимает storage и CSP boundaries.

### Риски

- raw artifacts увеличат объём хранения;
- преждевременное добавление D1 создаст второй state store без подтверждённой query потребности;
- ошибочная public bucket policy раскроет raw и quarantined artifacts;
- cadence источника не всегда формализована;
- reconciliation может задержать публикацию при допустимом методологическом расхождении.

## Discovery gate D. Отраслевые радары

### Цель

Проверить, есть ли у отраслевой истории устойчивые данные и повторяемая пользовательская задача. Gate идёт после core data trust layer фазы 0 и до core slice gates. Он полностью непубличный и не запускает разработку или публикацию отраслевой страницы.

### Effort

M на один отраслевой candidate

### Dependencies

- phase 0 gate;
- source registry и freshness contract;
- возможность хранить vintages и raw artifacts;
- назначенный owner для 90-day stability probe.

### Порядок candidates

Статус на 22.09.2026: пункты 1 и 2 уже отданы в production в облегчённом виде (один сборщик, один registry entry, один discovery-прогон вживую вместо полного шестифазного gate), в обход формального процесса этого документа. План остаётся в силе: следующие candidates идут по тому же облегчённому пути, если source-проверка проходит.

1. `Energy Production Monitor`: ЗАПУЩЕНО, `/macroradar/energy/`, коммит `2de2b3b` (13.09.2026). Энергоёмкость ВВП, первичное и конечное потребление, доля ВИЭ, национальный уровень.
2. `Industry Radar: металлургия и водозабор`: ЗАПУЩЕНО, `/macroradar/industry/`, коммит `82b2ea6` (22.09.2026). Индекс чёрной металлургии и число водозаборных сооружений по 20 областям без районов, `industry.py`. Найден через content-разбор kisi.kz (Центр экономических исследований).
3. `Agri Radar`: первый полный отраслевой продукт после поддержки preliminary и final vintages, сезонности и регионов. Проверяем урожай, запасы зерна, цены производителей, погоду и агропрогнозы.
4. `Transport & Logistics Radar`: candidate, не начат. Грузооборот и пассажирооборот по видам транспорта, транзитный потенциал; тема регулярно всплывает у kisi.kz («Транспортная связанность», «Транспортно-логистический потенциал»).
5. `Health Radar`: СОБРАН 23.09.2026 в ветке `health-radar` репозитория macroradar (коммит `327d08d`), ждёт деплоя. Койки и врачи на 10 000 населения по 20 областям (Talдау `704311`, `704316`), данные Минздрава с лагом около двух лет, последний год 2023. Объём медуслуг (`704347`) отброшен: годовой ряд противоречит квартальному, квартальный в Talдау обрывается на 2024.
6. `Standard of Living Radar`: candidate, не начат. Доходы населения, прожиточный минимум, неравенство. Пересекается с уже собираемой инфляцией в `pulse.py`, требует явной добавленной ценности перед стартом.
7. Расширение `Industry Radar` на цветную металлургию и добычу руд (ГМК целиком): candidate, требует отдельного discovery по кодам ОКЭД внутри того же индикатора Talдау `701625`.
8. Полный `Energy Radar`: P2 после отдельного source contract audit. Проверяем выработку, потребление, баланс, ВИЭ, тарифы и планы мощностей. Текущая evidence base не подтверждает стабильные machine-readable feeds для всего контура.

Перечни являются candidate source lists. Они не обещают интеграцию показателя.

### Задачи

1. Назвать один repeat-use question и основную аудиторию отрасли.
2. Составить source scorecard на каждый core metric.
3. Подтвердить machine-readable official source, cadence и revision policy.
4. Провести 90-day stability probe доступности и schema drift.
5. Назначить owner и fallback для каждого core metric.
6. Проверить права на возможное будущее переиспользование и публичное отображение.
7. Собрать локальный статический prototype story вне public routes.
8. Провести интервью или закрытый concept test с целевой аудиторией.

### Candidate official sources

- EIA, Brent spot prices: <https://www.eia.gov/dnav/pet/pet_pri_spt_s1_w.htm>
- БНС, промышленность: <https://stat.gov.kz/en/industries/business-statistics/stat-industrial-production/>
- БНС, энергетика: <https://stat.gov.kz/en/industries/business-statistics/stat-energy/>
- БНС, внешняя торговля: <https://stat.gov.kz/en/industries/economy/foreign-market/dynamic-tables/?period=month>
- KEGOC, национальная энергосистема: <https://www.kegoc.kz/electric-power/natsionalnaya-energosistema/index_en.php>
- БНС, сельское хозяйство: <https://stat.gov.kz/en/industries/business-statistics/stat-forrest-village-hunt-fish/>
- БНС, цены: <https://stat.gov.kz/ru/industries/economy/prices/>
- Казгидромет, агрометеорологические условия: <https://www.kazhydromet.kz/ru/agrometeorology/kratkiy-obzor-agrometeorologicheskih-usloviy>
- Казгидромет, агропрогнозы: <https://www.kazhydromet.kz/ru/agrometeorology/agrometeorologicheskie-prognozy>
- FAO Food Price Index: <https://www.fao.org/worldfoodsituation/foodpricesindex/en/>
- БНС, транспорт (проверено 22.09.2026): <https://stat.gov.kz/en/industries/business-statistics/stat-transport/>
- БНС, здравоохранение и благосостояние (проверено 22.09.2026): <https://stat.gov.kz/en/industries/social-statistics/stat-medicine/>
- БНС, уровень жизни (проверено 22.09.2026): <https://stat.gov.kz/en/industries/labor-and-income/stat-life/>
- БНС Talдау, показатель `701625` (индекс промпроизводства, разрез ОКЭД): <https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/701625>

### Acceptance evidence

- для каждого core metric есть минимум один machine-readable official source;
- source card фиксирует cadence, revision policy, owner и fallback;
- 90-day probe log не имеет необъяснённых пропусков или schema drift;
- prototype маркирует observed fact, external benchmark, official plan и `JBS proxy` разными trust types;
- prototype открывается только локально, не создаёт route на сайте и не меняет плитки общего хаба;
- product interview или usage experiment подтверждает repeat-use trigger.

### Stop/go gate

GO означает только право вынести candidate в backlog фазы 4. Публичный pilot до core phase gates запрещён. Если core metric не имеет machine-readable official source, опубликованной cadence, revision policy, owner или fallback, candidate получает STOP. Usage evidence требуется до добавления плитки на общий хаб.

Полный `Energy Radar` остаётся STOP, пока source contract audit не подтвердит тарифы, планы мощностей и нужную оперативность. `Agri Radar` остаётся STOP до поддержки сезонности, регионов и раздельных preliminary и final vintages.

### Owner role

Product analyst владеет user question. Data engineer владеет 90-day probe. Legal owner проверяет права переиспользования. Product owner принимает выбор pilot.

### Риски

- machine-readable endpoint может быть внутренним интерфейсом без гарантии стабильности;
- официальный план может публиковаться только в тексте или PDF;
- внешний benchmark может восприниматься как казахстанский факт;
- 90-day probe увеличивает время до product decision, но снижает риск мёртвого радара.

## Фаза 1. Один vertical slice и indicator page

### Цель

Запустить полную пользовательскую цепочку «Стоимость денег для бизнеса» на двух проверенных рядах.

### Effort

L

### Dependencies

- phase 0 gate;
- утверждённый route `/macroradar/macro/cost-of-money/`;
- утверждённый visual language пяти trust types;
- self-hosted chart runtime или собственный минимальный renderer.

### Задачи

#### P0

1. Добавить indicator page без новой верхнеуровневой вкладки.
2. Сгенерировать answer-first summary, последние факты, статический график и таблицу на серверной сборке.
3. Добавить interactive range controls, series toggles, crosshair и event detail.
4. Показать базовую ставку, инфляцию и формулу policy gap.
5. Добавить data passport и прямые primary source links.
6. Реализовать keyboard, screen reader, mobile, reduced motion и no-JS states.
7. Изменить CSP только для нужной страницы: self-hosted hashed JS, `script-src 'self'`, без inline и CDN.
8. Сохранить methodology как footer/data-passport link-only.

### Acceptance evidence

- DOM contract подтверждает отсутствие новой плитки и вкладки методики;
- browser network log содержит только first-party runtime и data requests;
- CSP test отклоняет inline script, `unsafe-eval` и внешний origin;
- keyboard E2E проходит все controls без pointer;
- screen reader review подтверждает summary, labels и table headers;
- mobile screenshots показывают график, controls и таблицу без horizontal page scroll;
- reduced-motion test фиксирует отсутствие animated transitions;
- no-JS screenshot сохраняет вывод, последние значения, таблицу, даты и источники;
- formula contract для policy gap воспроизводится из входных series ids;
- unit, page, accessibility и visual regression tests проходят.

### Stop/go gate

GO в фазу 2 только после независимого product review и accessibility review. Если без JavaScript теряется смысл страницы или CSP требует CDN, статус STOP.

### Owner role

Frontend engineer владеет indicator page. Data engineer владеет contract. Product designer и accessibility reviewer принимают interaction.

### Риски

- две шкалы могут создать ложное визуальное сравнение;
- tooltip может оказаться недоступным на touch и keyboard;
- chart bundle может ухудшить загрузку на mobile.

## Фаза 2. «Взгляд назад» и ревизии

### Цель

Показать, как показатель менялся, какие события совпали с изменениями и какие опубликованные значения были пересмотрены.

### Effort

M

### Dependencies

- phase 1 gate;
- накопленные normalized vintages;
- утверждённый порог видимости ревизии;
- event registry для решений НБРК и публикаций БНС.

### Задачи

#### P1

1. Построить revision log для серий первого vertical slice.
2. Добавить сравнение 12 месяцев, 3 года, 5 лет и полного ряда.
3. Добавить маркеры официальных событий на общей оси.
4. Показать change decomposition: новый факт, revision прошлого периода, техническое изменение без изменения значения.
5. Добавить блок «Что изменилось с прошлого выпуска» на indicator page и компактную версию на хаб.
6. Добавить deep links на выбранный период и серию.

### Acceptance evidence

- fixture с пересмотром прошлого периода сохраняет оба значения и показывает revision badge;
- сумма новых и пересмотренных изменений совпадает с diff нормализованных vintages;
- event marker открывает официальный source URL;
- deep link восстанавливает state без local storage;
- хаб показывает только изменения, прошедшие source gate;
- static fallback содержит последнюю revision note;
- regression tests первой фазы остаются зелёными.

### Stop/go gate

GO в фазу 3 только после накопления минимум двух реальных vintages серий первого vertical slice и воспроизводимого revision test. Если история перезаписывается без следа, статус STOP.

### Owner role

Data engineer владеет vintages. Product analyst формулирует decomposition. Frontend engineer владеет отображением.

### Риски

- первые периоды не дадут реальных ревизий;
- пользователю будет трудно отличить revision от нового наблюдения;
- архив raw может иметь разные форматы после изменения parser.

## Фаза 3. «Посмотреть вперёд»

### Цель

Показать ближайшие известные события и официальный forecast layer без притворной точности.

### Effort

M

### Dependencies

- phase 2 gate;
- устойчивый parser календарей НБРК и БНС;
- registry официальных прогнозов;
- правило срока действия прогноза.

### Задачи

#### P1

1. Сохранять `next_expected_at` для решения НБРК и публикации инфляции.
2. Закрывать плановое событие фактической публикацией.
3. Добавить официальный прогноз НБРК с автором, горизонтом и датой выпуска.
4. Использовать dashed line или forecast band, отличный от факта и JBS scenario.
5. Архивировать истёкший прогноз и не продолжать линию за официальный горизонт.
6. Добавить user-facing explanation границ forward layer.

#### P2

1. Спроектировать JBS scenario range на раскрытых предпосылках.
2. Подготовить decision memo по consensus: лицензия, состав, cadence, право публикации.

### Acceptance evidence

- fixture календаря создаёт `next_expected_at`, а пропущенная публикация меняет статус на `late`;
- fixture фактической публикации закрывает ожидаемое событие без дубля;
- просроченный forecast не виден в current layer и остаётся в archive;
- DOM и visual tests различают observed fact, official forecast и JBS calculation без опоры только на цвет;
- P0/P1 artifact не содержит series type `consensus`;
- каждый forecast point ведёт на официальный выпуск;
- accessibility и no-JS regression остаются зелёными.

### Stop/go gate

GO в фазу 4 только если факт и прогноз различимы в legend, DOM semantics, screen reader text и grayscale screenshot. Consensus без утверждённой лицензии означает STOP для consensus, но не для остальных задач.

### Owner role

Product analyst владеет taxonomy. Data engineer владеет calendar matching. Legal owner принимает consensus licensing. Accessibility reviewer принимает presentation.

### Риски

- календарь может менять URL и названия выпусков;
- официальный forecast может публиковаться в PDF с неоднородной структурой;
- визуальный forecast band может восприниматься как вероятность, хотя источник её не публиковал.

## Фаза 4. Расширение тем и ценности для посетителя

### Цель

Перенести проверенный product pattern на темы с доказанным спросом.

### Effort

L на волну тем

### Dependencies

- phase 3 gate;
- baseline product analytics;
- source scorecard для каждой новой темы;
- подтверждённая data feasibility.

### Задачи

#### P1

1. Приоритизировать следующую тему по спросу, источникам и решению для бизнеса.
2. Кандидаты: публичный `Energy Production Monitor` по постоянному прямому URL после gate D и core phase gates, полный `Agri Radar` после data prerequisites, затем валютная чувствительность, региональный бюджетный профиль, сравнение Казахстана со странами, экспортная концентрация. Полный `Energy Radar` остаётся P2 до source contract audit.
3. Переносить source contract, static fallback и trust taxonomy без локальных исключений.
4. Добавить календарь релизов по выбранной теме.
5. Показать visitors backlog через first-party analytics и source-link intent.

#### P2

1. Добавить export CSV и chart image после проверки условий переиспользования данных.
2. Добавить alerts после отдельного решения по consent и каналу.
3. Запустить consensus только после legal gate.
4. Рассмотреть сохранённые сравнения без account в первой итерации.

### Acceptance evidence

- scorecard новой темы содержит спрос, источник, cadence, revision risk, fallback и owner;
- public pilot получает постоянный прямой URL только в этой фазе и не становится плиткой общего хаба без usage evidence;
- новый indicator page проходит весь phase 1 evidence pack без исключений;
- analytics baseline сравнивает просмотр, interaction и source intent до и после запуска;
- export fixture сохраняет единицы, даты, источники и license note;
- alert test не отправляет сообщение без consent;
- consensus artifact отсутствует до принятого legal memo.

### Stop/go gate

Каждая новая тема имеет отдельный GO. Нет source registry, fallback или понятного business question, значит тема остаётся в backlog. Количество страниц само по себе не является целью.

### Owner role

Product owner выбирает тему. Data owner принимает источник. Frontend engineer переиспользует approved component. Legal owner принимает export и consensus.

### Риски

- копирование шаблона без сильного пользовательского вопроса;
- источники разных стран и периодов окажутся несопоставимыми;
- export увеличит риск распространения данных без контекста.

## Фаза 5. Масштабирование и operations

### Цель

Сделать регулярное обновление измеримым сервисом, а не набором успешных GitHub Actions runs.

### Effort

M, затем постоянная операционная работа

### Dependencies

- минимум два production slices;
- назначенный on-call owner;
- first-party observability и alert channel;
- утверждённые SLO после получения baseline.

### Задачи

#### P2

1. Ввести source scorecard dashboard: freshness, errors, revisions, parser version, last deploy.
2. Настроить alerts по missed run, late publication, schema drift, reconciliation mismatch и failed deploy.
3. Добавить runbook для каждого источника и recovery drill.
4. Задать retention raw artifacts и normalized vintages.
5. Автоматизировать quarterly source review и annual rubric review НБРК.
6. Измерить bundle size, Core Web Vitals и no-JS availability по всем slices.
7. Ввести post-release review: доверие, ошибочные интерпретации, source incidents и backlog.

### Acceptance evidence

- observability view показывает последний expected run, successful fetch, normalized build и deploy отдельно;
- game day с недоступным primary source проходит по runbook и не публикует ложную свежесть;
- recovery из raw artifact воспроизводит выбранный production vintage;
- on-call alert содержит series id, status, expected date, last observation и run link;
- quarterly review artifact перечисляет source changes и принятые действия;
- performance budget и accessibility regression проходят на всех indicator pages.

### Stop/go gate

Scale считается завершённым после одного успешного source failure drill и одного successful recovery drill. Отсутствие назначенного owner означает STOP для alerts, поскольку сигнал без ответственного не является контролем.

### Owner role

Operations owner отвечает за SLO и alerts. Data engineer отвечает за recovery. Product owner отвечает за пользовательское объяснение incidents.

### Риски

- alert fatigue при слишком узких freshness windows;
- raw retention без lifecycle policy увеличит стоимость;
- восстановление по старому parser может быть невоспроизводимым без версии среды.

## Сквозные обязательные гейты

| Gate | Проверяемое доказательство | Блокирует |
|---|---|---|
| Source gate | Primary URL, source id, cadence, dates, checksum, transform version | Публикацию новой серии |
| Freshness gate | Fixture с late observation и green test | Текущий вывод |
| Revision gate | Два vintages и воспроизводимый diff | Backward analysis |
| Forecast gate | Автор, официальный выпуск, горизонт и expiry | Forward layer |
| Accessibility gate | Keyboard, screen reader, mobile, reduced motion, no-JS evidence | Production deploy интерактива |
| CSP gate | First-party hashed JS, no inline, no CDN, negative test | Production deploy интерактива |
| Legal gate | Письменное решение по лицензии и публикации | Consensus и часть export |
| Operations gate | Missed-run alert и recovery drill | Масштабирование тем |

## Решения до старта реализации

1. Утвердить первый slice «Стоимость денег для бизнеса».
2. Утвердить route `/macroradar/macro/cost-of-money/`.
3. Выбрать raw storage и retention policy.
4. Назначить data owner и operations owner.
5. Утвердить поведение `late` и `blocked` на пользовательской странице.
6. Разрешить локальное изменение CSP только для self-hosted hashed JavaScript.
7. Отложить consensus до отдельного legal memo.

После этих решений команда готовит implementation plan только для фазы 0. Фазы 1-5 не стартуют пакетом.
