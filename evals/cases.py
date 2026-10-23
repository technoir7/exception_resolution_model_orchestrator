"""Invoices with known right answers, for measuring how well each way of
processing them decides what to pay.

Each case is built from one kind of situation an accounts-payable team meets,
and its documents settle the answer: a purchase order with its terms, a goods
receipt, the vendor's record (with the bank account on file), the vendor's
recent invoices, and the invoice itself. The answer is "pay" or "hold" (hold
means a person looks at it before any money moves). Nothing here asks a model
anything; the answer follows from how the case is built, and
`evals/tests/test_cases.py` checks that it does.

Each case has its own vendor, so one case's history can never make another
look like a duplicate. Cases are dated against a fixed day (`AS_OF`), so the
rules see the same thing whenever they run.

Round 1's audit found ways to guess without reading, and they are gone from
round 2 on: a vendor's notes can mislead ("Second notice" on an invoice never
paid, "Partial shipment" on one that bills more than arrived); overbilling
also shows up as a quantity off the PO, as a partial delivery does; a
resubmitted invoice may keep its number; paid history is numbered like the
vendor's other invoices; freight lands near its cap on both sides; and
vendors sell what their names say.
"""

import random
import re
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Dict, List

from evals import library as lib

AS_OF = date(2026, 10, 1)

# Kinds whose right answer is to pay; every other kind should be held.
PAY = {"clean", "partial_delivery", "freight_allowed", "tax_correct", "recurring_service", "unit_of_measure",
       "reworded_lines", "freight_at_cap", "repeat_shipment", "verified_bank_change", "partial_tax",
       "msa_freight_within_cap", "amended_price_in_effect", "latest_amended_price", "rush_fee_approved"}

# Kinds the rules and the three-way match flag. The rest pass them, so only a
# check that reads every invoice could catch the ones among them to hold.
FLAGGED = {
    "partial_delivery", "freight_allowed", "tax_correct", "recurring_service", "unit_of_measure",
    "price_increase", "overbilled_quantity", "duplicate", "freight_not_allowed", "tax_wrong",
    "vendor_mismatch",
    "reworded_lines", "freight_at_cap", "repeat_shipment", "partial_tax", "partial_freight_over_cap",
    "repeat_not_received",
    "msa_freight_within_cap", "msa_freight_not_allowed", "amended_price_in_effect", "amended_price_not_yet",
    "latest_amended_price", "rush_fee_approved", "rush_fee_unapproved",
}

# Exceptions are oversampled so each kind has enough cases to measure; results
# are reported per kind, so they can be reweighted to any real mix.
COUNTS = {
    "clean": 52,
    "partial_delivery": 14,
    "freight_allowed": 14,
    "tax_correct": 14,
    "recurring_service": 12,
    "unit_of_measure": 12,
    "price_increase": 12,
    "overbilled_quantity": 12,
    "duplicate": 10,
    "duplicate_late": 8,
    "freight_not_allowed": 12,
    "tax_wrong": 12,
    "bank_change": 10,
    "vendor_mismatch": 6,
}

# Round 3: errors the rules cannot see, look-alike pairs with opposite
# answers, and invoices worded and ordered differently from their POs.
COUNTS_3 = {
    "clean": 63,
    "reworded_lines": 15,
    "freight_at_cap": 10,
    "repeat_shipment": 12,
    "verified_bank_change": 10,
    "partial_tax": 10,
    "math_error": 12,
    "one_over": 12,
    "small_price_increase": 12,
    "partial_freight_over_cap": 10,
    "unverified_bank_change": 10,
    "duplicate_reworded": 12,
    "repeat_not_received": 12,
}


# Round 5: the terms that decide each invoice are in the vendor's agreement,
# its amendments, its emails or the AP policy manual, not on the PO (see
# `evals/library.py`). Look-alike pairs, and two of round 3's hidden errors as
# controls.
COUNTS_5 = {
    "clean": 50,
    "msa_freight_within_cap": 15,
    "msa_freight_not_allowed": 15,
    "amended_price_in_effect": 15,
    "amended_price_not_yet": 15,
    "latest_amended_price": 15,
    "superseded_price": 15,
    "rush_fee_approved": 15,
    "rush_fee_unapproved": 15,
    "one_over": 15,
    "small_price_increase": 15,
}
# Round 5 kinds that no document decides.
UNDECIDED_5 = {"clean", "one_over", "small_price_increase"}


def counts_for(round_number: int) -> Dict[str, int]:
    if round_number >= 5:
        return COUNTS_5
    return COUNTS_3 if round_number >= 3 else COUNTS


REASONS = {
    "clean": "matches the PO and the receipt",
    "partial_delivery": "bills the quantities received on a partial delivery",
    "freight_allowed": "freight within what the PO allows",
    "tax_correct": "sales tax at the PO's rate",
    "recurring_service": "a new week of a weekly service, not a repeat",
    "unit_of_measure": "the same goods counted in smaller units",
    "price_increase": "unit price above the PO's fixed price",
    "overbilled_quantity": "bills more than was received",
    "duplicate": "repeats an invoice already paid",
    "duplicate_late": "repeats an invoice already paid",
    "freight_not_allowed": "freight the PO does not allow, or more than its cap",
    "tax_wrong": "sales tax not at the PO's rate",
    "bank_change": "asks for payment to an account not on file",
    "vendor_mismatch": "billed by a vendor other than the PO's",
    "reworded_lines": "the PO's lines in other words and another order",
    "freight_at_cap": "freight exactly at the PO's cap",
    "repeat_shipment": "the second of two shipments the PO asked for, both received",
    "verified_bank_change": "the bank account the vendor record was updated to",
    "partial_tax": "a partial delivery billed as received, with tax at the PO's rate",
    "math_error": "a line's amount is more than its quantity times its price",
    "one_over": "bills one unit more than was received",
    "small_price_increase": "a unit price slightly above the PO's fixed price",
    "partial_freight_over_cap": "a partial delivery with freight above the PO's cap",
    "unverified_bank_change": "asks for payment to an account not on file",
    "duplicate_reworded": "repeats an invoice already paid, reworded",
    "repeat_not_received": "bills a second shipment that has not arrived",
    "msa_freight_within_cap": "freight within the agreement's cap",
    "msa_freight_not_allowed": "freight under an agreement whose prices are delivered",
    "amended_price_in_effect": "a price an amendment in effect set",
    "amended_price_not_yet": "a price from an amendment not yet in effect",
    "latest_amended_price": "the price the latest amendment set",
    "superseded_price": "a price a later amendment replaced",
    "rush_fee_approved": "a rush fee Purchasing approved in writing",
    "rush_fee_unapproved": "a rush fee with no written approval",
}

