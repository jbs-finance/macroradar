"""Static dataset-level registry for the published Macro Radar artifacts.

This is an inventory contract, not a freshness evaluator. Cadence labels describe
the source cadence documented by the current collector; they do not define a
freshness threshold.
"""

from __future__ import annotations

REQUIRED_IDS = frozenset(
    {
        "macroradar.pulse",
        "macroradar.radar",
        "macroradar.trade",
        "macroradar.national_fund",
        "macroradar.tax_budget",
        "macroradar.tax_minfin",
        "macroradar.tax_rates",
        "macroradar.oblast_budget",
    }
)
FRESHNESS_STATUSES = frozenset({"proposed", "manual_review", "existing_ad_hoc"})

SOURCE_REGISTRY = (
    {
        "dataset_id": "macroradar.pulse",
        "collector": "etl.py",
        "sources": (
            {
                "source_id": "world_bank",
                "canonical_url": "https://api.worldbank.org/v2",
                "cadence": "annual",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "nbk_rss",
                "canonical_url": "https://nationalbank.kz/rss/get_rates.cfm",
                "cadence": "daily",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "bns_taldau",
                "canonical_url": "https://taldau.stat.gov.kz",
                "cadence": "mixed",
                "freshness_status": "existing_ad_hoc",
            },
        ),
    },
    {
        "dataset_id": "macroradar.radar",
        "collector": "radar.py",
        "sources": (
            {
                "source_id": "nbk",
                "canonical_url": "https://nationalbank.kz",
                "cadence": "mixed",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "bns",
                "canonical_url": "https://stat.gov.kz",
                "cadence": "monthly",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "world_bank",
                "canonical_url": "https://api.worldbank.org/v2",
                "cadence": "annual",
                "freshness_status": "existing_ad_hoc",
            },
        ),
    },
    {
        "dataset_id": "macroradar.trade",
        "collector": "trade.py",
        "sources": (
            {
                "source_id": "world_bank",
                "canonical_url": "https://api.worldbank.org/v2",
                "cadence": "annual",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "un_comtrade_preview",
                "canonical_url": "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
                "cadence": "annual",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "un_comtrade_partners",
                "canonical_url": "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json",
                "cadence": "reference",
                "freshness_status": "existing_ad_hoc",
            },
        ),
    },
    {
        "dataset_id": "macroradar.national_fund",
        "collector": "national_fund.py",
        "sources": (
            {
                "source_id": "nbk_assets",
                "canonical_url": (
                    "https://nationalbank.kz/ru/international-reserve-and-asset/"
                    "mezhdunarodnye-rezervy-i-aktivy-nacionalnogo-fonda-rk"
                ),
                "cadence": "mixed",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "nbk_returns",
                "canonical_url": "https://nationalbank.kz/ru/page/NF-investment-management",
                "cadence": "mixed",
                "freshness_status": "existing_ad_hoc",
            },
        ),
    },
    {
        "dataset_id": "macroradar.tax_budget",
        "collector": "budget.py",
        "sources": (
            {
                "source_id": "kgd_dynamics",
                "canonical_url": "https://kgd.gov.kz/ru/content/dinamika-postupleniy-nalogov-i-platezhey-v-gosudarstvennyy-byudzhet-1",
                "cadence": "monthly",
                "freshness_status": "existing_ad_hoc",
            },
            {
                "source_id": "kgd_facts",
                "canonical_url": "https://kgd.gov.kz/ru/content/fakticheskie-postupleniya-po-nalogam-i-platezham-v-gosudarstvennyy-byudzhet-za-2002-2025-gg",
                "cadence": "monthly",
                "freshness_status": "existing_ad_hoc",
            },
        ),
    },
    {
        "dataset_id": "macroradar.tax_minfin",
        "collector": "minfin.py",
        "sources": (
            {
                "source_id": "minfin_gov_kz",
                "canonical_url": "https://www.gov.kz/memleket/entities/minfin/activities/448?lang=ru",
                "cadence": "monthly",
                "freshness_status": "existing_ad_hoc",
            },
        ),
    },
    {
        "dataset_id": "macroradar.tax_rates",
        "collector": "tax.py",
        "sources": (
            {
                "source_id": "tax_code",
                "canonical_url": "",
                "cadence": "manual",
                "freshness_status": "manual_review",
            },
        ),
    },
    {
        "dataset_id": "macroradar.oblast_budget",
        "collector": "oblast.py",
        "sources": (
            {
                "source_id": "minfin_gov_kz",
                "canonical_url": "https://www.gov.kz/api/v1/public/content-manager/documents?activities=7294&size=2000",
                "cadence": "monthly",
                "freshness_status": "existing_ad_hoc",
            },
        ),
    },
)
