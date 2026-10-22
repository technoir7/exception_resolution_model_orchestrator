"""Reading an invoice PDF into the invoice the rest of the app works with."""

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from apps.api.models.cost import CostEvent
from apps.api.models.vendor import Vendor
from apps.api.services import extraction, intake
from apps.api.services.llm_provider import LLMResponse
from apps.api.tests.conftest import TEST_TENANT_ID

PRINTED = {
    "invoice_number": "INV-79919", "invoice_date": "2026-02-20", "due_date": "2026-04-06",
    "vendor_name": "Keystone Office Products Corp", "vendor_tax_id": "31-2341310",
    "po_number": "PO-2026-1037", "currency": "USD",
    "line_items": [
        {"description": "Ethernet patch cable Cat6 10 ft", "quantity": 233, "unit_price": "6.14", "amount": "1430.62"},
        # Printed wrong (8 x 194.05 is 1552.40): the reader must copy it, not fix it.
        {"description": "Laptop docking station USB-C", "quantity": 8, "unit_price": "194.05", "amount": "1562.40"},
    ],
    "subtotal": "2993.02", "tax_amount": "0.00", "total_amount": "2993.02",
    "remit_to": {"bank": "Pacific Commerce Bank", "account_last4": "3572"},
    "notes": "Partial shipment; balance to follow.", "service_period": None,
}


class TestTheInstruction:
    def test_says_to_copy_not_correct(self):
        assert "exactly as printed" in extraction.INSTRUCTION
        assert "Do not correct" in extraction.INSTRUCTION

    def test_names_every_field_it_expects(self):
        for field in extraction.ExtractedInvoice.model_fields:
            assert field in extraction.INSTRUCTION


class TestReadingTheReply:
    def test_reads_what_was_printed(self):
        read = extraction.parse(json.dumps(PRINTED))
        assert read.invoice_number == "INV-79919"
        assert read.invoice_date == date(2026, 2, 20)
        assert read.line_items[1].amount == Decimal("1562.40")
        assert read.remit_to.account_last4 == "3572"

    def test_reads_json_in_a_code_fence(self):
        assert extraction.parse("```json\n" + json.dumps(PRINTED) + "\n```").po_number == "PO-2026-1037"

    @pytest.mark.parametrize("reply", [
        "I can't read this document.",
        json.dumps({**PRINTED, "invoice_date": "20 Feb"}),
        json.dumps({k: v for k, v in PRINTED.items() if k != "total_amount"}),
    ])
    def test_refuses_anything_else(self, reply):
        with pytest.raises(extraction.UnreadableInvoice):
            extraction.parse(reply)


class TestTheInvoiceItBecomes:
    def test_keeps_the_printed_numbers_even_when_they_do_not_add_up(self):
        invoice = extraction.to_canonical(extraction.parse(json.dumps(PRINTED)), vendor_id="V0001")
        assert invoice.line_items[1].amount == Decimal("1562.40")
        assert invoice.subtotal == Decimal("2993.02")

    def test_numbers_the_lines_and_carries_what_the_review_reads(self):
        invoice = extraction.to_canonical(extraction.parse(json.dumps(PRINTED)), vendor_id="V0001")
        assert [l.line_number for l in invoice.line_items] == [1, 2]
        assert invoice.vendor_id == "V0001"
        assert invoice.review_details() == {
            "remit_to": {"bank": "Pacific Commerce Bank", "account_last4": "3572"},
            "notes": "Partial shipment; balance to follow.",
        }


async def add_vendor(db, vendor_id="V0001", name="Keystone Office Products Corp", tax_id="31-2341310"):
    db.add(Vendor(tenant_id=TEST_TENANT_ID, vendor_id=vendor_id, name=name, tax_id=tax_id,
                  remit_bank="Pacific Commerce Bank", remit_account_last4="3572", payment_terms="NET45"))
    await db.flush()


def read(**changes):
    return extraction.parse(json.dumps({**PRINTED, **changes}))


