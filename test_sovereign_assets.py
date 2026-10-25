import copy

import pytest

from etl import SourceError
from national_assets_block import build_assets_blocks, kzt_billions_to_usd_billions
from sovereign_assets import load_disclosures, validate_disclosures


def test_official_snapshot_reconciles_every_published_total():
    data = load_disclosures()
    annual = data["national_fund"]["annual_2025"]
    assert sum(row["value"] for row in annual["savings_components"]) == annual["savings_portfolio"]
    assert annual["gross_foreign_portfolios"] - annual["children_claims"] == annual["net_foreign_assets"]
    assert (
        annual["net_foreign_assets"]
        + annual["domestic_securities_usd_equivalent"]
        + annual["domestic_cash_usd_equivalent"]
        == annual["total_market_value"]
    )
    enpf = data["enpf"]["nbk_managed"]
    assert sum(row["value"] for row in enpf["components"]) == pytest.approx(enpf["total"])
    reserves = data["nbk_reserves"]
    assert abs(reserves["gold"] + reserves["foreign_currency"] - reserves["gross"]) <= 1


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("national_fund", "annual_2025", "net_foreign_assets"), 1, "чистых валютных активов"),
        (("nbk_reserves", "gross"), 1, "валовых резервов"),
        (("enpf", "nbk_managed", "total"), 1, "портфеля ЕНПФ"),
    ],
)
def test_accounting_changes_fail_closed(path, replacement, message):
    data = copy.deepcopy(load_disclosures())
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(SourceError, match=message):
        validate_disclosures(data)


def test_different_dates_and_valuations_cannot_silently_collapse():
    data = copy.deepcopy(load_disclosures())
    children = data["children"]
    children["enpf_target_savings"]["as_of"] = children["claims"]["as_of"]
    with pytest.raises(SourceError, match="разные остатки"):
        validate_disclosures(data)

    data = copy.deepcopy(load_disclosures())
    domestic = data["national_fund"]["domestic_monthly"]
    domestic["debt_fair_value"] = domestic["debt_nominal"]
    with pytest.raises(SourceError, match="различие оценок"):
        validate_disclosures(data)


def test_rendered_blocks_expose_owner_date_unit_and_no_false_total():
    page = build_assets_blocks(load_disclosures())
    assert "Владелец: Республика Казахстан" in page
    assert "Владелец и управление: Национальный банк Казахстана" in page
    assert "Владельцы: вкладчики ЕНПФ" in page
    assert "31.12.2025" in page and "30.09.2026" in page and "01.10.2026" in page
    assert "$" in page
    assert " USD" not in page and " KZT" not in page
    assert "накопленный поток; текущий остаток считается отдельно" in page
    assert "Другие пулы показаны ниже" in page
    assert "Сводная сумма" in page
    assert "Индексное управление уже входит в итог" in page
    assert "Средства, начисленные детям" in page
    assert "обязательства по целевым требованиям" in page
    assert "минус требования детей" not in page
    assert "равно чистые валютные активы" not in page


def test_historical_fx_rates_and_conversion_are_date_bound():
    data = load_disclosures()
    assert data["fx_rates"]["2025-12-31"]["kzt_per_usd"] == 505.53
    assert data["fx_rates"]["2026-09-30"]["kzt_per_usd"] == 439.37
    assert data["fx_rates"]["2026-10-01"]["kzt_per_usd"] == 440.86
    assert kzt_billions_to_usd_billions(3378, 439.37) == pytest.approx(7.6882809477)
    assert kzt_billions_to_usd_billions(26633.21, 440.86) == pytest.approx(60.4119448351)


def test_missing_or_misdated_fx_rate_fails_closed():
    data = copy.deepcopy(load_disclosures())
    del data["fx_rates"]["2026-10-01"]
    with pytest.raises((SourceError, KeyError), match="курс|2026-10-01"):
        validate_disclosures(data)


def test_main_money_cards_and_charts_use_dollar_sign_before_numbers():
    page = build_assets_blocks(load_disclosures())
    assert "$65,39 млрд" in page
    assert "$60,41" in page
    assert "$7,69 млрд" in page
    assert "$161,06" in page and "млн" in page
    assert "млрд USD" not in page
    assert "млрд KZT" not in page


def test_bar_layout_uses_one_shared_grid_and_mobile_reflows_without_fixed_tracks():
    page = build_assets_blocks(load_disclosures())
    assert 'class="bars"' in page
    assert 'class="bar-row"' in page
    from national_assets_block import BLOCK_STYLE

    assert "grid-template-columns: subgrid" in BLOCK_STYLE
    assert "grid-column: 1 / -1" in BLOCK_STYLE
    assert "@media (max-width: 520px)" in BLOCK_STYLE
    assert "white-space: normal" in BLOCK_STYLE
