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

## Results

Both rounds' label audits agreed with every label checked (40 random cases
in round 1; 40 random and 19 chosen in round 2), so no case was dropped.

Round 2 (seed 2), 200 invoices, of which 82 should be held:

| Arm | Wrong payments | Paid wrongly | To a person | Needless reviews | Model cost per invoice |
|---|---:|---:|---:|---:|---:|
| rules only | 18 | $56,604.90 | 130 | 66 | $0 |
| haiku on flagged | 18 | $56,604.90 | 64 | 0 | $0.00038 |
| sonnet on flagged | 18 | $56,604.90 | 64 | 0 | $0.00588 |
| opus on flagged | 18 | $56,604.90 | 64 | 0 | $0.01186 |
| routed on flagged | 18 | $56,604.90 | 64 | 0 | $0.00162 |
| haiku on everything | 0 | $0 | 82 | 0 | $0.00058 |
| sonnet on everything | 0 | $0 | 82 | 0 | $0.00888 |
| opus on everything | 0 | $0 | 82 | 0 | $0.01807 |
| routed on everything | 0 | $0 | 82 | 0 | $0.00343 |

Every model decided every invoice it read correctly, and gave the right
reason for all 82 holds. One answer in 600 needed a retry. Each took about 4
seconds an invoice.

1. Against rules only, a model on the flagged invoices cleared all 66
   needless reviews; the 18 wrong payments left are the late duplicates and
   bank changes the rules pass, which it never read. Reading every invoice
   caught all 18, and sent to a person exactly the 82 that should be held.
2. Routing paid no more wrongly than Opus, at 14% of its cost on the flagged
   invoices and 19% on all of them. But Opus never changed Haiku's decision,
   so Haiku alone did as well for a quarter to a sixth of routing's cost.
3. Reading the invoices the rules pass caught every late duplicate and bank
   change, for $0.00058 an invoice with Haiku.

Round 1 (seed 1, the cases with shortcuts) came out the same, except that
Haiku and Sonnet each sent one payable invoice to a person (freight under
its cap): 0 wrong payments for every model on everything, 18 for every model
on flagged, against 18 and 66 needless reviews for rules only.

**What this does not show.** These cases are at the ceiling for all three
models, so they cannot rank them, or show where the cheaper model starts to
fail. The documents are clean structured data, each hold has one problem,
and round 2's audit still found clues a model could use (vendor notes such as
"Copy of invoice" only on duplicates; renumbered invoices, when suffixed,
only on duplicates). Real invoices, read from PDFs, with several issues at
once, would be harder. What the cases do show is that the choice of what the
model reads matters far more here than which model reads it, and that the
cheapest model is enough for documents like these.

The app follows these results: by default Haiku reads every invoice, and the
second opinion from Opus is an option (`REVIEW_SECOND_OPINION`), off.

## Round 3

Rounds 1 and 2 were at the ceiling: every model decided every invoice it read
correctly, so they could not show where a cheaper model fails. Round 3 is
built to be harder, written before any model answered it.

Changed in the app, both found while building the cases: a PO delivered in
two shipments has two receipts, which made the matching engine crash; it now
counts what all of them brought, and the review sees each. And the vendor
record can say when its bank account last changed and from what, which the
review is shown. The policy and the rest of the prompt are unchanged.

The cases (seed 3), 200 invoices, 80 to hold:

| Kind | Right answer | Rules flag it | Cases |
|---|---|---|---:|
| clean | pay | no | 63 |
| the PO's lines in other words (part numbers, abbreviations) and another order | pay | yes | 15 |
| freight exactly at the PO's cap | pay | yes | 10 |
| the second of two shipments the PO asked for, both received | pay | yes | 12 |
| payment to the account the vendor record was updated to | pay | no | 10 |
| a partial delivery billed as received, with tax at the PO's rate | pay | yes | 10 |
| a line's amount more than its quantity times its price, by under 1% of the total | hold | no | 12 |
| one unit more than was received | hold | no | 12 |
| a unit price under 1% above the PO's | hold | no | 12 |
| a partial delivery with freight above the cap | hold | yes | 10 |
| payment to a new account, said on the invoice to be agreed by phone | hold | no | 10 |
| a paid invoice resubmitted weeks later, reworded | hold | no | 12 |
| the second shipment billed, but not received | hold | yes | 12 |

