from source_registry import FRESHNESS_STATUSES, REQUIRED_IDS, SOURCE_REGISTRY

EXPECTED_SOURCE_URLS = {
    ("macroradar.pulse", "world_bank"): "https://api.worldbank.org/v2",
    ("macroradar.pulse", "nbk_rss"): "https://nationalbank.kz/rss/get_rates.cfm",
    ("macroradar.pulse", "bns_taldau"): "https://taldau.stat.gov.kz",
    ("macroradar.radar", "nbk"): "https://nationalbank.kz",
    ("macroradar.radar", "bns"): "https://stat.gov.kz",
    ("macroradar.radar", "world_bank"): "https://api.worldbank.org/v2",
    ("macroradar.trade", "world_bank"): "https://api.worldbank.org/v2",
    (
        "macroradar.trade",
        "un_comtrade_preview",
    ): "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
    (
        "macroradar.trade",
        "un_comtrade_partners",
    ): "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json",
    (
        "macroradar.national_fund",
        "nbk_assets",
    ): "https://nationalbank.kz/ru/international-reserve-and-asset/mezhdunarodnye-rezervy-i-aktivy-nacionalnogo-fonda-rk",
    (
        "macroradar.national_fund",
        "nbk_returns",
    ): "https://nationalbank.kz/ru/page/NF-investment-management",
    (
        "macroradar.tax_budget",
        "kgd_dynamics",
    ): "https://kgd.gov.kz/ru/content/dinamika-postupleniy-nalogov-i-platezhey-v-gosudarstvennyy-byudzhet-1",
    (
        "macroradar.tax_budget",
        "kgd_facts",
    ): "https://kgd.gov.kz/ru/content/fakticheskie-postupleniya-po-nalogam-i-platezham-v-gosudarstvennyy-byudzhet-za-2002-2025-gg",
    (
        "macroradar.tax_minfin",
        "minfin_gov_kz",
    ): "https://www.gov.kz/memleket/entities/minfin/activities/448?lang=ru",
    (
        "macroradar.oblast_budget",
        "minfin_gov_kz",
    ): "https://www.gov.kz/api/v1/public/content-manager/documents?activities=7294&size=2000",
}


def test_registry_covers_exactly_required_datasets():
    dataset_ids = [record["dataset_id"] for record in SOURCE_REGISTRY]

    assert set(dataset_ids) == REQUIRED_IDS
    assert len(dataset_ids) == len(set(dataset_ids))


def test_records_and_sources_have_required_nonempty_fields():
    for record in SOURCE_REGISTRY:
        assert record["dataset_id"].strip()
        assert record["collector"].strip()
        assert record["sources"]

        for source in record["sources"]:
            assert source["source_id"].strip()
            assert source["cadence"].strip()
            assert source["freshness_status"] in FRESHNESS_STATUSES
            assert isinstance(source["canonical_url"], str)
            if not source["canonical_url"]:
                assert source["freshness_status"] == "manual_review"


def test_source_ids_are_unique_within_each_dataset():
    for record in SOURCE_REGISTRY:
        source_ids = [source["source_id"] for source in record["sources"]]
        assert len(source_ids) == len(set(source_ids))


def test_nonempty_canonical_urls_match_pinned_source_pages():
    actual_urls = {
        (record["dataset_id"], source["source_id"]): source["canonical_url"]
        for record in SOURCE_REGISTRY
        for source in record["sources"]
        if source["canonical_url"]
    }

    assert actual_urls == EXPECTED_SOURCE_URLS
