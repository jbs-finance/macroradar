"""Тесты налогового справочника: пересчёт из МРП, полнота позиций, оговорки."""

import re

import pytest

import tax
from build_tax import build
from tax import BASE, GROUPS, MRP, MZP, money, mrp, mzp, validate

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


class TestDerivedValues:
    """Величины в МРП считаются, а не вбиваются: это главная защита от опечатки."""

    def test_known_thresholds_match_official_values(self):
        assert mrp(30) == 129_750
        assert mrp(10_000) == 43_250_000
        assert mrp(8_500) == 36_762_500
        assert mzp(50) == 4_250_000
        assert mzp(20) == 1_700_000
        assert mzp(40) == 3_400_000

    def test_base_constants_are_2026_values(self):
        assert MRP == 4325
        assert MZP == 85000

    def test_money_uses_nonbreaking_space(self):
        assert money(43_250_000) == "43 250 000 тг"

    def test_thresholds_follow_mrp_change(self):
        """При смене МРП производные обязаны поехать следом, иначе они захардкожены."""
        assert mrp(10_000) == MRP * 10_000


class TestValidate:
    def data(self, **over):
        d = tax.build()
        d.update(over)
        return d

    def test_valid_reference_passes(self):
        assert validate(self.data()) == []

    def test_position_without_value_rejected(self):
        d = self.data()
        d["groups"] = [
            {"id": "vat", "title": "НДС", "items": [{"name": "Ставка", "value": ""}]}
        ]
        assert any("без имени или значения" in p for p in validate(d))

    def test_base_without_legal_basis_rejected(self):
        d = self.data()
        d["base"] = [{"name": "МРП", "value": "4 325 тг", "basis": ""}]
        assert any("без значения или основания" in p for p in validate(d))

    def test_duplicate_position_rejected(self):
        d = self.data()
        d["groups"] = [
            {
                "id": "vat",
                "title": "НДС",
                "items": [
                    {"name": "Ставка", "value": "16%"},
                    {"name": "Ставка", "value": "12%"},
                ],
            }
        ]
        assert any("повторяется" in p for p in validate(d))

    def test_empty_group_rejected(self):
        d = self.data()
        d["groups"] = [{"id": "vat", "title": "НДС", "items": []}]
        assert any("без позиций" in p for p in validate(d))

    def test_future_review_date_rejected(self):
        assert any(
            "в будущем" in p for p in validate(self.data(reviewed_at="2030-01-01"))
        )

    def test_broken_review_date_rejected(self):
        assert any(
            "даты ревизии" in p for p in validate(self.data(reviewed_at="вчера"))
        )


class TestContent:
    def test_key_2026_rates_present(self):
        page = build(tax.build())
        for value in ["16%", "20%", "10%", "6%", "3,5%", "4%"]:
            assert value in page

    def test_vat_rate_is_not_the_old_one(self):
        """Ставка 12% действовала до 2026 и в справочнике может быть только как пометка."""
        vat = next(g for g in GROUPS if g["id"] == "vat")
        standard = next(i for i in vat["items"] if i["name"] == "Стандартная ставка")
        assert standard["value"] == "16%"
        assert "12%" in standard["was"]

    def test_social_tax_has_no_deduction_of_social_contributions(self):
        social = next(g for g in GROUPS if g["id"] == "social")
        item = next(i for i in social["items"] if "юрлиц" in i["name"])
        assert "ОПВ и ВОСМС" in item["value"]
        assert "отменён" in item["was"]

    def test_base_block_covers_mrp_mzp_and_thresholds(self):
        names = " ".join(i["name"] for i in BASE)
        assert "МРП" in names and "МЗП" in names and "НДС" in names


class TestPage:
    def page(self):
        return build(tax.build())

    def test_self_contained_and_scriptless(self):
        page = self.page()
        assert not re.search(r'<(img|link|script)[^>]+(src|href)="https?://(?!jbs\.finance)', page)
        assert "<script" not in page
        assert "{{" not in page and ":root {" in page

    def test_noindex_present(self):
        assert 'rel="canonical" href="https://jbs.finance/macroradar/tax/"' in self.page()
        assert "noindex" not in self.page()

    def test_disclaimer_is_present_and_explicit(self):
        """Публиковать ставки без оговорки об ответственности нельзя."""
        page = self.page()
        assert "не налоговая консультация" in page
        assert "Ответственность за поданную отчётность" in page

    def test_review_date_shown(self):
        assert "Сверено с первоисточниками" in self.page()

    def test_no_dashes_in_visible_text(self):
        page = self.page()
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<style.*?</style>", "", page))
        assert EM_DASH not in visible and EN_DASH not in visible

    def test_escapes_markup_in_values(self):
        data = tax.build()
        data["groups"][0]["items"][0]["name"] = "<script>x</script>"
        assert "<script>" not in build(data)