CENT = Decimal("0.01")

# What each trade sells: (description, low price, high price, low qty, high qty).
GOODS = {
    "Industrial Supply": [
        ("Hex bolt M10 x 40, zinc", 0.42, 0.95, 200, 2000),
        ("Hydraulic hose assembly 1/2 in", 38, 74, 4, 40),
        ("Industrial degreaser, 5 gal", 64, 112, 2, 24),
        ("Bearing 6205-2RS", 5.5, 12.4, 20, 250),
        ("Shop towels, box of 200", 21, 36, 6, 60),
        ("Stainless sheet 16 ga 4x8", 186, 289, 2, 20),
        ("Fork truck tire, press-on", 210, 340, 2, 8),
        ("Cordless drill 20V kit", 129, 219, 2, 12),
    ],
    "Packaging": [
        ("Pallet wrap film 18 in x 1500 ft", 16, 29, 10, 120),
        ("Shipping cartons 18x12x12, bundle of 25", 27, 44, 6, 80),
        ("Label rolls 4x6 thermal", 11, 19, 10, 120),
        ("Packing tape 2 in x 110 yd, case of 36", 38, 62, 4, 40),
        ("Air pillow void fill, roll", 44, 79, 2, 30),
    ],
    "Office Products": [
        ("Copy paper, letter, 10-ream carton", 41, 58, 5, 60),
        ("Toner cartridge, black, high yield", 89, 165, 2, 30),
        ("Laptop docking station USB-C", 149, 259, 2, 25),
        ("Ethernet patch cable Cat6 10 ft", 4.6, 9.9, 20, 300),
        ("Ergonomic mesh desk chair", 189, 329, 2, 15),
    ],
    "Electrical": [
        ("LED high-bay fixture 150W", 118, 196, 4, 40),
        ("Cable ties 8 in, pack of 100", 4.2, 9.5, 20, 200),
        ("THHN wire 12 AWG, 500 ft spool", 64, 118, 2, 30),
        ("Circuit breaker 20A single pole", 6.5, 14, 10, 120),
        ("Conduit EMT 3/4 in x 10 ft", 7.8, 13.9, 20, 200),
    ],
    "Safety Products": [
        ("Safety glasses, clear anti-fog", 3.1, 6.8, 24, 300),
        ("Work gloves, cut level A4, pair", 7.8, 15.5, 24, 240),
        ("Hi-vis vest, class 2", 6.2, 13.5, 12, 200),
        ("Earplugs, box of 200 pairs", 24, 39, 4, 50),
        ("First aid kit, 50-person", 45, 88, 2, 20),
    ],
}

# Goods bought by the case and billed by the each: (name, unit, pack, low, high, trade).
PACKED = [
    ("Nitrile exam gloves", "box", 10, 7.2, 11.5, "Safety Products"),
    ("Bottled water 16.9 oz", "bottle", 24, 0.38, 0.69, "Office Products"),
    ("AA alkaline batteries", "4-pack", 12, 3.9, 6.9, "Electrical"),
    ("Floor marking tape 2 in", "roll", 12, 8.5, 14.0, "Safety Products"),
    ("Disinfecting wipes", "canister", 6, 5.2, 8.9, "Safety Products"),
    ("Printer paper, letter", "ream", 10, 4.4, 6.6, "Office Products"),
]
PACK_ORDERED = ["{name}, case of {pack} ({unit}s)", "{name} - CS/{pack}", "{name}, {pack} {unit}s per case"]
PACK_BILLED = ["{name} ({unit})", "{name}, per {unit}", "{name} - EA"]

SERVICES = [
    ("Janitorial service", 380, 1450, "Facility Services"),
    ("Security patrol", 900, 2600, "Security Services"),
    ("Grounds maintenance", 260, 980, "Grounds Care"),
    ("Scissor lift rental", 410, 760, "Equipment Rental"),
    ("Waste hauling", 180, 640, "Waste Services"),
]

NAME_FIRST = ["Northwind", "Bluegate", "Cedar Ridge", "Harbor", "Summit", "Ironleaf", "Prairie", "Keystone",
              "Redwood", "Lakeshore", "Granite", "Silverline", "Oakmont", "Pioneer", "Riverbend", "Westfield"]
NAME_SUFFIX = ["Inc", "LLC", "Co", "Corp", "Ltd"]
BANKS = ["First Harbor Bank", "Mercantile Trust", "Pacific Commerce Bank", "Union Plains Bank",
         "Citizens Savings", "Heritage National Bank", "Summit Credit Union"]

