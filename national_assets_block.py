"""Accessible, static official-disclosure blocks for the assets dashboard."""

from __future__ import annotations

import html

from build_pulse import fmt_num
from sovereign_assets import validate_disclosures

BLOCK_STYLE = """
.asset-nav { margin: 0 0 2rem; color: var(--muted-fg); }
.asset-section { min-width: 0; max-width: 100%; margin: 3.25rem 0; padding-top: 1.5rem; border-top: 3px solid #2F6B4F; }
.asset-section > header { max-width: 780px; margin-bottom: 1.25rem; }
.asset-section h2 { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.55rem, 3vw, 2.15rem); letter-spacing: -0.025em; }
.asset-section h3 { margin: 1.65rem 0 0.45rem; font-size: 1.05rem; }
.eyebrow { margin: 0 0 0.55rem; color: var(--muted-fg); font-size: 0.76rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; }
.scope-note { padding: 0.85rem 1rem; color: var(--muted-fg); line-height: 1.5; background: #FAF4EA; border-left: 3px solid #C98C45; }
.metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; background: var(--muted); border: 1px solid var(--muted); }
.metric { min-width: 0; padding: clamp(1rem, 2.4vw, 1.55rem); background: var(--card); }
.metric .label { margin: 0 0 0.55rem; color: var(--muted-fg); font-size: 0.76rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
.metric .number { margin: 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.4rem, 3vw, 2.35rem); letter-spacing: -0.035em; line-height: 1; }
.metric .note { margin: 0.65rem 0 0; color: var(--muted-fg); font-size: 0.83rem; line-height: 1.4; }
.metric--main { background: #273C37; color: #F6F0E7; }
.metric--main .label, .metric--main .note { color: #D7DDD3; }
.bars { display: grid; gap: 0.85rem; margin: 1.25rem 0; }
.bar-row { display: grid; grid-template-columns: minmax(180px, 1.25fr) minmax(150px, 3fr) minmax(125px, auto); gap: 0.75rem; align-items: center; }
.bar-label { line-height: 1.25; }
.bar-track { height: 0.72rem; overflow: hidden; background: #E8E1D7; border-radius: 999px; }
.bar-fill { display: block; height: 100%; min-width: 2px; background: #2F6B4F; border-radius: inherit; }
.bar-row--muted .bar-fill { background: #7A8E85; }
.bar-value { min-width: 0; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.reconcile { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; margin: 1.25rem 0; }
.reconcile div { padding: 0.9rem; background: #F5F0E8; border: 1px solid var(--muted); }
.reconcile strong { display: block; margin-top: 0.3rem; font-size: 1.12rem; font-variant-numeric: tabular-nums; }
.valuation-grid, .flow-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: 1rem 0; }
.valuation-card, .flow { padding: 1rem; border: 1px solid var(--muted); }
.valuation-card dl { display: grid; grid-template-columns: 1fr auto; gap: 0.5rem; margin: 0.75rem 0 0; }
.valuation-card dd { margin: 0; font-variant-numeric: tabular-nums; text-align: right; }
.flow { border-style: dashed; }
.flow strong { display: block; margin: 0.35rem 0; font-family: Georgia, serif; font-size: 1.4rem; }
.source-line { color: var(--muted-fg); font-size: 0.86rem; line-height: 1.5; }
.separate-pools { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 1rem 0; }
.pool { flex: 1 1 230px; padding: 1rem; background: #F5F0E8; }
.pool strong { display: block; margin: 0.35rem 0; font-family: Georgia, serif; font-size: 1.3rem; }
.data-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.data-table th, .data-table td { padding: 0.7rem 0.5rem; border-bottom: 1px solid var(--muted); text-align: right; }
.data-table th:first-child, .data-table td:first-child { padding-left: 0; text-align: left; }
.data-table thead th { color: var(--muted-fg); font-size: 0.76rem; letter-spacing: 0.05em; text-transform: uppercase; }
.asset-section details { min-width: 0; max-width: 100%; }
.asset-section .details-body { max-width: 100%; overflow-x: auto; }
.asset-section details:not([open]) > .details-body { display: none; }
@media (max-width: 760px) {
  .metric-grid, .reconcile { grid-template-columns: 1fr 1fr; }
  .bar-row { grid-template-columns: 1fr auto; }
  .bar-track { grid-column: 1 / -1; grid-row: 2; }
}
@media (max-width: 520px) {
  .metric-grid, .reconcile, .valuation-grid, .flow-grid { grid-template-columns: 1fr; }
  .bar-row { grid-template-columns: minmax(0, 1fr); gap: 0.35rem; }
  .bar-track { grid-column: 1; grid-row: auto; width: 100%; }
  .bar-value { text-align: left; white-space: normal; font-size: 0.86rem; }
  .data-table { min-width: 560px; font-size: 0.86rem; }
  .asset-section { margin-block: 2.25rem; }
}
"""


