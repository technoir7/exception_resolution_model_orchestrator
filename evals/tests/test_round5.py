"""Round 5's cases: terms that live in the vendor's documents, not on the PO.
Each kind's right answer must follow from those documents."""

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from evals import cases, library

ALL = cases.generate(seed=5, counts=cases.COUNTS_5, documents=True)
MANUAL_IDS = {p["id"] for p in library.manual()}


def of(kind):
    return [c for c in ALL if c["kind"] == kind]


def d(text):
    return date.fromisoformat(text)


def passage(case, pid):
    return next(p for p in case["documents"] + library.manual() if p["id"] == pid)


def billed_price(case, item):
    [line] = [l for l in case["invoice"]["line_items"] if l["description"] == item]
    return Decimal(line["unit_price"])


def po_price(case, item):
    [line] = [l for l in case["po"]["line_items"] if l["description"] == item]
    return Decimal(line["unit_price"])


def pricing_clause(case) -> str:
    return f"{case['vendor']['id']}-msa-4"


def fee(case) -> Decimal:
    return sum((Decimal(l["amount"]) for l in case["invoice"]["line_items"] if l.get("is_fee")), Decimal(0))


def freight(case) -> Decimal:
    return sum((Decimal(l["amount"]) for l in case["invoice"]["line_items"] if l.get("is_freight")), Decimal(0))


class TestTheSet:
    def test_has_the_planned_number_of_each_kind(self):
        assert Counter(c["kind"] for c in ALL) == cases.COUNTS_5

    def test_is_the_same_for_the_same_seed(self):
        assert cases.generate(seed=5, counts=cases.COUNTS_5, documents=True) == ALL

    def test_answers_follow_the_kind(self):
        for c in ALL:
            assert c["truth"]["decision"] == ("pay" if c["kind"] in cases.PAY else "hold")

    def test_each_case_has_its_own_vendor(self):
        assert len({c["vendor"]["id"] for c in ALL}) == len(ALL)

    def test_lines_and_totals_add_up(self):
        for c in ALL:
            for doc in [c["po"], c["invoice"]]:
                for line in doc["line_items"]:
                    assert Decimal(line["amount"]) == Decimal(line["unit_price"]) * line["quantity"], c["id"]
            inv = c["invoice"]
            assert Decimal(inv["subtotal"]) == sum(Decimal(l["amount"]) for l in inv["line_items"])
            assert Decimal(inv["total_amount"]) == Decimal(inv["subtotal"]) + Decimal(inv["tax_amount"])


class TestTheDocuments:
    def test_the_po_refers_to_the_agreement_and_states_no_terms_of_its_own(self):
        for c in ALL:
            terms = c["po"]["terms"]
            assert c["msa"] in terms, c["id"]
            for leak in ("$", "freight is", "cap", "fixed", "tax"):
                assert leak not in terms.lower(), (c["id"], terms)

    def test_every_vendor_has_a_full_agreement(self):
        for c in ALL:
            clauses = [p for p in c["documents"] if p["source"] == "agreement"]
            assert len(clauses) == 24, c["id"]
            assert all(c["msa"] in p["title"] for p in clauses)

    def test_passage_ids_are_unique_across_the_library(self):
        ids = [p["id"] for c in ALL for p in c["documents"]] + list(MANUAL_IDS)
        assert len(ids) == len(set(ids))

    def test_the_deciding_passages_exist(self):
        for c in ALL:
            for pid in c["deciding"]:
                assert passage(c, pid), (c["id"], pid)

    def test_only_kinds_decided_by_the_documents_name_deciding_passages(self):
        for c in ALL:
            assert bool(c["deciding"]) == (c["kind"] not in cases.UNDECIDED_5), c["id"]

    def test_no_other_amendment_changes_a_price_the_invoice_bills(self):
        for c in ALL:
            billed = {l["description"] for l in c["invoice"]["line_items"]}
            own = {change["id"] for change in c["terms"]["price_changes"]}
            for p in c["documents"]:
                if p["source"] == "amendment" and "unit price" in p["text"] and p["id"] not in own:
                    assert not any(f'"{item}"' in p["text"] for item in billed), (c["id"], p["text"])

    def test_the_manual_asks_nothing_the_review_cannot_see(self):
        """The review is not shown the vendor's tax ID on the invoice."""
        assert all("tax ID" not in p["text"] for p in library.manual())

    def test_the_manual_says_how_rush_fees_are_paid(self):
        rush = next(p for p in library.manual() if p["id"] == library.RUSH)
        assert "in writing" in rush["text"] and "phone is not enough" in rush["text"]


class TestFreight:
    def test_freight_within_the_cap(self):
        for c in of("msa_freight_within_cap"):
            clause = passage(c, c["deciding"][0])
            assert c["terms"]["freight"]["cap"] in clause["text"]
            assert 0 < freight(c) <= Decimal(c["terms"]["freight"]["cap"])

    def test_freight_under_delivered_pricing(self):
        for c in of("msa_freight_not_allowed"):
            clause = passage(c, c["deciding"][0])
            assert clause["text"] == library.FREIGHT_INCLUDED
            assert freight(c) > 0

    def test_only_the_freight_kinds_bill_freight(self):
        for c in ALL:
            if not c["kind"].startswith("msa_freight"):
                assert freight(c) == 0, c["id"]