Three kinds are hidden errors the rules cannot see (the arithmetic, the one
unit, the small price rise); the rest come in look-alike pairs whose
documents differ in one detail (a bank change on the vendor record or only on
the invoice; a second shipment received or not; freight at its cap or over
it). 58 of the 80 invoices to hold pass the rules.

The arms, measures and routing rule are as in rounds 1 and 2. Questions:

1. Does each model still decide every invoice it reads correctly? If not,
   which kinds does each get wrong?
2. Where the models differ, does routing (Opus checking Haiku's pays of
   $5,000 or more, or below 0.9 confidence) pay no more invoices wrongly than
   Opus, at a fraction of its cost?
3. How many wrong payments does reading only the flagged invoices leave, now
   that most holds pass the rules?

The labels are audited as before: 40 cases at random, and every case of the
three hidden-error kinds, by a reviewer who has not seen any answers. A case
whose documents do not settle its label is reported and dropped.

Regenerating round 2's cases with the generator as it now stands gives the
same cases, except that the stated reason for disallowed freight now also
mentions the cap; decisions are unchanged.

### Round 3 results

The label audit agreed with all 65 labels it checked (40 random, and all 25
cases of the three hidden-error kinds), so no case was dropped. It noted that
the smallest errors are tiny (one extra hex bolt, $0.45) and that the policy,
which has no tolerance, makes them holds.

| Arm | Wrong payments | Paid wrongly | To a person | Needless reviews | Model cost per invoice |
|---|---:|---:|---:|---:|---:|
| rules only | 58 | $162,302.63 | 69 | 47 | $0 |
| haiku on flagged | 58 | $162,302.63 | 23 | 1 | $0.00024 |
| sonnet on flagged | 58 | $162,302.63 | 22 | 0 | $0.00360 |
| opus on flagged | 58 | $162,302.63 | 22 | 0 | $0.00694 |
| routed on flagged | 58 | $162,302.63 | 23 | 1 | $0.00180 |
| haiku on everything | 0 | $0 | 82 | 2 | $0.00062 |
| sonnet on everything | 0 | $0 | 80 | 0 | $0.00929 |
| opus on everything | 0 | $0 | 80 | 0 | $0.01878 |
| routed on everything | 0 | $0 | 82 | 2 | $0.00439 |

1. Every model caught every invoice to hold, the hidden errors included, and
   gave a sensible reason for each. The first difference between models: Haiku
   held two invoices that should have been paid. One was the second of two
   shipments, both received, which it took for a duplicate of the first, at
   0.95 confidence. The other was a clean invoice billing the same item and
   quantity as an unrelated earlier invoice on another PO, a coincidence of
   the generated history, which it sent to a person at 0.6 confidence. Sonnet
   and Opus made no mistake.
2. Routing escalates only pays, so it could not fix Haiku's two holds; it
   cost seven times Haiku alone for the same decisions. (Escalating holds
   below 0.9 confidence would have sent the second to Opus; that rule was not
   planned and is not measured here.)
3. Reading only the flagged invoices left 58 wrong payments, $162,302.63:
   most invoices to hold now pass the rules.

So on the harder cases the cheapest model still paid nothing wrongly, at the
cost of 2 needless reviews in 120 payable invoices, against none for models
15 to 30 times its price.

## Round 4: invoices read from PDFs

