"""Versioned official disclosures used by the National Fund dashboard."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from etl import SourceError

HERE = Path(__file__).resolve().parent
DEFAULT_DISCLOSURE = (
    HERE / "data" / "history" / "national_assets" / "2026-10-25.json"
)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _require_date(value: object, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SourceError(f"официальный срез: неверная дата {label}")


def _equal(actual: Decimal, expected: Decimal, label: str, tolerance: Decimal = Decimal("0")) -> None:
    if abs(actual - expected) > tolerance:
        raise SourceError(
            f"официальный срез: не сошлась сверка {label}: {actual} != {expected}"
        )


def validate_disclosures(data: dict) -> dict:
    """Fail closed when an edited disclosure breaks an accounting identity."""
    if data.get("schema_version") != 1 or data.get("status") != "official_disclosures":
        raise SourceError("официальный срез: неподдерживаемая схема")

    fund = data["national_fund"]
    annual = fund["annual_2025"]
    _require_date(annual["as_of"], "Нацфонда")
    savings_sum = sum(
        (_decimal(row["value"]) for row in annual["savings_components"]),
        Decimal("0"),
    )
    _equal(savings_sum, _decimal(annual["savings_portfolio"]), "сберегательного портфеля")
    _equal(
        _decimal(annual["stabilization_portfolio"])
        + _decimal(annual["savings_portfolio"]),
        _decimal(annual["gross_foreign_portfolios"]),
        "валовых валютных портфелей",
    )
    _equal(
        _decimal(annual["gross_foreign_portfolios"])
        - _decimal(annual["children_claims"]),
        _decimal(annual["net_foreign_assets"]),
        "чистых валютных активов",
    )
    _equal(
        _decimal(annual["net_foreign_assets"])
        + _decimal(annual["domestic_securities_usd_equivalent"])
        + _decimal(annual["domestic_cash_usd_equivalent"]),
        _decimal(annual["total_market_value"]),
        "общего рыночного итога Нацфонда",
    )

    domestic = fund["domestic_monthly"]
    _require_date(fund["monthly"]["as_of"], "месячного Нацфонда")
    _require_date(domestic["as_of"], "тенговых активов Нацфонда")
    if domestic["debt_nominal"] == domestic["debt_fair_value"]:
        raise SourceError("официальный срез: потеряно различие оценок долговых активов")
    if domestic["equity_cost"] == domestic["equity_fair_value"]:
        raise SourceError("официальный срез: потеряно различие оценок долевых активов")

    children = data["children"]
    _require_date(children["claims"]["as_of"], "детских требований")
    _require_date(children["enpf_target_savings"]["as_of"], "детских накоплений ЕНПФ")
    if children["claims"]["as_of"] == children["enpf_target_savings"]["as_of"]:
        raise SourceError("официальный срез: разные остатки ошибочно приведены к одной дате")
    if not str(children["historical_accrual_approx"]["basis"]).endswith("approximate"):
        raise SourceError("официальный срез: приблизительный поток не помечен")

    reserves = data["nbk_reserves"]
    _require_date(reserves["as_of"], "резервов НБК")
    _equal(
        _decimal(reserves["gold"]) + _decimal(reserves["foreign_currency"]),
        _decimal(reserves["gross"]),
        "валовых резервов НБК (округление)",
        Decimal("1"),
    )

    enpf = data["enpf"]
    portfolio = enpf["nbk_managed"]
    _require_date(portfolio["as_of"], "портфеля ЕНПФ")
    enpf_sum = sum(
        (_decimal(row["value"]) for row in portfolio["components"]), Decimal("0")
    )
    _equal(enpf_sum, _decimal(portfolio["total"]), "портфеля ЕНПФ")
    if portfolio["basis"] != "stock_opv_oppv_dpv_managed_by_nbk":
        raise SourceError("официальный срез: неверно обозначен охват портфеля ЕНПФ")
    if enpf["opvr"]["basis"] != "separate_pool" or enpf["private_managers"]["basis"] != "separate_pool":
        raise SourceError("официальный срез: отдельные пулы ЕНПФ не помечены")
    return data


def load_disclosures(path: Path = DEFAULT_DISCLOSURE) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceError(f"официальный срез не читается: {exc}") from exc
    return validate_disclosures(data)