def _billions(value: float | int, decimals: int = 2) -> str:
    return fmt_num(float(value) / 1_000_000_000, decimals)


def _date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{day}.{month}.{year}"


def _source(url: str) -> str:
    return html.escape(url, quote=True)


def _bars(rows: list[dict], total: float, unit: str, top: int | None = None) -> str:
    ordered = sorted(rows, key=lambda row: row["value"], reverse=True)
    if top is not None:
        ordered = ordered[:top]
    rendered = []
    for row in ordered:
        share = float(row["value"]) / total * 100 if total else 0
        shown = _billions(row["value"]) if unit == "USD" else fmt_num(row["value"], 2)
        rendered.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{html.escape(row["label"])}</span>'
            f'<span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:{share:.4f}%"></span></span>'
            f'<span class="bar-value">{shown} млрд {unit} · {fmt_num(share, 1)}%</span>'
            "</div>"
        )
    return "".join(rendered)


def _enpf_rows(rows: list[dict]) -> str:
    return "".join(
        f"<tr><td>{html.escape(row['label'])}</td><td>{fmt_num(row['value'], 2)}</td></tr>"
        for row in rows
    )


def build_assets_blocks(disclosure: dict) -> str:
    disclosure = validate_disclosures(disclosure)
    fund = disclosure["national_fund"]
    annual = fund["annual_2025"]
    domestic = fund["domestic_monthly"]
    children = disclosure["children"]
    reserves = disclosure["nbk_reserves"]
    enpf = disclosure["enpf"]
    main = enpf["nbk_managed"]
    composition = [
        {"label": "Стабилизационный портфель", "value": annual["stabilization_portfolio"]},
        *annual["savings_components"],
    ]
    gold_share = reserves["gold"] / reserves["gross"] * 100
    fx_share = reserves["foreign_currency"] / reserves["gross"] * 100
    return TEMPLATE.format(
        verified=_date(disclosure["verified_at"]),
        annual_date=_date(annual["as_of"]),
        composition=_bars(composition, annual["gross_foreign_portfolios"], "USD"),
        gross=_billions(annual["gross_foreign_portfolios"]),
        claims=_billions(annual["children_claims"]),
        net=_billions(annual["net_foreign_assets"]),
        domestic_total=_billions(annual["domestic_securities_usd_equivalent"] + annual["domestic_cash_usd_equivalent"]),
        total=_billions(annual["total_market_value"]),
        annual_source=_source(annual["source"]),
        domestic_date=_date(domestic["as_of"]),
        debt_nominal=fmt_num(domestic["debt_nominal"], 0),
        debt_fair=fmt_num(domestic["debt_fair_value"], 0),
        equity_cost=fmt_num(domestic["equity_cost"], 0),
        equity_fair=fmt_num(domestic["equity_fair_value"], 0),
        cash=fmt_num(domestic["cash"], 0),
        domestic_source=_source(domestic["source"]),
        child_claims=_billions(children["claims"]["value"]),
        child_claims_date=_date(children["claims"]["as_of"]),
        child_savings=_billions(children["enpf_target_savings"]["value"]),
        child_savings_date=_date(children["enpf_target_savings"]["as_of"]),
        child_accrual=_billions(children["historical_accrual_approx"]["value"], 1),
        child_payout=_billions(children["historical_payouts"]["value"]),
        child_source=_source(children["sources"][0]),
        reserves_date=_date(reserves["as_of"]),
        reserves_gross=fmt_num(reserves["gross"] / 1000, 2),
        reserves_net=fmt_num(reserves["net"] / 1000, 2),
        reserves_gold=fmt_num(reserves["gold"] / 1000, 2),
        reserves_fx=fmt_num(reserves["foreign_currency"] / 1000, 2),
        gold_share=fmt_num(gold_share, 1),
        fx_share=fmt_num(fx_share, 1),
        gold_width=gold_share,
        fx_width=fx_share,
        reserves_source=_source(reserves["source"]),
        enpf_date=_date(main["as_of"]),
        enpf_total=fmt_num(main["total"], 2),
        enpf_bars=_bars(main["components"], main["total"], "KZT", top=6),
        enpf_rows=_enpf_rows(main["components"]),
        enpf_source=_source(main["source"]),
        opvr_total=fmt_num(enpf["opvr"]["including_contribution_account"], 2),
        opvr_managed=fmt_num(enpf["opvr"]["managed"], 2),
        private_managers=fmt_num(enpf["private_managers"]["value"], 4),
    )