Rounds 1 to 3 gave the app each invoice as data. Real invoices arrive as
PDFs, so the app now has a reader (`apps/api/services/extraction.py`,
`intake.py`): Haiku is given the PDF itself, with no tools, and told to copy
it exactly as printed and to correct nothing, so that a line that does not add
up reaches the review as printed. The vendor is matched on file by the tax ID
printed (by name only when none is printed); an invoice whose vendor cannot be
matched, or that cannot be read in two tries, is refused at intake and goes to
a person. Round 4 measures what reading costs in wrong payments, needless
reviews and money. Written before any model has read a round 4 PDF.

The cases are round 3's 200 (seed 3), with the same right answers, which the
round 3 audit already checked. Only the invoice changes form: each is printed
as a one-page PDF (`evals/render.py`) in one of three layouts, one per vendor,
that write dates three ways (February 20, 2026; 02/20/2026; 20-Feb-2026),
money with or without a dollar sign and thousands separators, columns in
different orders under different names, and the bank account as "ending
3572", "****3572" or "xxxx3572". Everything the invoice says is printed, and
nothing else. The vendor record, PO, receipts and history are the same
records as in round 3.

The recorded readings are replayed through the app's own intake, then the
rules and the review run as in round 3. A test checks that an invoice read
perfectly gives exactly round 3's prompt, so any difference from round 3 comes
from reading. The arm measured is Haiku reading every PDF and Haiku reviewing
every invoice, round 3's cheapest arm with no wrong payments; rules only and
Haiku on flagged invoices are scored from the same answers. Cost per invoice
now includes reading.

A pilot of 7 PDFs from another case set (seed 100), across all three layouts
and including a line that does not add up, was read exactly, at about $0.001
a PDF; the reader's instruction was not changed after it.

Questions:

1. How many invoices are read exactly as printed, and which fields are read
   wrong? Formatting is not an error (1430.6 for 1430.60, spacing).
2. Does reading let any invoice be paid wrongly? Round 3's arm paid none. The
   risk is a reader that tidies the invoice: computes a line's amount instead
   of copying it, or reads a resubmitted invoice's reworded lines as the
   PO's wording.
3. How many payable invoices go to a person? Round 3's arm sent 2. A misread
   field can send more.
4. What does an invoice cost to read and review, against round 3's $0.00062?

A wrong payment caused by reading is reported as such, with the field
misread. The reader's instruction is not changed in response to round 4; a
change would be measured on a new round with new cases.

Not tested: scanned or photographed invoices, multi-page invoices, and
invoices from vendors not on file.

### Round 4 results

**As run, a bug of mine refused 35 invoices.** The terse layout prints no
currency, and the reader rightly answered null, as told to for anything not
printed; the app's parser required a currency, so it treated the reply as
unreadable, asked again, and refused the 35 of those 50 invoices that got
null both times. Every reading that parsed was exact. Those 35 would have gone
to a person (106 in all, 26 of them payable) with no wrong payment. The
round as run is kept in `results-as-run.json` and `prompts-as-run.jsonl`.

The fix is in the app, not the reader's instruction: an invoice that prints no
currency is taken to be in the buyer's own, as many domestic invoices are. The
recorded readings were replayed through the fixed intake, with no new reading
calls. 164 of the 165 prompts already reviewed came out the same; the other
(c140) now used the reader's first reply rather than its second, which
differed only in writing the tax as 0.0 rather than 0, and was reviewed again.
The 35 newly accepted invoices were reviewed for the first time.

| Arm | Wrong payments | Paid wrongly | To a person | Needless reviews | Model cost per invoice |
|---|---:|---:|---:|---:|---:|
| rules only | 58 | $162,302.63 | 69 | 47 | $0.00111 |
| haiku on flagged | 58 | $162,302.63 | 25 | 3 | $0.00135 |
| haiku on everything | 0 | $0 | 84 | 4 | $0.00173 |

Cost per invoice now includes reading the PDF, about $0.0011 as recorded and
$0.0010 without the retries the bug caused.

1. **All 200 invoices were read exactly as printed**: every field, on every
   layout. The 12 lines that do not add up were copied as printed, not
   corrected, and the 12 reworded resubmissions kept their wording.
