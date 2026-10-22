"""Prints a benchmark invoice as a one-page PDF, as a vendor's billing system
might, for round 4: round 3's invoices, read from PDFs instead of given as data.

There are three layouts, one per vendor. They differ in what a reader must
normalise: date formats, money with or without a currency sign and thousands
separators, column order and names, labels, and how the bank account is
shown. Everything the invoice says is printed, and nothing it does not say.

Written with the standard library rather than a PDF package: a page of text
and rules is a few dozen lines of PDF, and no dependency is needed for it.

    python -m evals.render --round 4 --out somewhere/   # write the PDFs to look at
"""

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Tuple

PRINTED = {"invoice_number", "invoice_date", "due_date", "vendor_id", "vendor_name", "po_number", "currency",
           "subtotal", "tax_amount", "total_amount", "line_items", "remit_to", "notes"}
# vendor_id and is_freight are the buyer's own bookkeeping, not on the page.
LINE_PRINTED = {"line_number", "description", "quantity", "unit_price", "amount", "is_freight"}

STREETS = ["Commerce Dr", "Industrial Pkwy", "Market St", "Harbor Blvd", "Mill Rd", "Depot Ave", "Lakeview Ct"]
CITIES = ["Dayton, OH 45402", "Fresno, CA 93721", "Tacoma, WA 98402", "Omaha, NE 68102", "Raleigh, NC 27601",
          "Tulsa, OK 74103", "Albany, NY 12207"]
BILL_TO = ["Accounts Payable", "1 Enterprise Way", "Springfield, IL 62701"]


@dataclass(frozen=True)
class Style:
    title: str
    date: Callable[[date], str]
    money: Callable[[Decimal], str]
    columns: Tuple[str, ...]          # the line's fields, in the order printed
    headings: Tuple[str, ...]
    labels: Dict[str, str]
    remit: str


STYLES = {
    "classic": Style(
        title="INVOICE",
        date=lambda d: f"{d:%B} {d.day}, {d.year}",
        money=lambda m: f"${m:,.2f}",
        columns=("description", "quantity", "unit_price", "amount"),
        headings=("Description", "Qty", "Unit Price", "Amount"),
        labels={"number": "Invoice No.", "date": "Invoice Date", "due": "Due Date", "po": "PO Number",
                "subtotal": "Subtotal", "tax": "Sales Tax", "total": "Total Due", "tax_id": "Tax ID",
                "notes": "Notes", "bill_to": "Bill To"},
        remit="Remit payment to: {bank}, account ending {last4}",
    ),
    "modern": Style(
        title="Bill",
        date=lambda d: f"{d:%m/%d/%Y}",
        money=lambda m: f"{m:,.2f}",
        columns=("quantity", "description", "unit_price", "amount"),
        headings=("Qty", "Item", "Rate", "Line Total"),
        labels={"number": "Bill #", "date": "Date", "due": "Payment due", "po": "Customer PO",
                "subtotal": "Net amount", "tax": "Tax", "total": "Amount due ({currency})", "tax_id": "EIN",
                "notes": "Message", "bill_to": "Customer"},
        remit="Pay by ACH or wire to {bank}, acct no. ****{last4}",
    ),
    "terse": Style(
        title="INVOICE",
        date=lambda d: f"{d.day:02d}-{d:%b}-{d.year}",
        money=lambda m: f"{m:.2f}",
        columns=("description", "quantity", "unit_price", "amount"),
        headings=("Item description", "Quantity", "Price each", "Ext. price"),
        labels={"number": "Inv #", "date": "Inv. date", "due": "Due", "po": "Order ref.",
                "subtotal": "Goods total", "tax": "Tax", "total": "Balance due", "tax_id": "Federal tax ID",
                "notes": "Comments", "bill_to": "Sold to"},
        remit="Bank: {bank}   Account: xxxx{last4}",
    ),
}


def layout_for(case: Dict) -> str:
    """A vendor's billing system prints every invoice the same way."""
    return sorted(STYLES)[int(case["invoice"]["vendor_id"][1:]) % len(STYLES)]


def issuer(case: Dict) -> Dict:
    """The vendor record of whoever sent the invoice."""
    for vendor in (case["vendor"], case.get("po_vendor")):
        if vendor and vendor["id"] == case["invoice"]["vendor_id"]:
            return vendor
    raise ValueError(f"{case['id']}: no vendor record for {case['invoice']['vendor_id']}")


# Helvetica's widths in thousandths of the font size: exact for the characters
# in numbers, rough for letters, which are only ever left-aligned or wrapped.
WIDTHS = {**{c: 556 for c in "0123456789$#"}, ",": 278, ".": 278, " ": 278, "-": 333, "/": 278, "*": 389}


def _width(text: str, size: float) -> float:
    return sum(WIDTHS.get(c, 667 if c.isupper() else 500) for c in text) * size / 1000


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Page:
    def __init__(self):
        self.ops: List[str] = []

    def text(self, x: float, y: float, s: str, size: float = 9, bold: bool = False, right: bool = False):
        if right:
            x -= _width(s, size)
        self.ops.append(f"BT /{'F2' if bold else 'F1'} {size} Tf {x:.2f} {y:.2f} Td ({_escape(s)}) Tj ET")

    def rule(self, x1: float, y: float, x2: float, weight: float = 0.5):
        self.ops.append(f"{weight} w {x1} {y:.2f} m {x2} {y:.2f} l S")

    def band(self, x: float, y: float, w: float, h: float):
        self.ops.append(f"0.92 g {x} {y:.2f} {w} {h} re f 0 g")

    def wrapped(self, x: float, y: float, s: str, width: float, size: float = 9) -> float:
        """Draws s in lines no wider than width; returns the y below it."""
        line = ""
        for word in s.split():
            if line and _width(f"{line} {word}", size) > width:
                self.text(x, y, line, size)
                y, line = y - size * 1.4, word
            else:
                line = f"{line} {word}".strip()
        if line:
            self.text(x, y, line, size)
            y -= size * 1.4
        return y


