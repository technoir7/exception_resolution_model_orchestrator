"""
What a model reading an invoice PDF is asked, and how its answer becomes an
invoice.

The reader copies; it does not judge. An invoice whose line does not come to
its quantity times its price must reach the review as printed, or the review
would approve the corrected invoice and the vendor would be paid the printed
one. Deciding is left to the rules and the review, which see the vendor's
records; the reader sees only the PDF.
"""

import json
import re
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ValidationError

from apps.api.schemas.invoice import InvoiceCanonical, LineItem, RemitTo


class PrintedLine(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class ExtractedInvoice(BaseModel):
    """An invoice as printed. The vendor is as the invoice names it, not yet
    matched to a vendor on file."""
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None
    vendor_name: str
    vendor_tax_id: Optional[str] = None
    po_number: Optional[str] = None
    currency: str = "USD"
    line_items: List[PrintedLine]
    subtotal: Decimal
    tax_amount: Decimal = Decimal("0")
    total_amount: Decimal
    remit_to: Optional[RemitTo] = None
    notes: Optional[str] = None
    service_period: Optional[date] = None


INSTRUCTION = """This PDF is a supplier invoice. Copy what it says into JSON, exactly as printed.

Do not correct anything. If a line's amount is not its quantity times its unit
price, or the totals do not add up, copy the numbers printed. Keep each line's
description word for word, including a freight or delivery charge billed as a
line.

Reply with only a JSON object with these fields:
{"invoice_number": as printed,
 "invoice_date": "YYYY-MM-DD",
 "due_date": "YYYY-MM-DD" or null,
 "vendor_name": the business that issued the invoice,
 "vendor_tax_id": the issuer's tax ID or EIN, or null,
 "po_number": the buyer's purchase order number, or null,
 "currency": three-letter code,
 "line_items": [{"description": ..., "quantity": ..., "unit_price": ..., "amount": ...}],
 "subtotal": ..., "tax_amount": ..., "total_amount": ...,
 "remit_to": {"bank": the bank's name, "account_last4": the account number's last four digits} or null,
 "notes": any message to the customer, word for word, or null,
 "service_period": "YYYY-MM-DD", the first day of a service period billed, or null}
Write amounts and quantities as plain numbers, with no currency sign or
thousands separator. Use null for anything not printed."""


class UnreadableInvoice(ValueError):
    """The reader's reply is not an invoice in the form asked for."""


def parse(reply: str) -> ExtractedInvoice:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.S)
    text = fenced.group(1) if fenced else reply.strip()
    try:
        return ExtractedInvoice.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as error:
        raise UnreadableInvoice(f"{error}: {reply[:200]!r}") from error


def to_canonical(read: ExtractedInvoice, vendor_id: str) -> InvoiceCanonical:
    return InvoiceCanonical(
        invoice_number=read.invoice_number,
        invoice_date=read.invoice_date,
        due_date=read.due_date,
        vendor_id=vendor_id,
        vendor_name=read.vendor_name,
        po_number=read.po_number,
        currency=read.currency,
        subtotal=read.subtotal,
        tax_amount=read.tax_amount,
        total_amount=read.total_amount,
        line_items=[LineItem(line_number=i, **line.model_dump()) for i, line in enumerate(read.line_items, 1)],
        remit_to=read.remit_to,
        notes=read.notes or None,
        service_period=read.service_period,
    )