FREIGHT_INCLUDED = [
    "Freight: included in prices (FOB destination).",
    "Delivered pricing; no separate freight or shipping charges.",
    "Prices include delivery. Do not bill freight.",
]
FREIGHT_CAPPED = [
    "Freight: billable at cost, not to exceed ${cap} per shipment.",
    "Shipping may be invoiced at actual cost up to ${cap}.",
    "Freight prepaid and added, capped at ${cap}.",
]
TAX_EXEMPT = [
    "Sales tax: exempt (resale certificate on file).",
    "Tax exempt purchase; certificate on file.",
]
TAX_RATE = [
    "Sales tax: {rate}% applies to goods.",
    "Taxable at {rate}%.",
]
PRICE_FIXED = [
    "Prices are fixed for the life of this PO.",
    "Unit prices firm; changes require a PO amendment.",
]
BANK_CHANGED = [
    "Please note: our bank details have changed. Kindly update your records and remit to the account below.",
    "IMPORTANT - new remittance details effective immediately. Payments to the old account will be returned.",
]
# Notes that say nothing about whether to pay, on every kind of invoice.
NEUTRAL = [
    "Thank you for your business.",
    "Please include the invoice number with your payment.",
    "Questions about this invoice? Contact our accounts receivable team.",
    "ACH payment preferred.",
]
# A reminder about an invoice never paid is no reason to hold it.
REMINDER = ["Second notice.", "Reminder: this invoice is now due."]


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _s(value: Decimal) -> str:
    return str(_money(value))


def _line(number: int, description: str, quantity: int, unit_price: Decimal, **extra) -> Dict:
    return {"line_number": number, "description": description, "quantity": quantity,
            "unit_price": _s(unit_price), "amount": _s(unit_price * quantity), **extra}


def _subtotal(lines) -> Decimal:
    return sum((Decimal(l["amount"]) for l in lines), Decimal(0))


class _Builder:
    def __init__(self, rng: random.Random, number: int, kind: str):
        self.rng, self.n, self.kind = rng, number, kind
        if kind == "recurring_service":
            self.service = rng.choice(SERVICES)
            trade = self.service[3]
        elif kind == "unit_of_measure":
            self.packed = rng.choice(PACKED)
            trade = self.packed[5]
        else:
            trade = rng.choice(sorted(GOODS))
        self.trade = trade
        self.vendor = self._vendor(number, trade)
        start = AS_OF - timedelta(days=300)
        self.po_date = start + timedelta(days=rng.randint(0, 220))
        self.receipt_date = self.po_date + timedelta(days=rng.randint(4, 18))
        self.invoice_date = self.receipt_date + timedelta(days=rng.randint(1, 6))
        prefix = "".join(w[0] for w in self.vendor["name"].split()[:2]).upper()
        self.number_format = rng.choice(["INV-{:05d}", prefix + "-{:04d}", "{:06d}"])
        low = {"INV-{:05d}": 10000, "{:06d}": 100000}.get(self.number_format, 1000)
        self.number_base = rng.randint(low + 500, low * 9)
        self.invoice_number = self.number_format.format(self.number_base)
        # Unique across the set (the database requires it), without counting up.
        self.po_number = f"PO-{self.po_date.year}-{(number * 37) % 9000 + 1000}"

    def _vendor(self, number: int, trade: str) -> Dict:
        rng = self.rng
        return {
            "id": f"V{number:04d}",
            "name": f"{rng.choice(NAME_FIRST)} {trade} {rng.choice(NAME_SUFFIX)}",
            "tax_id": f"{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}",
            "remit_to": {"bank": rng.choice(BANKS), "account_last4": f"{rng.randint(0, 9999):04d}"},
            "payment_terms": rng.choice(["NET30", "NET45"]),
        }

    def note(self, *specific: str, neutral: float = 0.3) -> str:
        """One of the notes this kind of invoice might carry, a neutral one, or none."""
        roll = self.rng.random()
        if roll < neutral:
            return self.rng.choice(NEUTRAL)
        return self.rng.choice(list(specific)) if specific else ""

    def goods(self, count=None) -> List[Dict]:
        rng = self.rng
        catalogue = GOODS[self.trade]
        picks = rng.sample(catalogue, count or rng.randint(1, 3))
        return [
            _line(i, name, rng.randint(lo_q, hi_q), _money(rng.uniform(lo_p, hi_p)))
            for i, (name, lo_p, hi_p, lo_q, hi_q) in enumerate(picks, 1)
        ]

    def terms(self, freight: str, tax: str, cap=None, rate=None) -> str:
        rng = self.rng
        parts = [rng.choice(PRICE_FIXED)]
        parts.append(rng.choice(FREIGHT_INCLUDED) if freight == "included"
                     else rng.choice(FREIGHT_CAPPED).replace("{cap}", _s(cap)))
        parts.append(rng.choice(TAX_EXEMPT) if tax == "exempt"
                     else rng.choice(TAX_RATE).format(rate=_pct(rate)))
        parts.append(f"Payment terms: {self.vendor['payment_terms'].replace('NET', 'Net ')}.")
        return " ".join(parts)

    def po(self, lines, freight="included", cap=None, tax_rate=Decimal(0), vendor=None) -> Dict:
        vendor = vendor or self.vendor
        return {
            "po_number": self.po_number,
            "po_date": self.po_date.isoformat(),
            "vendor_id": vendor["id"],
            "vendor_name": vendor["name"],
            "currency": "USD",
            "terms": self.terms(freight, "exempt" if tax_rate == 0 else "rate", cap, tax_rate),
            "freight": {"billable": freight == "capped", "cap": _s(cap) if cap is not None else None},
            "tax_rate": str(tax_rate),
            "line_items": lines,
            "total_amount": _s(_subtotal(lines)),
        }

    def receipt(self, po_lines, received=None) -> Dict:
        received = received or {l["line_number"]: l["quantity"] for l in po_lines}
        prices = {l["line_number"]: Decimal(l["unit_price"]) for l in po_lines}
        return {
            "receipt_number": f"RCV-{(self.n * 53) % 90000 + 10000}",
            "receipt_date": self.receipt_date.isoformat(),
            "po_number": self.po_number,
            "vendor_id": self.vendor["id"],
            "line_items": [
                {"line_number": l["line_number"], "description": l["description"], "quantity": received[l["line_number"]]}
                for l in po_lines
            ],
            "total_amount": _s(sum(prices[n] * q for n, q in received.items())),
        }

    def invoice(self, lines, tax=Decimal(0), notes="", remit_to=None, number=None, on=None, vendor=None, **extra) -> Dict:
        vendor = vendor or self.vendor
        on = on or self.invoice_date
        subtotal = _subtotal(lines)
        days = int(self.vendor["payment_terms"][3:])
        return {
            "invoice_number": number or self.invoice_number,
            "invoice_date": on.isoformat(),
            "due_date": (on + timedelta(days=days)).isoformat(),
            "vendor_id": vendor["id"],
            "vendor_name": vendor["name"],
            "po_number": self.po_number,
            "currency": "USD",
            "subtotal": _s(subtotal),
            "tax_amount": _s(tax),
            "total_amount": _s(subtotal + tax),
            "line_items": lines,
            "remit_to": remit_to or dict(vendor["remit_to"]),
            "notes": notes,
            **extra,
        }

    def background(self) -> List[Dict]:
        """Paid invoices from the vendor for its earlier orders, numbered as its
        invoices are, so that a history alone says nothing about the case."""
        if self.trade not in GOODS:
            return []
        out = []
        count = self.rng.choice([0, 1, 1, 2])
        offsets = sorted(self.rng.sample(range(5, 120), count))
        for i in range(count):
            on = self.invoice_date - timedelta(days=self.rng.randint(20, 90))
            lines = self.goods()
            subtotal = _subtotal(lines)
            while True:
                po_number = f"PO-{on.year}-{self.rng.randint(1000, 9999)}"
                if po_number != self.po_number:
                    break
            out.append({
                "invoice_number": self.number_format.format(self.number_base - offsets[i]),
                "invoice_date": on.isoformat(),
                "po_number": po_number,
                "subtotal": _s(subtotal), "tax_amount": "0.00", "total_amount": _s(subtotal),
                "line_items": lines, "status": "paid",
            })
        return out