def _pdf(ops: List[str]) -> bytes:
    content = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


LEFT, RIGHT = 54, 558
# Where each column's text sits: descriptions left-aligned from x, numbers
# right-aligned to x.
COLUMN_X = {"description": 54, "quantity": 380, "unit_price": 470, "amount": 558}
QTY_FIRST_X = {"quantity": 84, "description": 100, "unit_price": 470, "amount": 558}


def render(case: Dict) -> bytes:
    inv = case["invoice"]
    unknown = set(k for k, v in inv.items() if v is not None) - PRINTED
    unknown |= {k for line in inv["line_items"] for k in line} - LINE_PRINTED
    if unknown:
        raise ValueError(f"{case['id']}: the layouts do not print {sorted(unknown)}")
    style, vendor = STYLES[layout_for(case)], issuer(case)
    page = _Page()
    n = int(vendor["id"][1:])
    address = [f"{100 + n * 17 % 900} {STREETS[n % len(STREETS)]}", CITIES[n * 3 % len(CITIES)]]
    details = [(style.labels["number"], inv["invoice_number"]),
               (style.labels["date"], style.date(date.fromisoformat(inv["invoice_date"]))),
               (style.labels["due"], style.date(date.fromisoformat(inv["due_date"]))),
               (style.labels["po"], inv["po_number"])]

    if layout_for(case) == "modern":
        page.text(LEFT, 740, vendor["name"], 16, bold=True)
        page.text(LEFT, 724, f"{address[0]}, {address[1]}  |  {style.labels['tax_id']} {vendor['tax_id']}", 8)
        page.rule(LEFT, 712, RIGHT, 1)
        page.text(LEFT, 690, style.title, 14, bold=True)
        y = 670
        for label, value in details:
            page.text(LEFT, y, label, 9)
            page.text(140, y, value, 9, bold=True)
            y -= 13
        page.text(330, 670, style.labels["bill_to"], 9, bold=True)
        for i, line in enumerate(BILL_TO):
            page.text(330, 657 - i * 12, line, 9)
    else:
        page.text(LEFT, 740, vendor["name"], 14, bold=True)
        for i, line in enumerate(address + [f"{style.labels['tax_id']}: {vendor['tax_id']}"]):
            page.text(LEFT, 725 - i * 12, line, 9)
        page.text(RIGHT, 740, style.title, 20, bold=True, right=True)
        y = 712
        for label, value in details:
            page.text(440, y, f"{label}:", 9, right=True)
            page.text(RIGHT, y, value, 9, right=True)
            y -= 13
        page.text(LEFT, 668, f"{style.labels['bill_to']}:", 9, bold=True)
        for i, line in enumerate(BILL_TO):
            page.text(LEFT, 655 - i * 12, line, 9)

    xs = QTY_FIRST_X if style.columns[0] == "quantity" else COLUMN_X
    y = 600
    page.band(LEFT - 4, y - 4, RIGHT - LEFT + 8, 16)
    for field, heading in zip(style.columns, style.headings):
        page.text(xs[field], y, heading, 9, bold=True, right=field != "description")
    y -= 20
    for line in inv["line_items"]:
        cells = {"description": line["description"], "quantity": str(line["quantity"]),
                 "unit_price": style.money(Decimal(line["unit_price"])), "amount": style.money(Decimal(line["amount"]))}
        for field in style.columns:
            page.text(xs[field], y, cells[field], 9, right=field != "description")
        y -= 15
    page.rule(LEFT, y + 6, RIGHT)

    y -= 12
    for label, value, bold in [(style.labels["subtotal"], inv["subtotal"], False),
                               (style.labels["tax"], inv["tax_amount"], False),
                               (style.labels["total"].format(currency=inv["currency"]), inv["total_amount"], True)]:
        page.text(440, y, label, 9, bold=bold, right=True)
        page.text(RIGHT, y, style.money(Decimal(value)), 10 if bold else 9, bold=bold, right=True)
        y -= 15

    y -= 20
    remit = inv["remit_to"]
    page.text(LEFT, y, style.remit.format(bank=remit["bank"], last4=remit["account_last4"]), 9, bold=True)
    y -= 18
    if inv["notes"]:
        page.text(LEFT, y, f"{style.labels['notes']}:", 9, bold=True)
        page.wrapped(LEFT + 60, y, inv["notes"], RIGHT - LEFT - 60)
    return _pdf(page.ops)


def main(number: int, out: Path):
    from evals import reading
    out.mkdir(parents=True, exist_ok=True)
    for case in reading.printed_cases(number):
        (out / f"{case['id']}.pdf").write_bytes(render(case))
    print(f"wrote {len(list(out.glob('*.pdf')))} PDFs to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    main(args.round, args.out)