class TestPrices:
    def changes(self, c):
        return sorted(c["terms"]["price_changes"], key=lambda x: x["effective"])

    def test_a_price_rise_in_effect(self):
        for c in of("amended_price_in_effect"):
            [change] = self.changes(c)
            assert d(change["effective"]) <= d(c["invoice"]["invoice_date"])
            assert d(c["po"]["po_date"]) < d(change["effective"])
            assert billed_price(c, change["item"]) == Decimal(change["price"]) > po_price(c, change["item"])
            assert c["deciding"] == [change["id"], pricing_clause(c)]

    def test_a_price_rise_not_yet_in_effect(self):
        for c in of("amended_price_not_yet"):
            [change] = self.changes(c)
            assert d(change["effective"]) > d(c["invoice"]["invoice_date"])
            assert billed_price(c, change["item"]) == Decimal(change["price"]) > po_price(c, change["item"])

    def test_the_latest_amendments_price(self):
        for c in of("latest_amended_price"):
            first, latest = self.changes(c)
            assert first["item"] == latest["item"]
            assert d(c["po"]["po_date"]) < d(latest["effective"]) <= d(c["invoice"]["invoice_date"])
            assert po_price(c, first["item"]) == Decimal(first["price"]) != Decimal(latest["price"])
            assert billed_price(c, latest["item"]) == Decimal(latest["price"])
            assert c["deciding"] == [latest["id"], pricing_clause(c)]

    def test_a_superseded_price(self):
        for c in of("superseded_price"):
            first, latest = self.changes(c)
            assert d(latest["effective"]) <= d(c["invoice"]["invoice_date"])
            assert Decimal(latest["price"]) < Decimal(first["price"]) == billed_price(c, first["item"])
            assert c["deciding"] == [latest["id"], pricing_clause(c)]

    def test_the_pricing_clause_says_when_an_amendment_applies(self):
        for c in of("amended_price_not_yet"):
            assert "invoiced on or after the amendment's effective date" in passage(c, pricing_clause(c))["text"]

    def test_each_amendment_says_what_the_terms_say(self):
        for c in ALL:
            for change in c["terms"]["price_changes"]:
                text = passage(c, change["id"])
                assert f'"{change["item"]}" is ${change["price"]}' in text["text"]
                assert text["dated"] == change["effective"]


class TestRushFees:
    def test_an_approved_fee_has_purchasings_written_approval_for_this_po(self):
        for c in of("rush_fee_approved"):
            approval = passage(c, c["deciding"][0])
            assert approval["source"] == "email" and library.BUYER_MAIL in approval["title"].split(" to ")[0]
            assert c["po"]["po_number"] in approval["text"] and f"${fee(c)}" in approval["text"]
            assert d(approval["dated"]) < d(c["receipt"]["receipt_date"])
            assert library.RUSH in c["deciding"]

    def test_an_unapproved_fee_has_no_such_approval(self):
        for c in of("rush_fee_unapproved"):
            assert c["deciding"] == [library.RUSH]
            for p in c["documents"]:
                if p["source"] == "email" and p["title"].split(" to ")[0].endswith(library.BUYER_MAIL):
                    assert not ("Approved" in p["text"] and c["po"]["po_number"] in p["text"]), p

    def test_unapproved_fees_come_in_several_forms(self):
        assert len({c["terms"]["rush"]["form"] for c in of("rush_fee_unapproved")}) == 4

    def test_only_the_rush_kinds_bill_a_fee(self):
        for c in ALL:
            if not c["kind"].startswith("rush_fee"):
                assert fee(c) == 0, c["id"]


class TestControls:
    def test_one_over_bills_one_unit_more_than_received(self):
        for c in of("one_over"):
            received = {l["line_number"]: l["quantity"] for l in c["receipt"]["line_items"]}
            assert sum(l["quantity"] - received[l["line_number"]] for l in c["invoice"]["line_items"]) == 1

    def test_a_small_price_rise_has_no_amendment(self):
        for c in of("small_price_increase"):
            assert not c["terms"]["price_changes"]
            ordered = {l["line_number"]: Decimal(l["unit_price"]) for l in c["po"]["line_items"]}
            assert any(Decimal(l["unit_price"]) > ordered[l["line_number"]] for l in c["invoice"]["line_items"])


@pytest.mark.asyncio
async def test_the_rules_flag_exactly_the_kinds_meant_to_be_flagged(db_session):
    from apps.api.services.flags import flags_for
    from apps.api.tests.conftest import TEST_TENANT_ID
    from evals import seed

    invoices = await seed.load(db_session, TEST_TENANT_ID, ALL)
    wrong = []
    for c in ALL:
        raised = await flags_for(db_session, TEST_TENANT_ID, invoices[c["id"]], today=cases.AS_OF)
        if bool(raised) != (c["kind"] in cases.FLAGGED):
            wrong.append((c["id"], c["kind"], raised))
    assert not wrong, wrong[:5]
