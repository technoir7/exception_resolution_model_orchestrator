"""When a cheap model's verdict is trusted, and when a stronger one is asked."""

from decimal import Decimal

from apps.api.services import routing
from apps.api.services.review import Verdict


def verdict(decision, confidence=0.95):
    return Verdict(decision, "none", confidence, "")


def test_a_hold_is_never_escalated():
    """A hold sends the invoice to a person, who costs more than any model:
    asking a second model could only turn it into a payment."""
    assert not routing.needs_second_opinion(verdict("hold", 0.2), Decimal("50000"))


def test_a_confident_pay_on_a_small_invoice_stands():
    assert not routing.needs_second_opinion(verdict("pay", 0.95), Decimal("1200"))


def test_a_pay_on_a_large_invoice_is_checked():
    assert routing.needs_second_opinion(verdict("pay", 0.99), routing.LARGE)


def test_an_unsure_pay_is_checked():
    assert routing.needs_second_opinion(verdict("pay", routing.SURE - 0.01), Decimal("100"))
