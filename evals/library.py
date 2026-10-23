"""The documents a PO's terms refer to, for round 5: each vendor's master
supply agreement, its amendments and its emails, and the buyer's AP policy
manual.

Most of it is the boilerplate real agreements and manuals carry, and decides
nothing. The few passages that decide an invoice are generated from the case,
and their ids are recorded (`deciding`), so retrieval can be scored on its
own. Every passage is a dict with the fields of
`apps.api.services.retrieval.Passage`.
"""

import random
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

BUYER = "Calder Works"
BUYER_MAIL = "purchasing@calderworks.com"

# (number, heading, text). {buyer}, {vendor} and the rest are filled per vendor.
AGREEMENT = [
    (1, "Definitions", "In this Agreement, \"Buyer\" means {buyer}, \"Supplier\" means {vendor}, \"Goods\" means "
        "the products Supplier sells to Buyer, and \"Purchase Order\" means Buyer's written order for Goods "
        "referring to this Agreement."),
    (2, "Term", "This Agreement begins on the Effective Date and continues for {years} years. It then renews "
        "for successive one-year terms unless either party gives at least {notice} days' written notice "
        "before the end of a term."),
    (3, "Orders", "Buyer will order Goods by Purchase Order. Each Purchase Order incorporates this Agreement. "
        "Supplier shall confirm each Purchase Order within {confirm} business days. Terms on Supplier's "
        "quotations, acknowledgements or invoices that conflict with this Agreement do not apply."),
    (4, "Pricing", "Prices are those stated in the Purchase Order and are firm for the life of each Purchase "
        "Order. A price may change only by a written amendment to this Agreement signed by both parties. A "
        "changed price applies to all Goods invoiced on or after the amendment's effective date, including "
        "Goods on open Purchase Orders, and to no Goods invoiced before it."),
    (5, "Delivery", "Supplier shall deliver Goods to the location on the Purchase Order by the date it states. "
        "Partial deliveries are permitted; Supplier shall invoice only Goods actually delivered. Title and "
        "risk of loss pass to Buyer on delivery."),
    # 6 (Freight) and 7 (Taxes) are written per vendor; see `_freight` and TAXES.
    (8, "Invoicing", "Supplier shall invoice each shipment separately, quoting the Purchase Order number, and "
        "send invoices to accounts payable at {buyer}. Each invoice shall list the Goods delivered, their "
        "quantities and unit prices, and any charge this Agreement allows."),
    (9, "Payment", "Buyer will pay each undisputed invoice within {terms} days of receiving it. Buyer may "
        "withhold payment of any amount it disputes in good faith, and shall tell Supplier which amount and "
        "why."),
    (10, "Inspection and acceptance", "Buyer may inspect Goods within {inspect} days of delivery and reject "
         "any that do not conform. Payment is not acceptance. Supplier shall collect rejected Goods at its "
         "own cost."),
    (11, "Warranty", "Supplier warrants that Goods will conform to their specifications and be free from "
         "defects in materials and workmanship for {warranty} months from delivery."),
    (12, "Returns", "Buyer may return non-conforming Goods for credit or replacement, at Buyer's choice. "
         "Supplier shall issue a credit memo within {credit} days of receiving returned Goods."),
    (13, "Insurance", "Supplier shall maintain commercial general liability insurance of at least "
         "${liability} per occurrence and shall provide a certificate of insurance on request."),
    (14, "Indemnity", "Supplier shall defend and indemnify Buyer against third-party claims arising from "
         "defective Goods or from Supplier's negligence or breach of this Agreement."),
    (15, "Limitation of liability", "Neither party is liable for indirect or consequential damages. This "
         "limit does not apply to Supplier's indemnity obligations or to breach of confidentiality."),
    (16, "Confidentiality", "Each party shall keep the other's confidential information confidential and use "
         "it only to perform this Agreement, for {secrecy} years after it ends."),
    (17, "Compliance", "Supplier shall comply with all laws applicable to the Goods and their delivery, "
         "including laws on product safety, labelling and export control."),
    (18, "Audit", "Buyer may audit Supplier's records of charges invoiced under this Agreement, on {audit} "
         "days' notice, for {audit_years} years after each invoice."),
    (19, "Force majeure", "Neither party is liable for delay caused by events beyond its reasonable control. "
         "A party so delayed shall notify the other promptly and resume performance as soon as it can."),
    (20, "Termination", "Either party may terminate this Agreement on {notice} days' written notice. "
         "Termination does not affect Purchase Orders already issued unless Buyer cancels them."),
    (21, "Assignment", "Supplier may not assign this Agreement or subcontract its obligations without "
         "Buyer's written consent."),
    (22, "Notices", "Notices under this Agreement shall be in writing and sent to {notice_contact} for "
         "Supplier and to {buyer}, Attn: Purchasing, for Buyer."),
    (23, "Governing law", "This Agreement is governed by the laws of the State of {state}."),
    (24, "Entire agreement", "This Agreement, its amendments and each Purchase Order are the entire "
         "agreement between the parties about the Goods. They may be changed only in a writing signed by "
         "both parties."),
]
FREIGHT_INCLUDED = ("All prices are delivered prices (FOB destination). Supplier bears all freight, "
                    "shipping and handling costs and shall not invoice them.")