TEMPLATE = """
<p class="asset-nav" aria-label="Разделы этой страницы"><a href="#fund-structure">Нацфонд</a> · <a href="#children">Нацфонд — детям</a> · <a href="#reserves">Резервы НБК</a> · <a href="#enpf">ЕНПФ</a></p>
<section class="asset-section" id="fund-structure" aria-labelledby="fund-structure-title">
  <header><p class="eyebrow">Владелец: Республика Казахстан · управление: НБК</p><h2 id="fund-structure-title">Структура Национального фонда</h2><p class="section-note">Последнее полное годовое раскрытие на {annual_date}. Оно не выдаётся за структуру сентября 2026 года. Срез проверен {verified}.</p></header>
  <p class="scope-note">Основа диаграммы — валовые валютные портфели {gross} млрд USD. Золото уже входит в сберегательный портфель. Названия — инвестиционные мандаты, а не строгая классификация каждого эмитента.</p>
  <figure aria-labelledby="fund-composition-title"><figcaption id="fund-composition-title" class="eyebrow">Состав валовых валютных портфелей</figcaption><div class="bars">{composition}</div></figure>
  <div class="reconcile" aria-label="Сверка годового итога Нацфонда">
    <div>Валовые валютные портфели<strong>{gross} млрд USD</strong></div>
    <div>минус требования детей<strong>{claims} млрд USD</strong></div>
    <div>равно чистые валютные активы<strong>{net} млрд USD</strong></div>
    <div>плюс тенговые активы {domestic_total} млрд<strong>итого {total} млрд USD</strong></div>
  </div>
  <h3>Тенговые активы: оценки на {domestic_date}</h3>
  <p class="scope-note">Номинал, стоимость приобретения и справедливая стоимость — альтернативные оценки. Они показаны рядом, но не складываются.</p>
  <div class="valuation-grid">
    <article class="valuation-card"><strong>Долговые инструменты</strong><dl><dt>Номинал</dt><dd>{debt_nominal} млрд KZT</dd><dt>Справедливая стоимость</dt><dd>{debt_fair} млрд KZT</dd></dl></article>
    <article class="valuation-card"><strong>Долевые инструменты</strong><dl><dt>Стоимость приобретения</dt><dd>{equity_cost} млрд KZT</dd><dt>Справедливая стоимость</dt><dd>{equity_fair} млрд KZT</dd><dt>Остаток денег</dt><dd>{cash} млрд KZT</dd></dl></article>
  </div>
  <p class="source-line">Источники: <a href="{annual_source}">годовой отчёт НБК за 2025 год</a>; <a href="{domestic_source}">операции Нацфонда за сентябрь 2026 года</a>.</p>
</section>

<section class="asset-section" id="children" aria-labelledby="children-title">
  <header><p class="eyebrow">Получатели: дети — граждане Казахстана · оператор учёта: ЕНПФ</p><h2 id="children-title">«Нацфонд — детям»</h2><p class="section-note">Два остатка отражают разные стадии программы и разные даты. Поэтому радар намеренно не показывает их сумму.</p></header>
  <div class="metric-grid">
    <article class="metric metric--main"><p class="label">Целевые требования</p><p class="number">{child_claims}</p><p class="note">млрд USD на {child_claims_date}; обязательства Нацфонда</p></article>
    <article class="metric"><p class="label">Целевые накопления в ЕНПФ</p><p class="number">{child_savings}</p><p class="note">млрд USD на {child_savings_date}; другой остаток и дата</p></article>
    <article class="metric"><p class="label">Общего остатка</p><p class="number">нет</p><p class="note">складывать эти показатели некорректно</p></article>
  </div>
  <div class="flow-grid" aria-label="Исторические потоки программы">
    <div class="flow">Начислено с начала программы, приблизительно<strong>≈ {child_accrual} млрд USD</strong><span class="section-note">накопленный поток, не остаток</span></div>
    <div class="flow">Выплачено к 01.10.2026<strong>{child_payout} млрд USD</strong><span class="section-note">накопленный поток, не остаток</span></div>
  </div>
  <p class="source-line">Источник: <a href="{child_source}">официальная таблица ЕНПФ</a>; API и сверка НБК перечислены в открытом JSON страницы.</p>
</section>

<section class="asset-section" id="reserves" aria-labelledby="reserves-title">
  <header><p class="eyebrow">Владелец и управление: Национальный банк Казахстана</p><h2 id="reserves-title">Международные резервы НБК</h2><p class="section-note">Предварительный остаток на {reserves_date}. Это отдельный пул, не часть Нацфонда и не «свободные деньги государства».</p></header>
  <div class="metric-grid">
    <article class="metric metric--main"><p class="label">Валовые резервы</p><p class="number">{reserves_gross}</p><p class="note">млрд USD</p></article>
    <article class="metric"><p class="label">Чистые резервы</p><p class="number">{reserves_net}</p><p class="note">млрд USD</p></article>
    <article class="metric"><p class="label">Статус</p><p class="number">предв.</p><p class="note">компоненты округлены до 1 млн USD</p></article>
  </div>
  <figure aria-labelledby="reserves-chart"><figcaption id="reserves-chart" class="eyebrow">Состав валовых резервов</figcaption><div class="bars">
    <div class="bar-row"><span class="bar-label">Монетарное золото</span><span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:{gold_width:.4f}%"></span></span><span class="bar-value">{reserves_gold} млрд USD · {gold_share}%</span></div>
    <div class="bar-row bar-row--muted"><span class="bar-label">Свободно конвертируемая валюта</span><span class="bar-track" aria-hidden="true"><span class="bar-fill" style="width:{fx_width:.4f}%"></span></span><span class="bar-value">{reserves_fx} млрд USD · {fx_share}%</span></div>
  </div></figure>
  <p class="source-line">Источник: <a href="{reserves_source}">НБРК, международные резервы и активы</a>. Сумма компонентов отличается от валового итога на 1 млн USD из-за округления.</p>
</section>

<section class="asset-section" id="enpf" aria-labelledby="enpf-title">
  <header><p class="eyebrow">Владельцы: вкладчики ЕНПФ · управление показанного пула: НБК</p><h2 id="enpf-title">Пенсионные активы ЕНПФ</h2><p class="section-note">Основной график охватывает только ОПВ, ОППВ и ДПВ под управлением НБК на {enpf_date}. Это не весь ЕНПФ.</p></header>
  <div class="metric-grid">
    <article class="metric metric--main"><p class="label">Портфель под управлением НБК</p><p class="number">{enpf_total}</p><p class="note">млрд KZT; ОПВ / ОППВ / ДПВ</p></article>
    <article class="metric"><p class="label">Дата и единица</p><p class="number">KZT</p><p class="note">остаток на {enpf_date}</p></article>
    <article class="metric"><p class="label">Охват</p><p class="number">не весь</p><p class="note">ОПВР и частные управляющие показаны отдельно</p></article>
  </div>
  <figure aria-labelledby="enpf-chart"><figcaption id="enpf-chart" class="eyebrow">Шесть крупнейших строк портфеля</figcaption><div class="bars">{enpf_bars}</div></figure>
  <div class="separate-pools" aria-label="Отдельные пулы ЕНПФ">
    <div class="pool">ОПВР, включая взносный счёт<strong>{opvr_total} млрд KZT</strong><span class="section-note">из них под управлением {opvr_managed} млрд KZT</span></div>
    <div class="pool">Частные управляющие<strong>{private_managers} млрд KZT</strong><span class="section-note">отдельный пул; не добавлен к графику</span></div>
  </div>
  <details><summary>Все строки портфеля и сверка итога</summary><div class="details-body"><table class="data-table"><thead><tr><th>Категория</th><th>млрд KZT</th></tr></thead><tbody>{enpf_rows}</tbody><tfoot><tr><th>Итого</th><th>{enpf_total}</th></tr></tfoot></table><p>Индексное управление уже входит в итог и не добавляется повторно. Внешнее управление также нельзя считать отдельным дополнительным активом.</p></div></details>
  <p class="source-line">Источник: <a href="{enpf_source}">ЕНПФ, структура инвестиционного портфеля</a>, таблица 1, страница 1.</p>
</section>
"""
