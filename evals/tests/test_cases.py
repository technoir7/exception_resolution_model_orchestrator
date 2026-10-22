"""The benchmark's cases: each kind's right answer must follow from its documents."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

import pytest

from evals import cases

ALL = cases.generate(seed=1)


def of(kind):
    return [c for c in ALL if c["kind"] == kind]


def money(value) -> Decimal:
    return Decimal(value)


def lines_by_number(document):
    return {line["line_number"]: line for line in document["line_items"]}


class TestVendors:
    def test_sell_what_their_names_say(self):
        for case in ALL:
            descriptions = " ".join(l["description"] for l in case["po"]["line_items"])
            trade = next(t for t in cases.GOODS if t in case["vendor"]["name"]) if case["kind"] not in (
                "recurring_service", "unit_of_measure") else None
            if trade:
                assert all(l["description"] in [g[0] for g in cases.GOODS[trade]] for l in case["po"]["line_items"]), \
                    (case["id"], case["vendor"]["name"], descriptions)


class TestTheSet:
    def test_is_the_same_for_the_same_seed(self):
        assert cases.generate(seed=1) == ALL

    def test_differs_for_another_seed(self):
        assert cases.generate(seed=2) != ALL

    def test_has_the_planned_number_of_each_kind(self):
        assert Counter(c["kind"] for c in ALL) == cases.COUNTS

    def test_ids_and_invoice_numbers_are_unique(self):
        assert len({c["id"] for c in ALL}) == len(ALL)
        assert len({(c["invoice"]["vendor_id"], c["invoice"]["invoice_number"]) for c in ALL}) == len(ALL)

    def test_every_answer_is_pay_or_hold(self):
        for case in ALL:
            assert case["truth"]["decision"] == ("pay" if case["kind"] in cases.PAY else "hold")

    def test_each_case_has_its_own_vendor(self):
        """So one case's history can never make another look like a duplicate."""
        assert len({c["vendor"]["id"] for c in ALL}) == len(ALL)


class TestArithmetic:
    def test_lines_subtotals_and_totals_add_up(self):
        for case in ALL:
            for doc in [case["po"], case["invoice"], *case["history"]]:
                for line in doc["line_items"]:
                    assert money(line["amount"]) == money(line["unit_price"]) * line["quantity"], case["id"]
            inv = case["invoice"]
            assert money(inv["subtotal"]) == sum(money(l["amount"]) for l in inv["line_items"]), case["id"]
            assert money(inv["total_amount"]) == money(inv["subtotal"]) + money(inv["tax_amount"]), case["id"]
            assert money(case["po"]["total_amount"]) == sum(money(l["amount"]) for l in case["po"]["line_items"])


