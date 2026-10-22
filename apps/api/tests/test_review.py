"""What the model reviewing an invoice is shown, and how its answer is read."""

from decimal import Decimal

import pytest

from apps.api.services import review
from apps.api.services.case_file import case_file_for
from apps.api.tests.conftest import TEST_TENANT_ID
from evals import cases, seed

ALL = cases.generate(seed=1)


def first(kind):
    return next(c for c in ALL if c["kind"] == kind)


async def prompt_for(db_session, case):
    invoices = await seed.load(db_session, TEST_TENANT_ID, [case])
    file = await case_file_for(db_session, TEST_TENANT_ID, invoices[case["id"]], today=cases.AS_OF)
    return file, review.prompt(file)


class TestWhatTheModelIsShown:
    async def test_the_po_terms_and_lines(self, db_session):
        case = first("freight_not_allowed")
        _, text = await prompt_for(db_session, case)
        assert case["po"]["terms"] in text
        for line in case["po"]["line_items"]:
            assert line["description"] in text

    async def test_what_was_received(self, db_session):
        case = first("overbilled_quantity")
        _, text = await prompt_for(db_session, case)
        assert case["receipt"]["receipt_number"] in text

    async def test_the_bank_account_on_file_and_the_one_asked_for(self, db_session):
        case = first("bank_change")
        _, text = await prompt_for(db_session, case)
        assert case["vendor"]["remit_to"]["account_last4"] in text
        assert case["invoice"]["remit_to"]["account_last4"] in text

    async def test_the_vendors_recent_invoices(self, db_session):
        case = first("duplicate")
        _, text = await prompt_for(db_session, case)
        assert case["history"][0]["invoice_number"] in text

    async def test_the_flags(self, db_session):
        case = first("price_increase")
        file, text = await prompt_for(db_session, case)
        assert file.flags
        for flag in file.flags:
            assert flag in text

    async def test_says_when_nothing_was_flagged(self, db_session):
        _, text = await prompt_for(db_session, first("clean"))
        assert "No checks flagged this invoice" in text

    async def test_never_the_answer(self, db_session):
        case = first("freight_allowed")
        _, text = await prompt_for(db_session, case)
        for leak in ("is_freight", case["kind"], case["truth"]["reason"], "freight_allowed"):
            assert leak not in text


class TestReadingTheAnswer:
    def test_reads_a_verdict(self):
        verdict = review.parse('{"decision": "hold", "reason": "duplicate", "confidence": 0.93, '
                               '"explanation": "Same lines as INV-1 paid on 3 May."}')
        assert verdict == review.Verdict("hold", "duplicate", 0.93, "Same lines as INV-1 paid on 3 May.")

    def test_reads_json_in_a_code_fence(self):
        verdict = review.parse('```json\n{"decision": "pay", "reason": "none", "confidence": 1, "explanation": "ok"}\n```')
        assert verdict.decision == "pay"

    @pytest.mark.parametrize("reply", [
        "Pay it.",
        '{"decision": "approve", "reason": "none", "confidence": 0.9, "explanation": "x"}',
        '{"decision": "pay", "reason": "none", "confidence": 1.4, "explanation": "x"}',
        '{"decision": "pay", "reason": "none", "explanation": "x"}',
    ])
    def test_refuses_anything_else(self, reply):
        with pytest.raises(review.UnreadableVerdict):
            review.parse(reply)