FREIGHT_CAPPED = ("Freight may be invoiced as a separate line at Supplier's actual cost, not to exceed ${cap} "
                  "per shipment. Freight above that amount is at Supplier's cost.")
TAXES = ("Buyer purchases Goods for resale and has given Supplier a resale certificate. Supplier shall not "
         "invoice sales or use tax.")
STATES = ["California", "Delaware", "Illinois", "Ohio", "Texas", "Washington"]

# The buyer's AP policy manual: (section, heading, text). One section decides
# invoices (`RUSH`); a few restate rules the agreements set; most decide nothing.
MANUAL = [
    ("1.1", "Purpose", "This manual sets out how Calder Works receives, checks, approves and pays supplier "
            "invoices. It applies to all business units."),
    ("1.2", "Who it applies to", "Everyone who orders goods or services, approves invoices or pays suppliers "
            "on behalf of Calder Works."),
    ("2.1", "Receiving invoices", "Suppliers send invoices to accounts payable by email or post. Invoices "
            "sent to anyone else are forwarded to accounts payable the same day."),
    ("2.2", "What an invoice must show", "An invoice must show the supplier's name, an invoice number and "
            "date, the PO number, the goods or services, quantities, unit prices and total."),
    ("2.3", "Invoices without a PO", "An invoice with no PO is returned to the requester to raise one, "
            "unless it is for a utility or a recurring contract listed in schedule B."),
    ("3.1", "Three-way match", "Before payment, each invoice is matched to its PO and to the goods receipt. "
            "Goods are paid only as received."),
    ("3.2", "Prices", "Invoices are paid at the PO's prices, or at a price set by an amendment to the "
            "supplier's agreement, from that amendment's effective date."),
    ("3.3", "Freight", "Freight is paid only as the supplier's agreement or the PO allows."),
    ("3.4", "Sales tax", "Calder Works buys goods for resale and does not pay sales tax on them unless the "
            "PO states that tax applies."),
    ("4.1", "Approval limits", "Invoices matched to a PO need no further approval. Invoices without a PO "
            "need approval by a budget holder: up to $5,000 by a manager, above that by a director."),
    ("4.2", "Segregation of duties", "No one may approve an invoice for a PO they raised, or pay an invoice "
            "they approved."),
    ("5.1", "Duplicate invoices", "Accounts payable checks each invoice against the supplier's recent "
            "invoices. A second invoice for the same goods is not paid."),
    ("5.2", "Credit memos", "Credit memos are applied to the supplier's next payment, or refunded if no "
            "payment is due within 60 days."),
    ("6.1", "New suppliers", "A new supplier is set up only after Purchasing approves it and the supplier "
            "provides a W-9 and bank details on letterhead."),
    ("6.2", "Changes to bank details", "A change to a supplier's bank details is made only after accounts "
            "payable confirms it by calling the supplier on the number already on file. A request on an "
            "invoice or by email alone is not enough."),
    ("6.3", "Supplier records", "Supplier records are reviewed each year; suppliers with no activity for "
            "two years are deactivated."),
    ("7.1", "Payment runs", "Payments are made in weekly runs on Thursdays. Urgent payments outside a run "
            "need approval by the controller."),
    ("7.2", "Payment terms", "Invoices are paid on the supplier's agreed terms, counted from the date the "
            "invoice is received."),
    ("7.3", "Early payment discounts", "Where a supplier offers a discount for early payment, accounts "
            "payable takes it if the invoice can be approved in time."),
    ("7.4", "Expedite and rush fees", "Rush, expedite and priority-handling fees are payable only if "
            "Purchasing approved the fee in writing, for that PO, before the goods shipped. Approval by phone "
            "is not enough. An invoice with such a fee and no written approval is held."),
    ("8.1", "Employee expenses", "Employee expenses are claimed through the expense system within 30 days, "
            "with receipts for any item over $25."),
    ("8.2", "Travel", "Air travel is booked through the travel desk in economy class. Hotel stays follow the "
            "nightly limits in schedule C."),
    ("8.3", "Purchasing cards", "Purchasing cards may be used for purchases up to $2,500 that need no PO. "
            "Cardholders reconcile their statements monthly."),
    ("9.1", "Month-end", "Accounts payable accrues goods received but not yet invoiced at each month-end, "
            "from the receipts on open POs."),
    ("9.2", "1099 reporting", "Payments to suppliers who need a 1099 are tracked from their W-9 and reported "
            "each January."),
    ("9.3", "Record retention", "Invoices, receipts and approvals are kept for seven years."),
    ("10.1", "Disputes", "An invoice that cannot be paid as billed is held, and the supplier is told which "
             "amount is disputed and why, within five business days."),
    ("10.2", "Exceptions", "Any exception to this manual needs the controller's written approval."),
]
RUSH = "policy-7.4"

