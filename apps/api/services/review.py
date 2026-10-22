"""
A model's review of one invoice: what it is shown, and how its answer is read.

The model sees the documents a person would, not a summary of them: the
automatic checks compare totals crudely and flag many invoices that are fine
(a partial delivery, sales tax on a pre-tax PO), so a verdict built on the
flags alone could only repeat them.

Everything here is a pure function of a case file, so the exact text a model
receives can be tested.
"""

import json
import re
from dataclasses import dataclass
from typing import Iterable, List

from apps.api.services.case_file import CaseFile

DECISIONS = ("pay", "hold")
REASONS = ("none", "price", "quantity", "charges", "tax", "duplicate", "bank_details", "vendor", "other")

POLICY = """You review supplier invoices before payment for an accounts payable team.
Decide whether this invoice can be paid now, or must be held for a person to look at.

Pay only if all of these are true:
- every line bills goods or services the purchase order covers, at the PO's
  unit price (the same goods counted in different units are fine if the
  amount comes to the same);
- for goods, no more is billed than the receipt shows was received;
- any freight, tax or other charge is allowed by the PO's terms, and is no
  more than they allow;
- the invoice does not bill again for something already invoiced;
- the invoice comes from the vendor on the PO, and payment goes to the bank
  account on file for that vendor.
Otherwise hold it. A flag from the automatic checks is not a reason to hold on
its own: they compare totals crudely and flag many invoices that are fine.
Decide from the documents."""

ANSWER = """Reply with only a JSON object:
{"decision": "pay" or "hold",
 "reason": one of %s ("none" when paying),
 "confidence": a number from 0 to 1, how sure you are,
 "explanation": one or two sentences that cite the documents}""" % json.dumps(list(REASONS))


@dataclass(frozen=True)
class Verdict:
    decision: str
    reason: str
    confidence: float
    explanation: str


class UnreadableVerdict(ValueError):
    """The model's reply is not a verdict in the form asked for."""


def _lines(items: Iterable[dict], received: bool = False) -> List[str]:
    out = []
    for item in items or []:
        if received:
            out.append(f"  {item['line_number']}. {item['description']}: {item['quantity']} received")
        else:
            out.append(f"  {item['line_number']}. {item['description']}: {item['quantity']} x "
                       f"{item['unit_price']} = {item['amount']}")
    return out


def _invoice(file: CaseFile) -> List[str]:
    inv = file.invoice
    extra = inv.extracted_data or {}
    remit = extra.get("remit_to")
    out = [
        f"INVOICE {inv.invoice_number}, dated {inv.invoice_date}, due {inv.due_date}",
        f"From: {inv.vendor_name} (vendor {inv.vendor_id})",
        f"PO referenced: {inv.po_number or 'none'}",
    ]
    if extra.get("service_period"):
        out.append(f"Service period beginning: {extra['service_period']}")
    out += ["Lines:", *_lines(inv.line_items),
            f"Subtotal {inv.subtotal}; tax {inv.tax_amount}; total {inv.currency} {inv.total_amount}",
            f"Remit to: {remit['bank']}, account ending {remit['account_last4']}" if remit
            else "Remit to: not stated",
            f"Notes on the invoice: {extra.get('notes') or 'none'}"]
    return out


def _vendor(file: CaseFile) -> List[str]:
    v = file.vendor
    if v is None:
        return [f"VENDOR RECORD: none on file for vendor {file.invoice.vendor_id}"]
    return [f"VENDOR RECORD {v.vendor_id}: {v.name}; tax ID {v.tax_id}; payment terms {v.payment_terms}",
            f"Bank account on file: {v.remit_bank}, account ending {v.remit_account_last4}"]


def _po(file: CaseFile) -> List[str]:
    po = file.po
    if po is None:
        return ["PURCHASE ORDER: none found for the PO referenced"]
    return [f"PURCHASE ORDER {po.po_number}, dated {po.po_date}, vendor {po.vendor_id} ({po.vendor_name})",
            f"Terms: {po.terms or 'none stated'}",
            "Lines:", *_lines(po.line_items), f"Total {po.currency} {po.total_amount}"]


def _receipt(file: CaseFile) -> List[str]:
    r = file.receipt
    if r is None:
        return ["GOODS RECEIPT: none on file for this PO"]
    return [f"GOODS RECEIPT {r.receipt_number}, dated {r.receipt_date}", *_lines(r.line_items, received=True)]


def _recent(file: CaseFile) -> List[str]:
    if not file.recent:
        return ["VENDOR'S RECENT PAID INVOICES: none in the last 120 days"]
    out = ["VENDOR'S RECENT PAID INVOICES:"]
    for inv in file.recent:
        period = (inv.extracted_data or {}).get("service_period")
        out.append(f"- {inv.invoice_number}, dated {inv.invoice_date}, PO {inv.po_number}, total {inv.total_amount}"
                   + (f", service period beginning {period}" if period else ""))
        out += ["  " + line for line in _lines(inv.line_items)]
    return out


def _flags(file: CaseFile) -> List[str]:
    if not file.flags:
        return ["AUTOMATIC CHECKS: No checks flagged this invoice."]
    return ["AUTOMATIC CHECKS flagged:", *(f"- {flag}" for flag in file.flags)]


def prompt(file: CaseFile) -> str:
    sections = [_invoice(file), _vendor(file), _po(file), _receipt(file), _recent(file), _flags(file)]
    return "\n\n".join([POLICY, *("\n".join(s) for s in sections), ANSWER])


def parse(reply: str) -> Verdict:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", reply, re.S)
    text = fenced.group(1) if fenced else reply.strip()
    try:
        data = json.loads(text)
        verdict = Verdict(str(data["decision"]), str(data["reason"]), float(data["confidence"]),
                          str(data["explanation"]))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise UnreadableVerdict(f"{error}: {reply[:200]!r}") from error
    if verdict.decision not in DECISIONS or not 0 <= verdict.confidence <= 1:
        raise UnreadableVerdict(f"not a verdict: {reply[:200]!r}")
    return verdict
