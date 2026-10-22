"""Puts the benchmark's cases into the app's database, as its own records."""

import hashlib
from datetime import date
from decimal import Decimal
from typing import Dict, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.purchase_order import POStatus, PurchaseOrder
from apps.api.models.receipt import Receipt
from apps.api.models.vendor import Vendor

TENANT = UUID("00000000-0000-0000-0000-0000000000e1")


def _invoice(tenant_id: UUID, doc: Dict, vendor_id: str, po_number: str, status: InvoiceStatus) -> Invoice:
    key = f"{vendor_id}|{doc['invoice_number']}|{doc['invoice_date']}|{doc['total_amount']}"
    return Invoice(
        tenant_id=tenant_id,
        document_hash=hashlib.sha256(key.encode()).hexdigest(),
        document_type="json",
        status=status,
        invoice_number=doc["invoice_number"],
        invoice_date=date.fromisoformat(doc["invoice_date"]),
        due_date=date.fromisoformat(doc["due_date"]) if doc.get("due_date") else None,
        vendor_id=vendor_id,
        vendor_name=doc.get("vendor_name"),
        po_number=po_number,
        currency="USD",
        subtotal=Decimal(doc["subtotal"]),
        tax_amount=Decimal(doc["tax_amount"]),
        total_amount=Decimal(doc["total_amount"]),
        line_items=doc["line_items"],
        extracted_data={k: doc[k] for k in ("remit_to", "notes", "service_period") if doc.get(k) is not None},
    )


def _vendor(tenant_id: UUID, v: Dict) -> Vendor:
    updated = v.get("remit_updated_on")
    return Vendor(tenant_id=tenant_id, vendor_id=v["id"], name=v["name"], tax_id=v["tax_id"],
                  remit_bank=v["remit_to"]["bank"], remit_account_last4=v["remit_to"]["account_last4"],
                  payment_terms=v["payment_terms"], remit_previous=v.get("remit_previous"),
                  remit_updated_on=date.fromisoformat(updated) if updated else None)


async def load_records(db: AsyncSession, tenant_id: UUID, case: Dict) -> None:
    """Everything the case's invoice is checked against: its vendor(s), PO,
    receipts and the vendor's paid history."""
    db.add(_vendor(tenant_id, case["vendor"]))
    if "po_vendor" in case:
        db.add(_vendor(tenant_id, case["po_vendor"]))
    po = case["po"]
    db.add(PurchaseOrder(
        tenant_id=tenant_id, po_number=po["po_number"], po_date=date.fromisoformat(po["po_date"]),
        status=POStatus.OPEN, vendor_id=po["vendor_id"], vendor_name=po["vendor_name"], currency="USD",
        total_amount=Decimal(po["total_amount"]), line_items=po["line_items"], terms=po["terms"],
    ))
    for r in [case["receipt"], *case.get("extra_receipts", [])] if case["receipt"] else []:
        db.add(Receipt(
            tenant_id=tenant_id, receipt_number=r["receipt_number"],
            receipt_date=date.fromisoformat(r["receipt_date"]), po_number=r["po_number"],
            vendor_id=r["vendor_id"], total_amount=Decimal(r["total_amount"]), line_items=r["line_items"],
        ))
    for paid in case["history"]:
        db.add(_invoice(tenant_id, paid, case["invoice"]["vendor_id"], paid["po_number"], InvoiceStatus.APPROVED))


async def load(db: AsyncSession, tenant_id: UUID, cases: List[Dict]) -> Dict[str, Invoice]:
    """Each case's records, then the invoice to decide, as given. Returns the
    invoices to decide, by case id."""
    to_decide = {}
    for case in cases:
        await load_records(db, tenant_id, case)
        invoice = _invoice(tenant_id, case["invoice"], case["invoice"]["vendor_id"], case["po"]["po_number"],
                           InvoiceStatus.PENDING)
        db.add(invoice)
        to_decide[case["id"]] = invoice
    await db.flush()
    return to_decide