ROUTINE_EMAILS = [
    ("Delivery window for {po}", "{vendor_contact}", BUYER_MAIL,
     "We expect to deliver {po} during the week of {week}. Please let us know if your receiving hours "
     "have changed."),
    ("Holiday closure", "{vendor_contact}", BUYER_MAIL,
     "Our warehouse will be closed for the holidays from December 24 to January 1. Orders placed in that "
     "week will ship on January 2."),
    ("Updated W-9", "{vendor_contact}", BUYER_MAIL,
     "Attached is our updated W-9 for your records. Nothing else about our account has changed."),
    ("New account manager", "{vendor_contact}", BUYER_MAIL,
     "{rep} is now your account manager and can be reached at this address for orders and quotes."),
    ("Price list for next year", "{vendor_contact}", BUYER_MAIL,
     "Our list prices for next year are attached for planning. Your contract prices do not change unless "
     "we agree an amendment."),
    ("Receiving hours", BUYER_MAIL, "{vendor_contact}",
     "Our dock now receives deliveries from 7 a.m. to 3 p.m., Monday to Friday."),
]
REPS = ["Dana Ortiz", "Sam Whitfield", "Priya Nair", "Leo Brandt", "Mia Castellano", "Owen Pryce"]


def _iso(d: date) -> str:
    return d.isoformat()


def manual() -> List[Dict]:
    return [{"id": f"policy-{n}", "source": "policy", "title": f"AP Policy Manual {n}, {heading}",
             "text": text, "vendor_id": None, "dated": None} for n, heading, text in MANUAL]


def msa_number(vendor: Dict, rng: random.Random) -> str:
    return f"MSA-{rng.randint(2023, 2025)}-{vendor['id'][1:]}"


