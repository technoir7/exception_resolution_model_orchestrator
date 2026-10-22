# What each way of processing invoices pays wrongly, and what it costs

This measures the README's claim: that letting a cheap model handle the
invoices the rules flag, with a stronger model checking it where a mistake
would be expensive, pays as few invoices wrongly as the strongest model alone,
sends far fewer to a person than the rules alone, and costs a fraction of the
strongest model's price.

Written before any model answered the measured cases.

## The cases

`evals/cases.py` builds 200 invoices (seed 1), each from one kind of
situation an accounts-payable team meets, with the documents a person would
check: the purchase order and its terms, the goods receipt, the vendor's record
with the bank account on file, the vendor's recent paid invoices, and the
invoice. The documents settle each answer, pay or hold; `evals/tests/test_cases.py`
checks that they do, and that the app's rules flag exactly the kinds meant to
be flagged.

| Kind | Right answer | Rules flag it | Cases |
|---|---|---|---:|
| clean | pay | no | 52 |
| partial delivery, billed as received | pay | yes | 14 |
| freight within the PO's cap | pay | yes | 14 |
| sales tax at the PO's rate | pay | yes | 14 |
| a new week of a weekly service | pay | yes | 12 |
| same goods in smaller units | pay | yes | 12 |
| unit price above the PO's fixed price | hold | yes | 12 |
| billed for more than was received | hold | yes | 12 |
| resubmitted duplicate, within a week | hold | yes | 10 |
| resubmitted duplicate, weeks later | hold | no | 8 |
| freight the PO does not allow | hold | yes | 12 |
| sales tax not at the PO's rate | hold | yes | 12 |
| payment asked to a new bank account | hold | no | 10 |
| billed by a vendor other than the PO's | hold | yes | 6 |

Exceptions are oversampled so that each kind has enough cases to say
something; results are reported per kind, so they can be reweighted to any
real mix. Each case has its own vendor, so no case's history can make another
look like a duplicate.

The cases are synthetic. What they test is reading documents against a
policy; how often each situation arises, and how messy real documents are, is
not tested.

## The answers

`evals/collect.py` sends every invoice, flagged or not, to each of Claude
Haiku, Sonnet and Opus (the `claude` command's `haiku`, `sonnet` and `opus`,
whose exact model is recorded with each answer), with the prompt the app
builds (`apps/api/services/review.py`). An answer that cannot be read is
retried once, as the app does, and both calls are counted. Cost is what the
`claude` command reports for each call at API list prices.

## The arms

`evals/score.py` decides each invoice under each arm, from the same answers:

- **rules only**: pay what the rules pass; send everything they flag to a person.
- **haiku / sonnet / opus on flagged**: pay what the rules pass; the model
  decides each flagged invoice; a hold (or an unreadable answer) goes to a person.
- **routed on flagged**: as above, but Haiku decides first, and Opus decides
  instead when Haiku says pay on an invoice of $5,000 or more or with
  confidence below 0.9 (`apps/api/services/routing.py`). A hold is never
  escalated, since it only sends the invoice to a person.
- **... on everything**: the same, with the model reading the invoices the
  rules pass too.

A person is assumed to decide correctly. The error that costs money is a
**wrong payment**: an invoice paid that should have been held. Sending a
payable invoice to a person is not an error but costs their time (a
**needless review**).

## Questions

1. How many wrong payments and needless reviews does each arm leave,
   against rules only?
2. Does routing pay no more invoices wrongly than Opus on flagged, at a
   fraction of its cost?
3. Does reading the invoices the rules pass catch the late duplicates and the
   bank changes, and what does reading them all cost?

## Checks on the answers' labels

Before scoring, one reviewer who has not seen any model's answers reads 40
cases drawn at random, each with only its prompt and its labelled answer, and
reports any whose documents do not settle that answer. A case found wrong is
reported and dropped from every arm.

## Pilot

Before this was written, 12 cases from another set (seed 0, `data/round0/`)
went to Haiku and Opus, only to check that answers could be read. All were.
Nothing was changed after it.

## Round 2

Round 1's answers were collected (`data/round1/`, cases built by the
generator as of commit f0c013c), and its label audit found all 40 labels
right. It also found ways a model could guess without reading the documents:
a quantity flag that appeared only on invoices to pay, invoice notes that
always pointed the right way ("Second notice" only on duplicates, "Partial
shipment" only on true partial deliveries), resubmitted duplicates always
renumbered and the only paid history with real-looking numbers, no freight
billed near its cap, and vendors whose names did not fit what they sold.

Round 2 changes only the cases, before round 1 was scored:

- a vendor's notes can mislead: a reminder or "Second notice" on invoices
  never paid (which should be paid), "Partial shipment" on some that bill more
  than arrived, and neutral notes on any kind;
- overbilling bills either the whole order or more than arrived but less than
  ordered, so it also shows the quantity-off-the-PO flag a partial delivery
  shows;
- a resubmitted invoice keeps its number as often as not;
- every vendor's paid history is numbered like its other invoices, against
  ordinary PO numbers;
- freight lands near its cap, just under (pay) or just over (hold);
- unit-of-measure lines are worded several ways; vendors sell what their
  names say.

On round 2's cases (seed 2), the "received" flag now appears on 12 invoices
to pay and 12 to hold, freight lines on 14 and 12, and "Partial shipment" on 3
and 3. The quantity-off-the-PO flag still leans to invoices to pay (38 against
5), which only misleads a model that pays on it.

Everything else is as round 1: the same prompt, models, arms, routing rule
and measures, and a fresh label audit of 40 random cases by a reviewer who has
not seen any answers. Round 2's results are the ones the project's README
reports; round 1's are reported here beside them.
