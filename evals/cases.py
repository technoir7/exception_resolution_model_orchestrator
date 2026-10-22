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
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Dict, List

AS_OF = date(2026, 10, 1)

# Kinds whose right answer is to pay; every other kind should be held.
PAY = {"clean", "partial_delivery", "freight_allowed", "tax_correct", "recurring_service", "unit_of_measure"}

# Kinds the rules and the three-way match flag. The rest pass them, so only a
# check that reads every invoice could catch the ones among them to hold.
FLAGGED = {
    "partial_delivery", "freight_allowed", "tax_correct", "recurring_service", "unit_of_measure",
    "price_increase", "overbilled_quantity", "duplicate", "freight_not_allowed", "tax_wrong",
    "vendor_mismatch",
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
    "freight_not_allowed": "freight the PO does not allow",
    "tax_wrong": "sales tax not at the PO's rate",
    "bank_change": "asks for payment to an account not on file",
    "vendor_mismatch": "billed by a vendor other than the PO's",
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

    else:
        raise ValueError(f"unknown kind {kind}")

    case.update(po=po, receipt=receipt, history=history, invoice=invoice)
    return case


def generate(seed: int) -> List[Dict]:
    """The full set, shuffled so case numbers say nothing about kinds."""
    rng = random.Random(seed)
    kinds = [kind for kind, count in COUNTS.items() for _ in range(count)]
    rng.shuffle(kinds)
    return [_build(rng, number, kind) for number, kind in enumerate(kinds, 1)]