class Library:
    """One vendor's documents, built up for a case."""

    def __init__(self, rng: random.Random, vendor: Dict, msa: str, msa_date: date, as_of: date):
        self.rng, self.vendor, self.msa, self.msa_date, self.as_of = rng, vendor, msa, msa_date, as_of
        self.contact = "ar@" + "".join(w for w in vendor["name"].lower().split()[:2] if w.isalpha()) + ".com"
        self.amendments: List[Tuple[date, str, str]] = []  # (effective, section, change)
        self.emails: List[Tuple[date, str, str, str, str]] = []  # (on, subject, sender, to, body)

    def _id(self, kind: str, n) -> str:
        return f"{self.vendor['id']}-{kind}-{n}"

    def agreement(self, freight: str, cap=None) -> Tuple[List[Dict], str]:
        """The agreement's clauses, and the id of its freight clause."""
        rng = self.rng
        values = {"buyer": BUYER, "vendor": self.vendor["name"], "years": rng.choice([2, 3, 5]),
                  "notice": rng.choice([30, 60, 90]), "confirm": rng.choice([2, 3, 5]),
                  "terms": self.vendor["payment_terms"][3:], "inspect": rng.choice([10, 14, 30]),
                  "warranty": rng.choice([12, 18, 24]), "credit": rng.choice([10, 15, 30]),
                  "liability": f"{rng.choice([1, 2, 5])},000,000", "secrecy": rng.choice([2, 3, 5]),
                  "audit": rng.choice([10, 15, 30]), "audit_years": rng.choice([3, 5]),
                  "notice_contact": f"{self.vendor['name']}, Attn: Contracts", "state": rng.choice(STATES)}
        clauses = [(n, h, t.format(**values)) for n, h, t in AGREEMENT]
        freight_text = FREIGHT_INCLUDED if freight == "included" else FREIGHT_CAPPED.replace("{cap}", str(cap))
        clauses += [(6, "Freight", freight_text), (7, "Taxes", TAXES)]
        clauses.sort()
        return [{"id": self._id("msa", n), "source": "agreement",
                 "title": f"Master Supply Agreement {self.msa} (effective {_iso(self.msa_date)}) section {n}, "
                          f"{heading}",
                 "text": text, "vendor_id": self.vendor["id"], "dated": None}
                for n, heading, text in clauses], self._id("msa", 6)

    def price_amendment(self, item: str, price, effective: date) -> date:
        self.amendments.append((effective, "4 (Pricing)",
                                f"from the effective date the unit price of \"{item}\" is ${price}."))
        return effective

    def distractions(self, items_off_invoice: Sequence[Tuple[str, str]], earliest: date, latest: date) -> None:
        """Amendments and emails that bear on nothing the invoice bills."""
        rng = self.rng
        for _ in range(rng.choice([0, 1, 1, 2])):
            on = earliest + timedelta(days=rng.randint(0, max(0, (latest - earliest).days)))
            choice = rng.random()
            if choice < 0.35 and items_off_invoice:
                item, price = rng.choice(list(items_off_invoice))
                self.amendments.append((on, "4 (Pricing)",
                                        f"from the effective date the unit price of \"{item}\" is ${price}."))
            elif choice < 0.6:
                self.amendments.append((on, "13 (Insurance)", "the per-occurrence limit is raised to "
                                        f"${rng.choice([3, 5, 10])},000,000."))
            elif choice < 0.8:
                self.amendments.append((on, "2 (Term)", f"the initial term is extended by {rng.choice([1, 2])} "
                                        "years."))
            else:
                self.amendments.append((on, "22 (Notices)", "notices to Supplier shall be sent to "
                                        f"{self.contact}."))
        values = {"po": "", "week": "", "vendor_contact": self.contact, "rep": rng.choice(REPS)}
        for subject, sender, to, body in rng.sample(ROUTINE_EMAILS, rng.randint(2, 4)):
            on = earliest + timedelta(days=rng.randint(0, max(0, (latest - earliest).days)))
            if "{po}" in subject:
                continue  # delivery emails are added per PO by `delivery_email`
            self.emails.append((on, subject, sender.format(**values), to.format(**values), body.format(**values)))

    def delivery_email(self, po: str, on: date, week: date) -> None:
        self.emails.append((on, f"Delivery window for {po}", self.contact, BUYER_MAIL,
                            f"We expect to deliver {po} during the week of {_iso(week)}. Please let us know if "
                            "your receiving hours have changed."))

    def email(self, on: date, subject: str, sender: str, to: str, body: str) -> str:
        self.emails.append((on, subject, sender, to, body))
        return subject

    def documents(self) -> Tuple[List[Dict], Dict[str, str]]:
        """Every passage, and the id each amendment and email was given, by
        its text (amendments) or subject (emails)."""
        ids: Dict[str, str] = {}
        out = []
        for n, (effective, section, change) in enumerate(sorted(self.amendments, key=lambda a: a[0]), 1):
            pid = self._id("amendment", n)
            ids[change] = pid
            out.append({"id": pid, "source": "amendment",
                        "title": f"Amendment No. {n} to Master Supply Agreement {self.msa}, effective "
                                 f"{_iso(effective)}",
                        "text": f"Section {section} is amended: {change} All other terms are unchanged.",
                        "vendor_id": self.vendor["id"], "dated": _iso(effective)})
        for n, (on, subject, sender, to, body) in enumerate(sorted(self.emails, key=lambda e: e[0]), 1):
            pid = self._id("email", n)
            ids[subject] = pid
            out.append({"id": pid, "source": "email", "title": f"Email {_iso(on)} from {sender} to {to}: {subject}",
                        "text": body, "vendor_id": self.vendor["id"], "dated": _iso(on)})
        return out, ids