def _round_up(amount: Decimal) -> Decimal:
    """Caps are round sums, as a buyer would write them."""
    return Decimal(25) * (amount / 25).to_integral_value(rounding=ROUND_CEILING)


def _round_down(amount: Decimal) -> Decimal:
    return Decimal(25) * (amount / 25).to_integral_value(rounding=ROUND_FLOOR)


def _pct(rate: Decimal) -> str:
    return f"{rate * 100:.2f}".rstrip("0").rstrip(".")


def _tax(subtotal: Decimal, rate: Decimal) -> Decimal:
    return _money(subtotal * rate)


def _resubmitted_number(number: str, rng: random.Random) -> str:
    """A resubmitted invoice often keeps its number, or nearly."""
    variants = [number, number, number + "-R", number + "A", number + "-1"]
    if "-" in number:
        variants.append(number.replace("-", ""))
    return rng.choice(variants)


ABBREVIATIONS = [
    ("assembly", "ASSY"), ("pack of ", "PK/"), ("box of ", "BX/"), ("bundle of ", "BDL/"), ("case of ", "CS/"),
    ("black", "BLK"), ("high yield", "HY"), ("stainless", "SS"), ("fixture", "FIXT"), ("cartridge", "CART"),
    ("industrial", "IND"), ("circuit breaker", "CB"), ("single pole", "1P"), ("ergonomic", "ERGO"),
    ("thermal", "THRM"), ("cordless", "CRDLS"), ("press-on", "PRESS ON"), ("anti-fog", "AF"),
]


def _reword(description: str, rng: random.Random) -> str:
    """How a vendor's own system tends to describe what a PO ordered."""
    text = description
    for long, short in ABBREVIATIONS:
        text = re.sub(re.escape(long), short, text, flags=re.I)
    text = text.replace(",", "").upper()
    return f"{rng.choice(['SKU', 'ITEM ', '#', 'P/N '])}{rng.randint(10000, 99999)} {text}"


def _over(po_lines, at_least: Decimal, make) -> List[Dict]:
    """`make()` until the invoice total exceeds the PO's by at least `at_least`."""
    po_total = _subtotal(po_lines)
    while True:
        lines = make()
        if _subtotal(lines) >= po_total * (1 + at_least):
            return lines