class TestFindingTheVendor:
    async def test_by_the_tax_id_printed(self, db_session):
        await add_vendor(db_session)
        assert await intake.find_vendor(db_session, TEST_TENANT_ID, read(vendor_name="Keystone Office")) == "V0001"

    async def test_by_name_when_no_tax_id_is_printed(self, db_session):
        await add_vendor(db_session)
        found = await intake.find_vendor(db_session, TEST_TENANT_ID,
                                         read(vendor_tax_id=None, vendor_name="keystone office products  corp"))
        assert found == "V0001"

    async def test_not_by_name_when_the_tax_id_printed_is_not_on_file(self, db_session):
        """A known name with an unknown tax ID is how an impostor's invoice
        looks, so it goes to a person rather than to the vendor it names."""
        await add_vendor(db_session)
        with pytest.raises(intake.UnknownVendor):
            await intake.find_vendor(db_session, TEST_TENANT_ID, read(vendor_tax_id="99-9999999"))

    async def test_only_among_the_tenants_own_vendors(self, db_session):
        from uuid import uuid4
        db_session.add(Vendor(tenant_id=uuid4(), vendor_id="V0001", name="Keystone Office Products Corp",
                              tax_id="31-2341310", remit_bank="x", remit_account_last4="0000", payment_terms="NET30"))
        await db_session.flush()
        with pytest.raises(intake.UnknownVendor):
            await intake.find_vendor(db_session, TEST_TENANT_ID, read())


class FakeReader:
    def __init__(self, *replies, cost="0.002"):
        self.replies, self.cost, self.calls = list(replies), Decimal(cost), []

    async def read(self, document, instruction):
        self.calls.append((document, instruction))
        return LLMResponse(content=self.replies.pop(0), model_id="claude-haiku-5-5", input_tokens=1500,
                           output_tokens=300, cost_usd=self.cost)


PDF = b"%PDF-1.4 an invoice"


async def costs(db):
    return (await db.execute(select(CostEvent))).scalars().all()


class TestIngestingAPDF:
    async def test_stores_the_invoice_as_read(self, db_session):
        await add_vendor(db_session)
        invoice = await intake.ingest_pdf(db_session, TEST_TENANT_ID, PDF, FakeReader(json.dumps(PRINTED)),
                                          filename="inv.pdf")
        assert (invoice.invoice_number, invoice.vendor_id, invoice.po_number) == ("INV-79919", "V0001", "PO-2026-1037")
        assert invoice.document_type == "pdf" and invoice.original_filename == "inv.pdf"
        assert invoice.line_items[1]["amount"] == "1562.40"
        assert invoice.extracted_data["remit_to"]["account_last4"] == "3572"

    async def test_sends_the_reader_the_pdf_and_the_instruction(self, db_session):
        await add_vendor(db_session)
        reader = FakeReader(json.dumps(PRINTED))
        await intake.ingest_pdf(db_session, TEST_TENANT_ID, PDF, reader)
        assert reader.calls == [(PDF, extraction.INSTRUCTION)]

    async def test_records_what_reading_it_cost(self, db_session):
        await add_vendor(db_session)
        invoice = await intake.ingest_pdf(db_session, TEST_TENANT_ID, PDF, FakeReader(json.dumps(PRINTED)))
        [event] = await costs(db_session)
        assert (event.invoice_id, event.cost_usd, event.model_id) == (invoice.id, Decimal("0.002"), "claude-haiku-5-5")

    async def test_asks_again_once_when_the_reply_is_unreadable(self, db_session):
        await add_vendor(db_session)
        invoice = await intake.ingest_pdf(db_session, TEST_TENANT_ID, PDF,
                                          FakeReader("Sorry, which invoice?", json.dumps(PRINTED)))
        assert invoice.invoice_number == "INV-79919"
        assert len(await costs(db_session)) == 2

    async def test_gives_up_after_two_unreadable_replies_and_still_records_their_cost(self, db_session):
        await add_vendor(db_session)
        with pytest.raises(extraction.UnreadableInvoice):
            await intake.ingest_pdf(db_session, TEST_TENANT_ID, PDF, FakeReader("no", "still no"))
        assert len(await costs(db_session)) == 2

    async def test_refuses_an_unknown_vendor_and_still_records_the_cost(self, db_session):
        with pytest.raises(intake.UnknownVendor):
            await intake.ingest_pdf(db_session, TEST_TENANT_ID, PDF, FakeReader(json.dumps(PRINTED)))
        assert len(await costs(db_session)) == 1

    @pytest.mark.parametrize("body", [b"", b"<html>not a pdf</html>", b"%PDF-" + b"x" * intake.MAX_PDF_BYTES])
    async def test_refuses_what_is_not_a_pdf_or_is_too_large_without_a_model_call(self, db_session, body):
        reader = FakeReader()
        with pytest.raises(intake.NotAcceptable):
            await intake.ingest_pdf(db_session, TEST_TENANT_ID, body, reader)
        assert reader.calls == []

    async def test_refuses_past_the_daily_spend_cap_without_a_model_call(self, db_session, monkeypatch):
        from apps.api.config import settings
        monkeypatch.setattr(settings, "router_tenant_daily_cap", Decimal("0"))
        reader = FakeReader(json.dumps(PRINTED))
        with pytest.raises(intake.SpendCapReached):
            await intake.ingest_pdf(db_session, TEST_TENANT_ID, PDF, reader)
        assert reader.calls == []