2. **Reading let no invoice be paid wrongly.** Haiku reviewing every invoice
   held all 80 that should be held, as in round 3.
3. **Payable invoices sent to a person: 4, against round 3's 2**, and not the
   same ones: c015 (freight at its cap, which Haiku read as possibly not "at
   actual cost"), c165 (a weak duplicate suspicion, at 0.6 confidence), and
   c104 and c107 (each the second of two shipments, taken for a duplicate).
   Round 3's c105 was paid this time. The invoices as read differ from
   round 3's only in how numbers are written: the reader gives 1552.4 where
   the data said 1552.40. To tell that from chance, Haiku was asked again
   three times on each of these five invoices, with round 3's prompt and with
   round 4's (`repeats-haiku.json`): it held 4 of 15 times with round 3's and
   5 of 15 with round 4's, flipping on the same invoices with either. So the
   difference is Haiku's run-to-run variation on borderline payable invoices,
   not reading. It is also a measure of that variation: any single run's count
   of needless reviews could be a couple higher or lower.
4. **Reading and reviewing cost $0.00173 an invoice**, about $1.70 per thousand
   (reading $1.10, the review $0.62). A PDF is about 2,900 tokens to the reader,
   and a reading took about 5 seconds.

So for clean, generated PDFs, reading is not where invoices go wrong; the
review's judgement on borderline payable invoices is. Scans, photographs and
multi-page invoices would test the reader harder.

## Round 5: terms that live outside the PO

In rounds 1 to 4 every term that decides an invoice is printed on the PO:
the freight cap, the tax rate, whether prices are fixed. In practice most of
them live elsewhere. A PO says "per the Master Supply Agreement", and the
agreement, its amendments, the AP policy manual and emails agreeing
exceptions say what may be billed. Round 5 moves the deciding terms into
that library of documents and asks whether the review needs retrieval (RAG)
to use them, or whether giving it all of a vendor's documents does as well.
Written before any model answered round 5's cases.

Changed in the app: a case file can carry the vendor's documents
(`case_file.py`), and the review shows them after the PO with one more
paragraph of policy: an amendment applies from its effective date and
overrides the agreement and earlier amendments, and what was agreed in
writing by email counts (`review.py`, `DOCUMENTS_POLICY`). Without documents
the prompt is exactly as before. Retrieval is `apps/api/services/retrieval.py`:
keyword ranking (BM25), ranking by embedding, and the two fused (reciprocal
rank fusion). The app does not yet store vendors' documents; this round
measures whether it should look them up, and how.

### The library

Generated with the cases (`evals/library.py`), with the right answers fixed:

- **A master supply agreement per vendor**: 24 clauses, most of them the
  boilerplate real agreements carry (confidentiality, insurance, indemnity).
  Clause 4 says a changed price applies to goods invoiced on or after an
  amendment's effective date; clause 6 sets freight (prices delivered, or
  freight at cost up to a cap); clause 7 rules out sales tax.
- **Amendments, 0 to 4 per vendor**: each dated, each changing one clause;
  most change nothing an invoice bills (insurance limits, notices, the term,
  the price of something else).
- **Emails, 1 to 7 per vendor**: delivery windows, holiday closures, a new
  account manager, and the expedite offers and replies the rush-fee cases
  turn on.
- **One AP policy manual** for the buyer, 28 sections, of which one decides
  invoices: rush fees are payable only with Purchasing's written approval,
  for that PO, before shipment.

A vendor's documents with the manual come to about 1,800 words. The PO says
only "Pricing, freight and all other charges per Master Supply Agreement
MSA-..., as amended".

### The cases

200 invoices (seed 5), 90 to hold, 45 of which the rules pass:

