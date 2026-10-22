"""Round 4: round 3's invoices as PDFs, read by a model, then decided as before."""

import json
from decimal import Decimal

from apps.api.services import extraction
from evals import collect, reading

CASES = reading.printed_cases(4)


def first(kind):
    return next(c for c in CASES if c["kind"] == kind)


def recorded(*replies, cost="0.002"):
    return {"attempts": [{"reply": r, "cost_usd": cost, "model_id": "claude-haiku-5-5"} for r in replies]}


def perfect(case):
    return recorded(json.dumps(reading.as_printed(case)))


class TestTheCases:
    def test_are_round_3s_with_the_same_answers(self):
        from evals import cases
        assert CASES == cases.generate(seed=3, counts=cases.counts_for(3))

    def test_as_printed_is_what_a_perfect_reader_would_copy(self):
        case = first("math_error")
        printed = reading.as_printed(case)
        assert [l["amount"] for l in printed["line_items"]] == [l["amount"] for l in case["invoice"]["line_items"]]
        assert printed["vendor_tax_id"] == case["vendor"]["tax_id"]
        extraction.ExtractedInvoice.model_validate(printed)


class TestThePrompts:
    async def test_a_perfect_reading_gives_exactly_the_prompt_the_data_did(self):
        """So any difference from round 3 comes from reading the PDF."""
        sample = [first(k) for k in ("clean", "math_error", "duplicate_reworded", "verified_bank_change",
                                     "freight_at_cap", "repeat_shipment")]
        from_data = await collect.prompts(sample)
        from_pdf = await reading.prompts(sample, {c["id"]: perfect(c) for c in sample})
        for case in sample:
            assert from_pdf[case["id"]]["prompt"] == from_data[case["id"]]["prompt"], case["kind"]
            assert from_pdf[case["id"]]["flags"] == from_data[case["id"]]["flags"]

    async def test_an_invoice_whose_vendor_cannot_be_matched_is_refused(self):
        case = first("clean")
        misread = {**reading.as_printed(case), "vendor_tax_id": "00-0000000"}
        built = await reading.prompts([case], {case["id"]: recorded(json.dumps(misread))})
        assert "prompt" not in built[case["id"]]
        assert "tax ID 00-0000000" in built[case["id"]]["refused"]

    async def test_an_unreadable_reply_is_retried_as_the_app_does(self):
        case = first("clean")
        built = await reading.prompts([case], {case["id"]: recorded("no idea", json.dumps(reading.as_printed(case)))})
        assert "prompt" in built[case["id"]]


class TestReadingAccuracy:
    def test_a_perfect_reading_has_no_errors(self):
        result = reading.accuracy(CASES[:20], {c["id"]: perfect(c) for c in CASES[:20]})
        assert result["read_exactly"] == 20 and result["field_errors"] == {}

    def test_counts_each_field_read_wrong(self):
        case = first("math_error")
        printed = reading.as_printed(case)
        corrected = {**printed, "line_items": [{**l, "amount": str(Decimal(l["quantity"]) * Decimal(l["unit_price"]))}
                                               for l in printed["line_items"]]}
        result = reading.accuracy([case], {case["id"]: recorded(json.dumps(corrected))})
        assert result["read_exactly"] == 0
        assert result["field_errors"] == {"line amount": 1}
        assert result["examples"][0]["field"] == "line amount"

    def test_formatting_differences_are_not_errors(self):
        case = first("clean")
        printed = reading.as_printed(case)
        loose = {**printed, "subtotal": float(printed["subtotal"]), "notes": printed["notes"] or "",
                 "line_items": [{**l, "description": "  " + l["description"] + " "} for l in printed["line_items"]]}
        assert reading.accuracy([case], {case["id"]: recorded(json.dumps(loose))})["read_exactly"] == 1

    def test_an_unreadable_one_counts_as_unread(self):
        case = first("clean")
        result = reading.accuracy([case], {case["id"]: recorded("no", "still no")})
        assert result["unreadable"] == 1 and result["read_exactly"] == 0
