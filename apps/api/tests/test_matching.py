"""Matching an invoice against its PO and everything received on it."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.purchase_order import POStatus, PurchaseOrder
from apps.api.models.receipt import Receipt
from apps.api.services.matching_engine import MatchingEngine, MatchStatus
from apps.api.tests.conftest import TEST_TENANT_ID

LINE = {"line_number": 1, "description": "Widget", "quantity": 100, "unit_price": "10.00", "amount": "1000.00"}


async def setup(db, received, billed):
    db.add(PurchaseOrder(tenant_id=TEST_TENANT_ID, po_number="PO-1", po_date=date(2026, 1, 5), status=POStatus.OPEN,
                         vendor_id="V1", vendor_name="Acme", currency="USD", total_amount=Decimal("1000.00"),
                         line_items=[LINE]))
    for i, quantity in enumerate(received, 1):
        db.add(Receipt(tenant_id=TEST_TENANT_ID, receipt_number=f"R-{i}", receipt_date=date(2026, 1, 10 * i),
                       po_number="PO-1", vendor_id="V1", total_amount=Decimal(quantity * 10),
                       line_items=[{"line_number": 1, "description": "Widget", "quantity": quantity}]))
    invoice = Invoice(id=uuid4(), tenant_id=TEST_TENANT_ID, document_hash="h", status=InvoiceStatus.PENDING,
                      invoice_number="INV-1", invoice_date=date(2026, 1, 25), vendor_id="V1", po_number="PO-1",
                      total_amount=Decimal(billed * 10),
                      line_items=[{**LINE, "quantity": billed, "amount": str(billed * 10)}])
    db.add(invoice)
    await db.flush()
    return invoice


async def test_a_po_delivered_in_two_shipments_counts_both(db_session):
    """A second receipt on a PO used to raise MultipleResultsFound."""
    invoice = await setup(db_session, received=[50, 50], billed=100)
    result = await MatchingEngine(db_session, TEST_TENANT_ID).match(invoice)
    assert result.status == MatchStatus.FULL_MATCH


async def test_billing_more_than_all_shipments_brought_is_a_variance(db_session):
    invoice = await setup(db_session, received=[50, 20], billed=100)
    result = await MatchingEngine(db_session, TEST_TENANT_ID).match(invoice)
    assert any(v.field == "line_1_quantity" and not v.within_tolerance for v in result.variances)