class TestTheEndpoint:
    @pytest.fixture
    def post(self, db_session, monkeypatch):
        import httpx
        from apps.api.dependencies import TenantContext, get_tenant_context
        from apps.api.main import app
        from apps.api.routes import ingest

        def send(body, reply=json.dumps(PRINTED), reader=None):
            monkeypatch.setattr(ingest.claude, "model", lambda model: reader or FakeReader(reply))
            app.dependency_overrides[get_tenant_context] = lambda: TenantContext(TEST_TENANT_ID, db_session)
            client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
            return client.post("/ingest/invoice-pdf?filename=inv.pdf", content=body,
                               headers={"Content-Type": "application/pdf"})
        yield send
        app.dependency_overrides.clear()

    async def test_answers_with_the_invoice_as_read(self, db_session, post):
        await add_vendor(db_session)
        response = await post(PDF)
        assert response.status_code == 201
        body = response.json()
        assert (body["invoice_number"], body["vendor_id"], body["document_type"]) == ("INV-79919", "V0001", "pdf")

    async def test_refuses_what_is_not_a_pdf(self, post):
        assert (await post(b"<html>")).status_code == 415

    async def test_says_why_it_could_not_take_the_invoice(self, post):
        response = await post(PDF)
        assert response.status_code == 422 and "tax ID 31-2341310" in response.json()["detail"]

    async def test_needs_models_on(self, post, monkeypatch):
        from apps.api.config import settings
        monkeypatch.setattr(settings, "review_with_models", False)
        assert (await post(PDF)).status_code == 503

    async def test_says_when_the_model_cannot_be_reached(self, post):
        from apps.api.services.llm_provider import ModelUnavailable

        class Down:
            async def read(self, document, instruction):
                raise ModelUnavailable("the Claude API answered 529: Overloaded")

        response = await post(PDF, reader=Down())
        assert response.status_code == 502 and "Overloaded" in response.json()["detail"]


class TestCurrency:
    def test_an_invoice_that_prints_none_is_in_the_buyers_own(self):
        """One of round 4's layouts prints no currency, as many domestic
        invoices do, and the reader rightly reports none."""
        invoice = extraction.to_canonical(read(currency=None), vendor_id="V0001")
        assert invoice.currency == "USD"

    def test_a_printed_currency_is_kept(self):
        assert extraction.to_canonical(read(currency="CAD"), vendor_id="V0001").currency == "CAD"
