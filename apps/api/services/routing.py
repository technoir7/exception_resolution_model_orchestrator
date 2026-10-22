"""
Which model's verdict decides an invoice, when a second opinion is on
(REVIEW_SECOND_OPINION; off by default, since in the benchmark it never
changed the cheap model's decision).

A hold always stands:
it only sends the invoice to a person, and a second model could only turn it
into a payment. A pay is checked by the strongest model when a mistake would
be expensive or the cheap model is unsure, since a wrong payment is the error
that costs money.
"""

from decimal import Decimal

from apps.api.services.review import Verdict

FIRST = "haiku"
SECOND = "opus"

# A wrong payment above this costs more than any number of model calls.
LARGE = Decimal("5000")
# Below this, the cheap model's own confidence is not trusted.
SURE = 0.9


def needs_second_opinion(first: Verdict, amount: Decimal) -> bool:
    return first.decision == "pay" and (amount >= LARGE or first.confidence < SURE)