| Kind | Right answer | Rules flag it | Decided by | Cases |
|---|---|---|---|---:|
| clean | pay | no | nothing at issue | 50 |
| freight within the agreement's cap (the PO is silent) | pay | yes | agreement, clause 6 | 15 |
| freight where the agreement says prices are delivered | hold | yes | agreement, clause 6 | 15 |
| a price rise in an amendment in effect on the invoice date | pay | yes | amendment, clause 4 | 15 |
| a price rise in an amendment not yet in effect | hold | yes | amendment, clause 4 | 15 |
| the price the latest of two amendments set | pay | yes | latest amendment, clause 4 | 15 |
| the price an earlier amendment set, since lowered (the PO's price) | hold | no | latest amendment, clause 4 | 15 |
| a rush fee Purchasing approved in writing | pay | yes | the approval email, the manual | 15 |
| a rush fee with no written approval | hold | yes | the manual | 15 |
| control: one unit more than was received | hold | no | receipt, as in round 3 | 15 |
| control: a unit price above the PO's | hold | no | PO, as in round 3 | 15 |

Unapproved rush fees come four ways: an offer never answered, an offer
declined, an approval for a different PO, and the vendor saying it was agreed
by phone. `evals/tests/test_round5.py` checks that each kind's documents
settle its answer, and the generator records which passages decide each case
(`deciding`). The labels are audited as in round 3, by a reviewer who has
seen no answers, before results are read.

### The arms

Haiku reviews every invoice in each arm; only what it is shown of the
documents changes:

1. **PO only**: today's prompt. The baseline.
2. **Everything**: all of the vendor's documents and the whole manual.
3. **Keyword**: for each invoice line, the 3 passages BM25 ranks highest.
4. **Embeddings**: the same, ranked by a small embedding model.
5. **Both**: the same, with the two rankings fused.

Retrieval searches the vendor's own documents and the manual, as the app
would: it knows the vendor from intake. Each line is its own query (what it
bills, without the invoice number or dates), and the best of each line's
ranking are taken in turn, so a review is shown about 6 passages.

The embedding model is a static one (model2vec's potion-base-8M, 30 MB, from
its maker's Hugging Face organisation, in safetensors) that runs on numpy; no
PyTorch, no vector database, no local LLM.

### Pilot

On another case set (seed 105), with no answer from round 5's:

- **Retrieval, scored without a model.** The obvious query, the whole
  invoice at once, was scored first; on round 5's own cases too, since that
  needs no model. It finds little: the vendor's name and PO number, in most
  of its documents, outweigh a freight line or a rush fee. Querying each
  line separately was then built on the pilot set alone and fixed before
  round 5 was scored. Both are reported.
- **22 invoices in all five arms** (110 Haiku calls). Two faults in the
  generated documents came out, both fixed before round 5: the manual asked
  for the vendor's tax ID on the invoice, which the review is not shown, and
  one review held a payable invoice for it; and clause 4, which says an
  amendment's price applies to invoices dated from its effective date, was
  not counted among the passages that decide the price cases, though
  without it a review can reasonably read an amendment as applying by
  delivery date. It is counted now, so retrieval is scored on finding it.

### Questions

1. **How often is every deciding passage shown?** For each retriever, and
   for the one-query baseline.
2. **Without the documents, what goes wrong?** Wrong payments and needless
   holds under arm 1, per kind.
3. **Does showing everything fix it, and at what cost** in tokens and
   dollars per invoice?
4. **Does retrieval match arm 2's decisions at lower cost?** Where it
   doesn't, was a deciding passage not shown, or shown and misread?
5. **Do the controls stay caught** under arms 2 to 5?

Tokens per invoice are reported for every arm, so the cost of showing
everything can be projected to larger libraries.

Not tested: scanned contracts, terms that conflict without a clear later
date, and libraries too large for one vendor's documents to fit in a prompt.

### Round 5 results

The label audit agreed with all 44 labels it checked (40 at random, topped
up so each kind a document decides had at least 3), so no case was dropped.
It found no case the documents leave open, and noted what could mislead: the
pricing clause says prices are "firm for the life of each Purchase Order"
before it says an amendment's price applies to open POs; in several price
cases the goods arrived before the amendment took effect and were invoiced
after; and the automatic checks flag most of the payable cases and pass
most of the held ones. It also found cosmetic faults in the generator, none
changing an answer: agreement numbers dated a year off their effective
dates, a few approval emails dated before their PO, holiday-closure emails
in spring, an amendment pricing an item of another trade, and vendors in
different cases sharing a name or email domain.

| Arm | Wrong payments | Paid wrongly | To a person | Needless reviews | Model cost per invoice | Input tokens |
|---|---:|---:|---:|---:|---:|---:|
| PO only | 15 | $31,452.12 | 136 | 61 | $0.00055 | 1,699 |
| everything | 0 | $0 | 91 | 1 | $0.00168 | 6,300 |
| keyword | 0 | $0 | 106 | 16 | $0.00077 | 2,413 |
| embeddings | 0 | $0 | 103 | 13 | $0.00077 | 2,360 |
| both | 0 | $0 | 108 | 18 | $0.00078 | 2,442 |

Wrong outcomes by kind (a wrong payment for a kind to hold, a needless
review for a kind to pay):

| Kind | PO only | everything | keyword | embeddings | both |
|---|---:|---:|---:|---:|---:|
| clean (50) | 1 | 1 | 0 | 1 | 0 |
| freight within the agreement's cap | 15 | 0 | 5 | 1 | 1 |
| price rise in an amendment in effect | 15 | 0 | 5 | 4 | 9 |
| the latest amendment's price | 15 | 0 | 0 | 0 | 1 |
| rush fee approved in writing | 15 | 0 | 6 | 7 | 7 |
| every kind to hold | 15 (superseded prices) | 0 | 0 | 0 | 0 |

1. **Retrieval showed every deciding passage for 46 to 57 of the 120
   cases a document decides** (keyword 46, embeddings 56, both 57), about 6
   passages a review. It always found the amendments and the freight clause
   when prices were delivered; what it missed was clause 4, which says how
   an amendment applies and shares no words with an invoice line, and, for
   rush fees, the approval email or the manual's section. The obvious query,
   the whole invoice at once, did worse still: 17 to 32 of 120.
2. **Without the documents, every superseded price was paid** (15 invoices,
   $31,452): each bills the PO's price, which a later amendment lowered, so
   the rules pass it and the PO agrees with it. And every payable invoice
   whose terms live in the documents was held: 60 of them.
3. **Showing everything fixed it**: no wrong payment, and one needless
   review (c112, a clean invoice held over the duplicate check's 120-day
   window). It cost $0.00168 an invoice, three times PO only, at about
   6,300 input tokens.
4. **Retrieval paid nothing wrongly either, at under half the cost of
   everything, but sent 12 to 17 more payable invoices to a person.** In
   all but a few of them a deciding passage was not shown: without clause 4,
   Haiku read an amendment as applying by delivery date; without the
   freight clause or the approval email, it could not see that the charge
   was allowed. Its misses held invoices rather than paying them, because
   the policy says to hold what the documents do not support.
5. **The controls stayed caught**: one unit over, and a price above the
   PO with no amendment behind it, were held in every arm.

So, for one vendor's documents (about 1,800 words with the manual), giving
the review all of them is better than retrieving from them: retrieval saved
$0.91 per thousand invoices and cost 12 to 17 needless reviews per 200, each
a person's time. At the cost measured here, about $0.25 per million input
tokens, showing everything adds about $6 per thousand invoices for each
10,000 more words of a vendor's documents, so it stays the cheaper choice
until a vendor's documents run to well beyond what one prompt should hold.
Retrieval earns its place when they cannot be narrowed to one vendor, or
grow past that; and then it needs the clauses that say how to read the
others (here, clause 4) always to be included, which ranking alone does not
do.

The pilot's answers and prompts are in `data/pilot5-seed105-first/`, and
the per-line retrieval scores on the pilot set as finally built in
`data/pilot5-seed105/`.