def _build(rng: random.Random, number: int, kind: str) -> Dict:
    b = _Builder(rng, number, kind)
    case = {"id": f"c{number:03d}", "kind": kind, "as_of": AS_OF.isoformat(),
            "truth": {"decision": "pay" if kind in PAY else "hold", "reason": REASONS[kind]},
            "vendor": b.vendor}
    history = b.background()

    if kind == "clean":
        lines = b.goods()
        po = b.po(lines, freight=rng.choice(["included", "capped"]), cap=Decimal(25 * rng.randint(3, 10)))
        receipt = b.receipt(lines)
        invoice = b.invoice([dict(l) for l in lines], notes=b.note("", "", "", *REMINDER))

    elif kind in ("partial_delivery", "overbilled_quantity"):
        lines = b.goods()
        while True:
            received = {l["line_number"]: l["quantity"] for l in lines}
            short = rng.choice(lines)
            received[short["line_number"]] = max(1, int(short["quantity"] * rng.uniform(0.35, 0.85)))
            if _subtotal(lines) - sum(Decimal(l["unit_price"]) * received[l["line_number"]] for l in lines) \
                    >= _subtotal(lines) * Decimal("0.05"):
                break
        po, receipt = b.po(lines), b.receipt(lines, received)
        if kind == "partial_delivery":
            billed = {n: q for n, q in received.items()}
            note = b.note("", "Partial shipment; balance to follow.", "Backordered items will ship separately.")
        else:
            got, ordered = received[short["line_number"]], short["quantity"]
            # Either the whole order, or more than arrived but less than ordered.
            billed = {n: q for n, q in received.items()}
            billed[short["line_number"]] = rng.choice(
                [ordered, rng.randint(min(ordered, max(got + 1, int(got * 1.15) + 1)), ordered)])
            note = b.note("", "", "Partial shipment; balance to follow.")
        invoice = b.invoice([_line(l["line_number"], l["description"], billed[l["line_number"]],
                                   Decimal(l["unit_price"])) for l in lines], notes=note)

    elif kind in ("freight_allowed", "freight_not_allowed"):
        lines = b.goods()
        subtotal = _subtotal(lines)
        charge = _money(subtotal * Decimal(str(rng.uniform(0.02, 0.08))) + rng.randint(15, 40))
        # Freight lands near its cap on either side, so the numbers must be read.
        if kind == "freight_allowed":
            po = b.po(lines, freight="capped", cap=_round_up(charge + rng.randint(0, 40)))
        else:
            cap = _round_down(charge * Decimal(str(rng.uniform(0.7, 0.98))))
            po = b.po(lines, freight="included") if rng.random() < 0.5 or cap < 25 else \
                b.po(lines, freight="capped", cap=cap)
        freight_line = _line(len(lines) + 1, rng.choice(["Freight", "Shipping & handling", "Freight charges"]),
                             1, charge, is_freight=True)
        receipt = b.receipt(lines)
        invoice = b.invoice([dict(l) for l in lines] + [freight_line],
                            notes=b.note("", "", *REMINDER) if kind == "freight_allowed" else b.note(""))

    elif kind in ("tax_correct", "tax_wrong"):
        lines = b.goods()
        rate = Decimal(rng.choice(["0.0625", "0.0725", "0.0825", "0.0875", "0.095"]))
        if kind == "tax_correct":
            po, charged = b.po(lines, tax_rate=rate), rate
        elif rng.random() < 0.5:
            po, charged = b.po(lines), rate
        else:
            po_rate = Decimal(rng.choice(["0.0625", "0.0725", "0.0825"]))
            charged = Decimal(rng.choice([r for r in ("0.0725", "0.0825", "0.0875", "0.095") if Decimal(r) > po_rate]))
            po = b.po(lines, tax_rate=po_rate)
        receipt = b.receipt(lines)
        invoice = b.invoice([dict(l) for l in lines], tax=_tax(_subtotal(lines), charged),
                            notes=b.note("", "", *REMINDER) if kind == "tax_correct" else b.note(""))

    elif kind == "recurring_service":
        name, lo, hi, _ = b.service
        weekly = _money(rng.uniform(lo, hi))
        weeks = rng.randint(8, 26)
        po = b.po([_line(1, f"{name}, weekly", weeks, weekly)])
        receipt = None
        week = b.invoice_date - timedelta(days=b.invoice_date.weekday())
        def bill(start):
            return [_line(1, f"{name}, week of {start.isoformat()}", 1, weekly)]
        previous = b.invoice(bill(week - timedelta(days=7)), number=b.number_format.format(b.number_base - 1),
                             on=b.invoice_date - timedelta(days=7),
                             service_period=(week - timedelta(days=7)).isoformat())
        previous["status"] = "paid"
        history = [previous]
        invoice = b.invoice(bill(week), service_period=week.isoformat(), notes=b.note(""))

    elif kind == "unit_of_measure":
        name, unit, pack, lo, hi, _ = b.packed
        each = _money(rng.uniform(lo, hi))
        cases_ordered = rng.randint(6, 40)
        ordered_as = rng.choice(PACK_ORDERED).format(name=name, pack=pack, unit=unit)
        po_line = _line(1, ordered_as, cases_ordered, each * pack, pack_size=pack, unit="case")
        po = b.po([po_line])
        receipt = b.receipt([po_line])
        billed_as = rng.choice(PACK_BILLED).format(name=name, unit=unit)
        invoice = b.invoice([_line(1, billed_as, cases_ordered * pack, each)], notes=b.note(""))

    elif kind == "price_increase":
        lines = b.goods()
        po = b.po(lines)
        def raised():
            target = rng.choice(lines)
            factor = Decimal(str(rng.uniform(1.04, 1.15)))
            return [_line(l["line_number"], l["description"], l["quantity"],
                          _money(Decimal(l["unit_price"]) * factor) if l is target else Decimal(l["unit_price"]))
                    for l in lines]
        billed = _over(lines, Decimal("0.015"), raised)
        receipt = b.receipt(lines)
        invoice = b.invoice(billed, notes=b.note(
            "", "Price adjustment reflects current raw material costs.", "Updated pricing per our notice."))

    elif kind in ("duplicate", "duplicate_late"):
        lines = b.goods()
        po, receipt = b.po(lines), b.receipt(lines)
        paid = b.invoice([dict(l) for l in lines], on=b.invoice_date)
        paid["status"] = "paid"
        late = kind == "duplicate_late"
        gap = rng.randint(10, 35) if late else rng.randint(1, 6)
        invoice = b.invoice([dict(l) for l in lines], number=_resubmitted_number(b.invoice_number, rng),
                            on=b.invoice_date + timedelta(days=gap),
                            notes=b.note("", "Resubmitted for payment.", "Copy of invoice.",
                                         *(REMINDER if late else [])))
        history = sorted(history + [paid], key=lambda h: h["invoice_date"], reverse=True)

    elif kind == "bank_change":
        lines = b.goods()
        po, receipt = b.po(lines), b.receipt(lines)
        other = {"bank": rng.choice([x for x in BANKS if x != b.vendor["remit_to"]["bank"]]),
                 "account_last4": f"{rng.randint(0, 9999):04d}"}
        invoice = b.invoice([dict(l) for l in lines], remit_to=other, notes=b.note("", *BANK_CHANGED))

    elif kind == "vendor_mismatch":
        lines = b.goods()
        po_vendor = b._vendor(500 + number, b.trade)
        po_vendor["name"] = b.vendor["name"].rsplit(" ", 1)[0] + " " + rng.choice(
            [s for s in NAME_SUFFIX if not b.vendor["name"].endswith(s)])
        po = b.po(lines, vendor=po_vendor)
        receipt = b.receipt(lines)
        receipt["vendor_id"] = po_vendor["id"]
        invoice = b.invoice([dict(l) for l in lines], notes=b.note(""))
        case["po_vendor"] = po_vendor

    elif kind == "reworded_lines":
        while True:
            lines = b.goods(count=rng.choice([2, 3]))
            order = lines[1:] + lines[:1]
            # Matched by line number, as the rules match, every line is off.
            if all(abs(a["quantity"] - p["quantity"]) > p["quantity"] * 0.06 for a, p in zip(order, lines)):
                break
        po, receipt = b.po(lines), b.receipt(lines)
        billed = [_line(i, _reword(l["description"], rng), l["quantity"], Decimal(l["unit_price"]))
                  for i, l in enumerate(order, 1)]
        invoice = b.invoice(billed, notes=b.note(""))

    elif kind == "freight_at_cap":
        lines = b.goods()
        cap = _round_up(_subtotal(lines) * Decimal(str(rng.uniform(0.02, 0.06))) + 15)
        po, receipt = b.po(lines, freight="capped", cap=cap), b.receipt(lines)
        freight_line = _line(len(lines) + 1, rng.choice(["Freight", "Shipping & handling", "Freight charges"]),
                             1, cap, is_freight=True)
        invoice = b.invoice([dict(l) for l in lines] + [freight_line], notes=b.note(""))

    elif kind in ("repeat_shipment", "repeat_not_received"):
        half = b.goods()
        lines = [_line(l["line_number"], l["description"], l["quantity"] * 2, Decimal(l["unit_price"])) for l in half]
        po = b.po(lines)
        po["terms"] = po["terms"].replace("Payment terms", "Deliver in two equal shipments; invoice each shipment. "
                                                             "Payment terms", 1)
        first_qty = {l["line_number"]: l["quantity"] for l in half}
        receipt = b.receipt(lines, first_qty)
        first_on = b.receipt_date + timedelta(days=rng.randint(1, 4))
        paid = b.invoice([dict(l) for l in half], number=b.number_format.format(b.number_base - 1), on=first_on)
        paid["status"] = "paid"
        second_arrival = b.receipt_date + timedelta(days=rng.randint(14, 30))
        if kind == "repeat_shipment":
            second = b.receipt(lines, first_qty)
            second["receipt_number"] = f"RCV-{(number * 53) % 90000 + 10001}"
            second["receipt_date"] = second_arrival.isoformat()
            case["extra_receipts"] = [second]
        invoice = b.invoice([dict(l) for l in half], on=second_arrival + timedelta(days=rng.randint(1, 4)),
                            notes=b.note("", "Second shipment.", "Balance of order."))
        history = sorted(history + [paid], key=lambda h: h["invoice_date"], reverse=True)

    elif kind in ("verified_bank_change", "unverified_bank_change"):
        lines = b.goods()
        po, receipt = b.po(lines), b.receipt(lines)
        new = {"bank": rng.choice([x for x in BANKS if x != b.vendor["remit_to"]["bank"]]),
               "account_last4": f"{rng.randint(0, 9999):04d}"}
        if kind == "verified_bank_change":
            old_account = b.vendor["remit_to"]
            b.vendor["remit_to"] = new
            b.vendor["remit_updated_on"] = (b.invoice_date - timedelta(days=rng.randint(10, 60))).isoformat()
            b.vendor["remit_previous"] = f"{old_account['bank']}, account ending {old_account['account_last4']}"
            notes = b.note("", *BANK_CHANGED)
        else:
            notes = b.note(*BANK_CHANGED, "As agreed by phone with your accounts payable team, please pay the "
                                          "new account below.", neutral=0.1)
        invoice = b.invoice([dict(l) for l in lines], remit_to=new, notes=notes)

    elif kind in ("partial_tax", "partial_freight_over_cap"):
        lines = b.goods()
        while True:
            got = {l["line_number"]: l["quantity"] for l in lines}
            short = rng.choice(lines)
            got[short["line_number"]] = max(1, int(short["quantity"] * rng.uniform(0.35, 0.85)))
            if got[short["line_number"]] < short["quantity"]:
                break
        billed = [_line(l["line_number"], l["description"], got[l["line_number"]], Decimal(l["unit_price"]))
                  for l in lines]
        receipt = b.receipt(lines, got)
        if kind == "partial_tax":
            rate = Decimal(rng.choice(["0.0625", "0.0725", "0.0825", "0.0875", "0.095"]))
            po = b.po(lines, tax_rate=rate)
            invoice = b.invoice(billed, tax=_tax(_subtotal(billed), rate),
                                notes=b.note("", "Partial shipment; balance to follow."))
        else:
            charge = _money(_subtotal(billed) * Decimal(str(rng.uniform(0.02, 0.06))) + rng.randint(20, 40))
            cap = _round_down(charge * Decimal(str(rng.uniform(0.6, 0.95))))
            cap = cap if cap >= 25 else Decimal(25)
            charge = max(charge, cap + Decimal("5.00"))
            po = b.po(lines, freight="capped", cap=cap)
            freight_line = _line(len(lines) + 1, rng.choice(["Freight", "Shipping & handling"]), 1, charge,
                                 is_freight=True)
            invoice = b.invoice(billed + [freight_line], notes=b.note("", "Partial shipment; balance to follow."))

    elif kind == "math_error":
        lines = b.goods()
        po, receipt = b.po(lines), b.receipt(lines)
        target = rng.choice(lines)
        # Small enough that the total stays within the rules' 1% tolerance.
        extra = max(Decimal("1.00"), _money(_subtotal(lines) * Decimal(str(rng.uniform(0.003, 0.009)))))
        billed = [dict(l, amount=_s(Decimal(l["amount"]) + extra)) if l is target else dict(l) for l in lines]
        invoice = b.invoice(billed, notes=b.note(""))

    elif kind == "one_over":
        while True:
            lines = b.goods(count=rng.choice([2, 3]))
            total = _subtotal(lines)
            fits = [l for l in lines if l["quantity"] >= 40 and Decimal(l["unit_price"]) < total * Decimal("0.008")]
            if fits:
                break
        target = rng.choice(fits)
        po, receipt = b.po(lines), b.receipt(lines)
        billed = [_line(l["line_number"], l["description"], l["quantity"] + (l is target), Decimal(l["unit_price"]))
                  for l in lines]
        invoice = b.invoice(billed, notes=b.note(""))

    elif kind == "small_price_increase":
        while True:
            lines = b.goods()
            target = rng.choice(lines)
            raised = _money(Decimal(target["unit_price"]) * Decimal(str(rng.uniform(1.003, 1.009))))
            if raised == Decimal(target["unit_price"]):
                raised += CENT
            billed = [_line(l["line_number"], l["description"], l["quantity"],
                            raised if l is target else Decimal(l["unit_price"])) for l in lines]
            if _subtotal(billed) < _subtotal(lines) * Decimal("1.01"):
                break
        po, receipt = b.po(lines), b.receipt(lines)
        invoice = b.invoice(billed, notes=b.note("", "", "Updated pricing per our notice."))

    elif kind == "duplicate_reworded":
        lines = b.goods()
        po, receipt = b.po(lines), b.receipt(lines)
        paid = b.invoice([dict(l) for l in lines], on=b.invoice_date)
        paid["status"] = "paid"
        reworded = [_line(l["line_number"], _reword(l["description"], rng), l["quantity"], Decimal(l["unit_price"]))
                    for l in lines]
        invoice = b.invoice(reworded, number=_resubmitted_number(b.invoice_number, rng),
                            on=b.invoice_date + timedelta(days=rng.randint(10, 35)),
                            notes=b.note("", "", *REMINDER))
        history = sorted(history + [paid], key=lambda h: h["invoice_date"], reverse=True)

    else:
        raise ValueError(f"unknown kind {kind}")

    case.update(po=po, receipt=receipt, history=history, invoice=invoice)
    return case


