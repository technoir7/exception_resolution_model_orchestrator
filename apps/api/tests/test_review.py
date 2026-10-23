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


class TestWhatAnIngestedInvoiceCarries:
    def test_the_bank_details_notes_and_service_period_reach_the_review(self):
        from apps.api.schemas.invoice import InvoiceCanonical
        invoice = InvoiceCanonical(
            invoice_number="INV-1", invoice_date="2026-05-04", vendor_id="V001", vendor_name="Acme",
            subtotal="10.00", total_amount="10.00", notes="Second notice.", service_period="2026-04-27",
            remit_to={"bank": "First Harbor Bank", "account_last4": "0042"},
        )
        assert invoice.review_details() == {
            "remit_to": {"bank": "First Harbor Bank", "account_last4": "0042"},
            "notes": "Second notice.", "service_period": "2026-04-27",
        }

    def test_leaves_out_what_was_not_given(self):
        from apps.api.schemas.invoice import InvoiceCanonical
        invoice = InvoiceCanonical(invoice_number="INV-1", invoice_date="2026-05-04", vendor_id="V001",
                                   vendor_name="Acme", subtotal="10.00", total_amount="10.00")
        assert invoice.review_details() == {}


class TestDeliveriesAndBankChanges:
    async def test_every_receipt_on_the_po_is_shown(self, db_session):
        from apps.api.models.receipt import Receipt
        from datetime import date
        case = first("clean")
        invoices = await seed.load(db_session, TEST_TENANT_ID, [case])
        db_session.add(Receipt(tenant_id=TEST_TENANT_ID, receipt_number="RCV-SECOND", receipt_date=date(2026, 5, 1),
                               po_number=case["po"]["po_number"], vendor_id=case["vendor"]["id"],
                               total_amount=Decimal("0"), line_items=[]))
        await db_session.flush()
        file = await case_file_for(db_session, TEST_TENANT_ID, invoices[case["id"]], today=cases.AS_OF)
        text = review.prompt(file)
        assert case["receipt"]["receipt_number"] in text and "RCV-SECOND" in text

    async def test_a_changed_bank_account_shows_when_and_from_what(self, db_session):
        from datetime import date
        case = first("clean")
        invoices = await seed.load(db_session, TEST_TENANT_ID, [case])
        file = await case_file_for(db_session, TEST_TENANT_ID, invoices[case["id"]], today=cases.AS_OF)
        file.vendor.remit_updated_on = date(2026, 3, 2)
        file.vendor.remit_previous = "Union Plains Bank, account ending 1234"
        text = review.prompt(file)
        assert "updated 2026-03-02" in text and "Union Plains Bank, account ending 1234" in text


class TestTheVendorsDocuments:
    """The agreement, amendments, emails and AP policy that a PO refers to."""

    def docs(self):
        from apps.api.services.retrieval import Passage
        return [
            Passage("p", "policy", "AP Policy Manual 7.4 Expedite and rush fees", "Rush fees need written approval."),
            Passage("e", "email", "Email 2026-04-02, Purchasing to vendor", "The $80 expedite fee is approved.",
                    vendor_id="V1", dated="2026-04-02"),
            Passage("a2", "amendment", "Amendment No. 2 to MSA-1, effective 2026-06-01", "Bolt price $0.51.",
                    vendor_id="V1", dated="2026-06-01"),
            Passage("m", "agreement", "MSA-1 section 6, Freight", "Freight is included in prices.", vendor_id="V1"),
            Passage("a1", "amendment", "Amendment No. 1 to MSA-1, effective 2026-02-01", "Bolt price $0.55.",
                    vendor_id="V1", dated="2026-02-01"),
        ]

    async def file(self, db_session):
        case = first("clean")
        invoices = await seed.load(db_session, TEST_TENANT_ID, [case])
        return await case_file_for(db_session, TEST_TENANT_ID, invoices[case["id"]], today=cases.AS_OF)

    async def test_are_left_out_when_none_were_looked_up(self, db_session):
        file = await self.file(db_session)
        text = review.prompt(file)
        assert text.startswith(review.POLICY + "\n\nINVOICE ")
        assert review.DOCUMENTS_POLICY not in text

    async def test_every_passage_is_shown_with_its_title(self, db_session):
        file = await self.file(db_session)
        file.documents = self.docs()
        text = review.prompt(file)
        for d in file.documents:
            assert f"[{d.title}] {d.text}" in text

    async def test_the_policy_says_how_they_bear_on_the_terms(self, db_session):
        file = await self.file(db_session)
        file.documents = self.docs()
        assert review.prompt(file).startswith(review.POLICY + "\n\n" + review.DOCUMENTS_POLICY)

    async def test_come_in_order_agreement_amendments_by_date_emails_policy(self, db_session):
        file = await self.file(db_session)
        file.documents = self.docs()
        text = review.prompt(file)
        positions = [text.index(f"[{d.title}]") for d in sorted(file.documents, key=lambda d: "m a1 a2 e p".split().index(d.id))]
        assert positions == sorted(positions)

    async def test_come_after_the_po(self, db_session):
        file = await self.file(db_session)
        file.documents = self.docs()
        text = review.prompt(file)
        assert text.index("PURCHASE ORDER") < text.index("[MSA-1 section 6, Freight]") < text.index("GOODS RECEIPT")

    async def test_says_so_when_none_were_found(self, db_session):
        file = await self.file(db_session)
        file.documents = []
        assert "VENDOR'S AGREEMENT, AMENDMENTS, EMAILS AND AP POLICY: none found" in review.prompt(file)
