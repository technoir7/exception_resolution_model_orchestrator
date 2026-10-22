"""Round 4's invoices, printed as PDFs: everything the invoice says, and nothing else."""

import re
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from evals import cases, render

ROUND3 = cases.generate(seed=3, counts=cases.counts_for(3))


def shown(pdf: bytes) -> list:
    """The strings the PDF draws, in order."""
    text = pdf.decode("latin-1")
    raw = re.findall(r"\(((?:[^()\\]|\\.)*)\) Tj", text)
    return [re.sub(r"\\(.)", r"\1", s) for s in raw]


def first(kind):
    return next(c for c in ROUND3 if c["kind"] == kind)


class TestTheFile:
    def test_is_a_pdf_whose_index_points_at_its_objects(self):
        pdf = render.render(first("clean"))
        assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
        start = int(pdf.rsplit(b"startxref\n", 1)[1].split()[0])
        assert pdf[start:].startswith(b"xref")
        offsets = [int(line.split()[0]) for line in pdf[start:].split(b"\n")[3:] if line.endswith(b" n ")]
        for number, offset in enumerate(offsets, 1):
            assert pdf[offset:].startswith(f"{number} 0 obj".encode())

    def test_is_the_same_every_time(self):
        assert render.render(first("clean")) == render.render(first("clean"))


class TestTheLayouts:
    def test_all_three_are_used_about_equally(self):
        counts = Counter(render.layout_for(c) for c in ROUND3)
        assert set(counts) == set(render.STYLES)
        assert min(counts.values()) >= 50

    def test_a_vendor_always_gets_the_same_one(self):
        case = first("clean")
        assert render.layout_for(case) == render.layout_for({**case, "id": "other"})

    def test_differ_in_how_dates_and_money_are_written(self):
        on, amount = date(2026, 2, 20), Decimal("1430.62")
        written = {(render.STYLES[s].date(on), render.STYLES[s].money(amount)) for s in render.STYLES}
        assert written == {("February 20, 2026", "$1,430.62"), ("02/20/2026", "1,430.62"), ("20-Feb-2026", "1430.62")}


@pytest.mark.parametrize("case", ROUND3, ids=lambda c: c["id"])
def test_prints_everything_the_invoice_says(case):
    inv, style = case["invoice"], render.STYLES[render.layout_for(case)]
    strings = shown(render.render(case))
    text = " ".join(strings)
    vendor = render.issuer(case)
    expected = [inv["invoice_number"], inv["po_number"], vendor["name"], vendor["tax_id"],
                style.date(date.fromisoformat(inv["invoice_date"])), style.date(date.fromisoformat(inv["due_date"])),
                style.money(Decimal(inv["subtotal"])), style.money(Decimal(inv["tax_amount"])),
                inv["remit_to"]["bank"], inv["remit_to"]["account_last4"]]
    for line in inv["line_items"]:
        expected += [line["description"], str(line["quantity"]), style.money(Decimal(line["unit_price"])),
                     style.money(Decimal(line["amount"]))]
    for value in expected:
        assert any(value in s for s in strings), value
    assert style.money(Decimal(inv["total_amount"])) in text
    if inv["notes"]:
        assert inv["notes"] in text


def test_never_prints_the_answer():
    for case in ROUND3[:40]:
        text = " ".join(shown(render.render(case)))
        assert case["kind"] not in text and case["truth"]["reason"] not in text and "is_freight" not in text


def test_refuses_an_invoice_with_something_it_would_not_print():
    case = first("clean")
    with pytest.raises(ValueError, match="service_period"):
        render.render({**case, "invoice": {**case["invoice"], "service_period": "2026-04-01"}})
