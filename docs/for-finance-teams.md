# Catching bad supplier payments before they go out

*For accounts payable managers and controllers.*

## The problem

Most AP teams check invoices with fixed rules: does it match the purchase
order, was the order received, have we seen this invoice before. The rules
are fast, but they miss mistakes they weren't written for, and they flag
plenty of invoices that are fine. Your team spends its time clearing false
alarms while some wrong payments still get through.

## What this does

Before an invoice is paid, a Claude AI model reads it alongside what a
careful clerk would pull up: the purchase order, the goods receipt, the
vendor's bank details on file and their recent invoices. It says "pay" or
"hold", and gives its reason. A hold goes to a person with that reason
attached. The model never rejects an invoice: anything it won't approve
goes to a person. Every decision is logged, and so is what each check cost.

It takes invoices as data from your system or as PDFs, which it reads
itself.

## What it found in testing

I tested it on 600 invoices, each with a known right answer, with the test
planned in writing before it was run. On the hardest 200, whose mistakes the
fixed rules weren't written for, the rules let **58 wrong payments through,
worth $162,303**. Among them:

- a bank account changed only on the invoice, "as agreed by phone"
- a line whose amount isn't the quantity times the price
- one more unit billed than arrived
- a price just under 1% above the purchase order
- an invoice already paid, sent again weeks later and reworded

With the cheapest Claude model reading every invoice:

- **No wrong payments got through.**
- **Only 2 good invoices were held for a person**, compared with 47 under the
  rules alone.
- **It cost $0.62 per thousand invoices.**

When it read the same 200 from PDFs, it copied every one exactly. Still no
wrong payment got through, 4 good invoices were held, and reading and
checking together cost $1.73 per thousand.

These were clean, generated documents with one problem each, not your
invoices. Scanned paper and invoices with several problems at once are
harder, and I haven't tested those yet.

## How we'd start: measure first

Results on test invoices don't prove anything about yours, so nothing is
switched on until it has been measured on your own:

1. **You provide** a few hundred past invoices whose outcomes you know: the
   ones paid without trouble, and the ones later found to be wrong. Along
   with them, the matching purchase orders, goods receipts and vendor
   records.
2. **I run them through** with the model deciding nothing, and report what
   it would have done: the wrong payments it would have stopped, the good
   invoices it would have held for a person, and the cost per invoice. All
   of it is compared with how they were actually handled.
3. **You decide** whether those numbers justify a next step. That would
   start with the model working alongside your team, then approving only
   the invoices it is clearly sure of.

It can run on your own servers and call Claude with your company's own
Anthropic account, so the only outside party that sees your invoices is
Anthropic, under your own agreement with them.

## See it working

The code, the full test results and a demo are public:
[github.com/technoir7/exception_resolution_model_orchestrator](https://github.com/technoir7/exception_resolution_model_orchestrator).
To talk about measuring it on your invoices, message me on
[LinkedIn](https://www.linkedin.com/in/aaron-fung-bb0a3875).