class TestPay:
    def test_clean_invoices_match_the_po_and_the_receipt(self):
        for case in of("clean"):
            assert case["invoice"]["line_items"] == case["po"]["line_items"]
            assert money(case["invoice"]["tax_amount"]) == 0
            received = {l["line_number"]: l["quantity"] for l in case["receipt"]["line_items"]}
            assert all(received[l["line_number"]] == l["quantity"] for l in case["po"]["line_items"])

    def test_a_partial_delivery_bills_what_was_received(self):
        for case in of("partial_delivery"):
            received = {l["line_number"]: l["quantity"] for l in case["receipt"]["line_items"]}
            ordered = lines_by_number(case["po"])
            billed = lines_by_number(case["invoice"])
            assert all(billed[n]["quantity"] == received[n] for n in billed)
            assert any(received[n] < ordered[n]["quantity"] for n in billed)

    def test_allowed_freight_is_within_the_cap(self):
        for case in of("freight_allowed"):
            terms = case["po"]["terms"]
            assert case["po"]["freight"] == {"billable": True, "cap": terms_cap(case)}
            assert 0 < freight(case) <= money(case["po"]["freight"]["cap"])

    def test_correct_tax_is_the_po_rate(self):
        for case in of("tax_correct"):
            rate = money(case["po"]["tax_rate"])
            assert rate > 0
            assert money(case["invoice"]["tax_amount"]) == (money(case["invoice"]["subtotal"]) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def test_a_weekly_service_bills_a_new_week(self):
        for case in of("recurring_service"):
            [previous] = case["history"]
            assert previous["service_period"] != case["invoice"]["service_period"]
            assert money(previous["total_amount"]) == money(case["invoice"]["total_amount"])
            assert (date(case["invoice"]["invoice_date"]) - date(previous["invoice_date"])).days == 7

    def test_a_unit_of_measure_difference_bills_the_same_goods(self):
        for case in of("unit_of_measure"):
            [po_line] = case["po"]["line_items"]
            [inv_line] = case["invoice"]["line_items"]
            pack = po_line["pack_size"]
            assert inv_line["quantity"] == po_line["quantity"] * pack
            assert money(inv_line["amount"]) == money(po_line["amount"])


class TestHold:
    def test_a_price_increase_is_not_on_the_po(self):
        for case in of("price_increase"):
            ordered = lines_by_number(case["po"])
            assert any(money(l["unit_price"]) > money(ordered[l["line_number"]]["unit_price"])
                       for l in case["invoice"]["line_items"])

    def test_overbilling_charges_for_more_than_was_received(self):
        for case in of("overbilled_quantity"):
            received = {l["line_number"]: l["quantity"] for l in case["receipt"]["line_items"]}
            assert any(l["quantity"] > received[l["line_number"]] for l in case["invoice"]["line_items"])

    def test_a_duplicate_repeats_a_paid_invoice(self):
        for case in of("duplicate") + of("duplicate_late"):
            paid = original(case)
            assert paid["total_amount"] == case["invoice"]["total_amount"]
            assert paid["po_number"] == case["invoice"]["po_number"]

    def test_a_late_duplicate_falls_outside_the_rules_window(self):
        for case in of("duplicate_late"):
            assert (date(case["invoice"]["invoice_date"]) - date(original(case)["invoice_date"])).days > 7

    def test_only_a_duplicates_history_holds_the_same_lines(self):
        for case in ALL:
            if case["kind"] not in ("duplicate", "duplicate_late"):
                assert all(h["line_items"] != case["invoice"]["line_items"] for h in case["history"]), case["id"]

    def test_disallowed_freight_breaks_the_po_terms(self):
        for case in of("freight_not_allowed"):
            po_freight = case["po"]["freight"]
            assert freight(case) > 0
            assert not po_freight["billable"] or freight(case) > money(po_freight["cap"])

    def test_wrong_tax_is_not_the_po_rate(self):
        for case in of("tax_wrong"):
            expected = (money(case["invoice"]["subtotal"]) * money(case["po"]["tax_rate"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            assert money(case["invoice"]["tax_amount"]) != expected

    def test_a_bank_change_pays_another_account(self):
        for case in of("bank_change"):
            assert case["invoice"]["remit_to"] != case["vendor"]["remit_to"]

    def test_everyone_else_pays_the_account_on_file(self):
        for case in ALL:
            if case["kind"] != "bank_change":
                assert case["invoice"]["remit_to"] == case["vendor"]["remit_to"], case["id"]

    def test_a_vendor_mismatch_bills_someone_elses_po(self):
        for case in of("vendor_mismatch"):
            assert case["invoice"]["vendor_id"] != case["po"]["vendor_id"]


def original(case):
    [paid] = [h for h in case["history"] if h["line_items"] == case["invoice"]["line_items"]]
    return paid


def freight(case) -> Decimal:
    return sum((money(l["amount"]) for l in case["invoice"]["line_items"] if l.get("is_freight")), Decimal(0))


def terms_cap(case) -> str:
    return case["po"]["freight"]["cap"]


def date(text):
    from datetime import date as _date
    return _date.fromisoformat(text)


@pytest.mark.asyncio
async def test_the_rules_flag_exactly_the_kinds_meant_to_be_flagged(db_session):
    """The benchmark's split between invoices the rules pass and those they
    flag must be what the rules really do, not what the generator assumes."""
    from evals import seed
    from apps.api.services.flags import flags_for
    from apps.api.tests.conftest import TEST_TENANT_ID

    invoices = await seed.load(db_session, TEST_TENANT_ID, ALL)
    wrong = []
    for case in ALL:
        raised = await flags_for(db_session, TEST_TENANT_ID, invoices[case["id"]], today=cases.AS_OF)
        if bool(raised) != (case["kind"] in cases.FLAGGED):
            wrong.append((case["id"], case["kind"], raised))
    assert not wrong, wrong[:5]