RUSH_LINES = ["Expedite fee", "Rush charge", "Expedited shipping surcharge", "Priority handling fee"]
RUSH_FEES = [45, 60, 75, 95, 120, 150, 175, 225]


def _build_with_documents(rng: random.Random, number: int, kind: str) -> Dict:
    """A round 5 case: the PO refers to the vendor's agreement, and the
    agreement, its amendments, its emails and the AP policy manual decide."""
    # Kinds that need no document of their own are built as before.
    case = _build(rng, number, kind) if kind in UNDECIDED_5 else None
    b = _Builder(rng, number, "clean")
    if case:
        # Rebuild the builder's dates from the case, so the documents fit it.
        b.vendor = case["vendor"]
        b.po_date, b.receipt_date = date.fromisoformat(case["po"]["po_date"]), \
            date.fromisoformat(case["receipt"]["receipt_date"])
        b.invoice_date = date.fromisoformat(case["invoice"]["invoice_date"])
        b.po_number = case["po"]["po_number"]
    else:
        case = {"id": f"c{number:03d}", "kind": kind, "as_of": AS_OF.isoformat(),
                "truth": {"decision": "pay" if kind in PAY else "hold", "reason": REASONS[kind]},
                "vendor": b.vendor}
    msa = lib.msa_number(b.vendor, rng)
    msa_date = b.po_date - timedelta(days=rng.randint(240, 700))
    docs = lib.Library(rng, b.vendor, msa, msa_date, AS_OF)
    terms = {"freight": {"billable": False, "cap": None}, "price_changes": [], "rush": None}
    deciding: List[str] = []
    changes = []  # (item, price, effective) for the case's own price amendments

    if kind in UNDECIDED_5:
        po, receipt, invoice, history = case["po"], case["receipt"], case["invoice"], case["history"]
        freight = rng.choice(["included", "capped"])
        cap = Decimal(25 * rng.randint(3, 10)) if freight == "capped" else None
    else:
        history = b.background()
        lines = b.goods()
        po_lines, billed = lines, [dict(l) for l in lines]
        freight, cap = rng.choice(["included", "capped"]), None
        if freight == "capped":
            cap = Decimal(25 * rng.randint(3, 10))
        extra = []

        if kind in ("msa_freight_within_cap", "msa_freight_not_allowed"):
            charge = _money(_subtotal(lines) * Decimal(str(rng.uniform(0.02, 0.08))) + rng.randint(15, 40))
            if kind == "msa_freight_within_cap":
                freight, cap = "capped", _round_up(charge + rng.randint(0, 40))
            else:
                freight, cap = "included", None
            extra = [_line(len(lines) + 1, rng.choice(["Freight", "Shipping & handling", "Freight charges"]),
                           1, charge, is_freight=True)]

        elif kind in ("amended_price_in_effect", "amended_price_not_yet"):
            # Big enough for the rules to flag, so the pair differs only in the date.
            while True:
                target = rng.choice(lines)
                raised = _money(Decimal(target["unit_price"]) * Decimal(str(rng.uniform(1.03, 1.12))))
                rise = (raised - Decimal(target["unit_price"])) * target["quantity"]
                if rise >= _subtotal(lines) * Decimal("0.015"):
                    break
            if kind == "amended_price_in_effect":
                span = max(1, (b.invoice_date - b.po_date).days)
                effective = b.po_date + timedelta(days=rng.randint(1, span))
            else:
                effective = b.invoice_date + timedelta(days=rng.randint(5, 45))
            changes.append((target["description"], raised, effective))
            billed = [_line(l["line_number"], l["description"], l["quantity"],
                            raised if l is target else Decimal(l["unit_price"])) for l in lines]

        elif kind in ("latest_amended_price", "superseded_price"):
            target = rng.choice(lines)
            first_price = Decimal(target["unit_price"])  # the PO was raised at the first amendment's price
            first_on = b.po_date - timedelta(days=rng.randint(10, 120))
            span = max(1, (b.invoice_date - b.po_date).days)
            latest_on = b.po_date + timedelta(days=rng.randint(1, span))
            while True:
                if kind == "latest_amended_price":
                    factor = rng.choice([rng.uniform(0.85, 0.97), rng.uniform(1.03, 1.15)])
                else:
                    factor = rng.uniform(0.85, 0.97)
                latest_price = _money(first_price * Decimal(str(factor)))
                # A latest price billed is a change from the PO the rules see.
                if abs(latest_price - first_price) * target["quantity"] >= _subtotal(lines) * Decimal("0.015"):
                    break
                target = rng.choice(lines)
                first_price = Decimal(target["unit_price"])
            changes += [(target["description"], first_price, first_on),
                        (target["description"], latest_price, latest_on)]
            charged = latest_price if kind == "latest_amended_price" else first_price
            billed = [_line(l["line_number"], l["description"], l["quantity"],
                            charged if l is target else Decimal(l["unit_price"])) for l in lines]

        elif kind in ("rush_fee_approved", "rush_fee_unapproved"):
            amount = _money(rng.choice(RUSH_FEES))
            extra = [_line(len(lines) + 1, rng.choice(RUSH_LINES), 1, amount, is_fee=True)]
            offered = b.receipt_date - timedelta(days=rng.randint(6, 15))
            docs.email(offered, f"Expedite option for {b.po_number}", docs.contact, lib.BUYER_MAIL,
                       f"We can expedite {b.po_number} to arrive by {b.receipt_date.isoformat()} for a rush fee "
                       f"of ${amount}. Please confirm in writing if you would like us to go ahead.")
            replied = offered + timedelta(days=rng.randint(0, 2))
            form = "approved" if kind == "rush_fee_approved" else rng.choice(["none", "declined", "other_po", "phone"])
            if form == "approved":
                subject = docs.email(replied, f"Re: Expedite option for {b.po_number}", lib.BUYER_MAIL, docs.contact,
                                     f"Approved: please expedite {b.po_number}. We accept the ${amount} rush fee.")
                terms["rush"] = {"form": form, "fee": str(amount), "approval": subject}
            else:
                if form == "declined":
                    docs.email(replied, f"Re: Expedite option for {b.po_number}", lib.BUYER_MAIL, docs.contact,
                               f"Thanks, but the standard delivery date works for us. Please ship {b.po_number} "
                               "as normal.")
                elif form == "other_po":
                    other = f"PO-{b.po_date.year}-{(number * 41) % 9000 + 1000}"
                    if other == b.po_number:
                        other = f"PO-{b.po_date.year}-{(number * 43) % 9000 + 1000}"
                    docs.email(replied, f"Expedite request for {other}", lib.BUYER_MAIL, docs.contact,
                               f"Approved: please expedite {other}. We accept the ${amount} rush fee on that order.")
                elif form == "phone":
                    docs.email(replied, f"Re: Expedite option for {b.po_number}", docs.contact, lib.BUYER_MAIL,
                               f"As agreed on the phone with your team today, we are expediting {b.po_number}. "
                               f"The ${amount} rush fee will appear on our invoice.")
                terms["rush"] = {"form": form, "fee": str(amount)}

        else:
            raise ValueError(f"unknown round 5 kind {kind}")

        po = b.po(po_lines)
        receipt = b.receipt(po_lines)
        invoice = b.invoice(billed + extra, notes=b.note(""))

    po["terms"] = (f"Pricing, freight and all other charges per Master Supply Agreement {msa}, as amended. "
                   f"Payment terms: {b.vendor['payment_terms'].replace('NET', 'Net ')}.")
    po["freight"] = {"billable": None, "cap": None}  # on the agreement, not the PO
    clauses, freight_id = docs.agreement(freight, _s(cap) if cap is not None else None)
    terms["freight"] = {"billable": freight == "capped", "cap": _s(cap) if cap is not None else None}
    for item, price, effective in changes:
        docs.price_amendment(item, _s(price), effective)
    billed_items = {l["description"] for l in invoice["line_items"]}
    off_invoice = [(name, _s(_money(rng.uniform(lo, hi)))) for name, lo, hi, _, _ in GOODS.get(b.trade, [])
                   if name not in billed_items]
    docs.distractions(off_invoice, msa_date, b.invoice_date)
    if rng.random() < 0.5:
        docs.delivery_email(po["po_number"], b.po_date + timedelta(days=rng.randint(1, 3)),
                            b.receipt_date - timedelta(days=b.receipt_date.weekday()))
    passages, ids = docs.documents()
    for item, price, effective in changes:
        change = f"from the effective date the unit price of \"{item}\" is ${_s(price)}."
        terms["price_changes"].append({"item": item, "price": _s(price), "effective": effective.isoformat(),
                                       "id": ids[change]})

    if kind.startswith("msa_freight"):
        deciding = [freight_id]
    # An amendment says its price applies "from the effective date"; the
    # agreement's pricing clause says that means invoices dated from then.
    elif kind in ("amended_price_in_effect", "amended_price_not_yet"):
        deciding = [terms["price_changes"][0]["id"], f"{b.vendor['id']}-msa-4"]
    elif kind in ("latest_amended_price", "superseded_price"):
        deciding = [max(terms["price_changes"], key=lambda c: c["effective"])["id"], f"{b.vendor['id']}-msa-4"]
    elif kind == "rush_fee_approved":
        deciding = [ids[terms["rush"]["approval"]], lib.RUSH]
    elif kind == "rush_fee_unapproved":
        deciding = [lib.RUSH]

    case.update(po=po, receipt=receipt, history=history, invoice=invoice, msa=msa, terms=terms,
                documents=clauses + passages, deciding=deciding)
    return case


def generate(seed: int, counts: Dict[str, int] = COUNTS, documents: bool = False) -> List[Dict]:
    """The full set, shuffled so case numbers say nothing about kinds. With
    `documents`, the PO's terms live in the vendor's documents (round 5)."""
    rng = random.Random(seed)
    kinds = [kind for kind, count in counts.items() for _ in range(count)]
    rng.shuffle(kinds)
    build = _build_with_documents if documents else _build
    return [build(rng, number, kind) for number, kind in enumerate(kinds, 1)]
