import copy

import pytest

from etl import SourceError
from national_assets_block import build_assets_blocks
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
    assert "USD" in page and "KZT" in page
    assert "накопленный поток, не остаток" in page
    assert "Это не весь ЕНПФ" in page
    assert "Общего остатка" in page
    assert "Индексное управление уже входит в итог" in page
