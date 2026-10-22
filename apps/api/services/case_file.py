"""
Everything a reviewer needs to decide one invoice, gathered from the database.

What a person in accounts payable would pull up before paying: the PO with its
terms, every goods receipt on the PO, the vendor's record with the bank account on file,
the vendor's recent paid invoices, and what the automatic checks flagged.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.purchase_order import PurchaseOrder
from apps.api.models.receipt import Receipt
from apps.api.models.vendor import Vendor
from apps.api.services.flags import flags_for

# Far enough back to catch a resubmitted invoice; near enough to stay short.
HISTORY_DAYS = 120
HISTORY_LIMIT = 10


@dataclass
class CaseFile:
    invoice: Invoice
    po: Optional[PurchaseOrder]
    receipts: List[Receipt]
    vendor: Optional[Vendor]
    recent: List[Invoice] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


async def case_file_for(
    db: AsyncSession, tenant_id: UUID, invoice: Invoice, today: Optional[date] = None,
    flags: Optional[List[str]] = None,
) -> CaseFile:
    """Several queries: the PO, receipt and vendor, the history, and - unless
    the caller already has them - the flags, which re-run the rules."""
    async def one(model, *conditions):
        result = await db.execute(select(model).where(and_(model.tenant_id == tenant_id, *conditions)))
        return result.scalars().first()

    po = await one(PurchaseOrder, PurchaseOrder.po_number == invoice.po_number) if invoice.po_number else None
    receipts = []
    if invoice.po_number:
        result = await db.execute(select(Receipt).where(and_(
            Receipt.tenant_id == tenant_id, Receipt.po_number == invoice.po_number,
        )).order_by(Receipt.receipt_date))
        receipts = list(result.scalars().all())
    vendor = await one(Vendor, Vendor.vendor_id == invoice.vendor_id)

    recent = []
    if invoice.invoice_date:
        result = await db.execute(
            select(Invoice).where(and_(
                Invoice.tenant_id == tenant_id,
                Invoice.vendor_id == invoice.vendor_id,
                Invoice.id != invoice.id,
                Invoice.status == InvoiceStatus.APPROVED,
                Invoice.invoice_date >= invoice.invoice_date - timedelta(days=HISTORY_DAYS),
                Invoice.invoice_date <= invoice.invoice_date,
            )).order_by(Invoice.invoice_date.desc()).limit(HISTORY_LIMIT)
        )
        recent = list(result.scalars().all())

    if flags is None:
        flags = await flags_for(db, tenant_id, invoice, today=today)
    return CaseFile(invoice=invoice, po=po, receipts=receipts, vendor=vendor, recent=recent, flags=flags)
