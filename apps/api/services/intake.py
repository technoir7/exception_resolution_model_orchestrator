"""
Taking in an invoice: as data, or as a PDF a model reads first.

Either way the result is the same invoice record, so everything after intake
(the rules, the review, the decision) cannot tell which way it came.
"""

import hashlib
import json
import re
from typing import Optional, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.vendor import Vendor
from apps.api.schemas.invoice import InvoiceCanonical
from apps.api.services import extraction
from apps.api.services.cost_service import CostService
from apps.api.services.llm_provider import LLMResponse

# Copying a page needs no judgement, so the cheapest model reads (measured in
# the benchmark's round 4).
READER = "haiku"
MAX_PDF_BYTES = 10 * 1024 * 1024
ATTEMPTS = 2


class NotAcceptable(ValueError):
    """Not a PDF, or too large to send to a model."""


class UnknownVendor(LookupError):
    """No vendor on file matches the one the invoice names."""


class SpendCapReached(RuntimeError):
    """The tenant's model spend for the day is used up."""


class Reader(Protocol):
    async def read(self, document: bytes, instruction: str) -> LLMResponse: ...


def new_invoice(tenant_id: UUID, data: InvoiceCanonical, document_hash: str, document_type: str,
                filename: Optional[str] = None, document_content: Optional[str] = None) -> Invoice:
    return Invoice(
        tenant_id=tenant_id,
        document_content=document_content,
        document_hash=document_hash,
        document_type=document_type,
        original_filename=filename,
        status=InvoiceStatus.PENDING,
        invoice_number=data.invoice_number,
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        vendor_id=data.vendor_id,
        vendor_name=data.vendor_name,
        po_number=data.po_number,
        currency=data.currency,
        subtotal=data.subtotal,
        tax_amount=data.tax_amount,
        total_amount=data.total_amount,
        line_items=[item.model_dump(mode="json") for item in data.line_items],
        extracted_data=data.review_details(),
    )


def hash_of_data(data: InvoiceCanonical) -> str:
    return hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, default=str).encode()).hexdigest()


def _plain(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


async def find_vendor(db: AsyncSession, tenant_id: UUID, read: extraction.ExtractedInvoice) -> str:
    """The vendor on file the invoice comes from: by the tax ID printed, or by
    name only when none is printed. A known name beside an unknown tax ID is
    how an impostor's invoice looks, so it is not matched by name."""
    vendors = (await db.execute(select(Vendor).where(Vendor.tenant_id == tenant_id))).scalars().all()
    if read.vendor_tax_id:
        match = [v for v in vendors if v.tax_id == read.vendor_tax_id.strip()]
        what = f"tax ID {read.vendor_tax_id}"
    else:
        match = [v for v in vendors if _plain(v.name) == _plain(read.vendor_name)]
        what = f"the name {read.vendor_name!r} (no tax ID printed)"
    if len(match) != 1:
        raise UnknownVendor(f"{'no' if not match else 'more than one'} vendor on file with {what}")
    return match[0].vendor_id


async def ingest_pdf(db: AsyncSession, tenant_id: UUID, pdf: bytes, reader: Reader,
                     filename: Optional[str] = None) -> Invoice:
    """Has the reader copy the PDF, matches the vendor and stores the invoice.
    Every model call is recorded at its cost, including those for an invoice
    then refused."""
    if not pdf.startswith(b"%PDF-"):
        raise NotAcceptable("not a PDF")
    if len(pdf) > MAX_PDF_BYTES:
        raise NotAcceptable(f"larger than {MAX_PDF_BYTES // (1024 * 1024)} MB")
    costs = CostService(db, tenant_id)
    calls = []
    invoice = None
    try:
        read = None
        for _ in range(ATTEMPTS):
            if await costs.get_daily_spend() >= settings.router_tenant_daily_cap:
                raise SpendCapReached("today's model spend cap is reached")
            calls.append(await reader.read(pdf, extraction.INSTRUCTION))
            try:
                read = extraction.parse(calls[-1].content)
                break
            except extraction.UnreadableInvoice:
                continue
        if read is None:
            raise extraction.UnreadableInvoice(f"no invoice could be read in {ATTEMPTS} tries")
        data = extraction.to_canonical(read, await find_vendor(db, tenant_id, read))
        invoice = new_invoice(tenant_id, data, hashlib.sha256(pdf).hexdigest(), "pdf", filename)
        invoice.extracted_data = {**invoice.extracted_data, "read_by": calls[-1].model_id}
        db.add(invoice)
        await db.flush()
    finally:
        for call in calls:
            await costs.record_llm_call(
                model_tier=call.model_tier, model_id=call.model_id, input_tokens=call.input_tokens,
                output_tokens=call.output_tokens, invoice_id=invoice.id if invoice else None,
                cost_usd=call.cost_usd,
            )
        await db.flush()
    return invoice
