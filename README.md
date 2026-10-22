# AP Reconciliation Orchestrator

Checks supplier invoices before they are paid. Fixed rules compare each invoice
with its purchase order, goods receipt and the vendor's history; a Claude model
then reads the documents and says pay or hold; a hold goes to a person, never
straight to payment or rejection. Every step is logged, and every model call is
recorded at what it cost.

## Result

On a benchmark of 200 invoices with known right answers
([method and data](evals/README.md)):

| How invoices are processed | Wrong payments | Sent to a person | Of which payable | Model cost per invoice |
|---|---:|---:|---:|---:|
| Rules only | 18 ($56,605) | 130 | 66 | $0 |
| Haiku reads the invoices the rules flag | 18 ($56,605) | 64 | 0 | $0.0004 |
| **Haiku reads every invoice** | **0** | **82** | **0** | **$0.0006** |
| Opus reads every invoice | 0 | 82 | 0 | $0.0181 |
| Haiku reads every invoice, Opus checks large or unsure pays | 0 | 82 | 0 | $0.0034 |

- **What the model reads mattered more than which model reads it.** The rules
  pass invoices that ask for payment to a new bank account, and duplicates
  resubmitted weeks later. A model that reads only what the rules flag never
  sees them; one that reads every invoice caught all 18.
- **The cheapest model was enough.** Haiku, Sonnet and Opus decided every
  invoice they read correctly, with the right reason for every hold, so Haiku
  did Opus's work for about 1/30 of the cost: $0.58 per thousand invoices.
  Asking Opus for a second opinion never changed a decision, so it is off by
  default.
- **Against the rules alone, nothing payable waited for a person.** The rules
  flag partial deliveries, sales tax on a pre-tax PO, freight within its cap
  and weekly service bills as exceptions; the models cleared all 66.

The invoices are synthetic, generated with their answers fixed by
construction, and an independent reviewer checked a sample of the answers.
The documents are clean structured data with one problem per invoice, so the
benchmark is at its ceiling for all three models: it shows the cheap model is
enough for documents like these, not where it would start to fail. Invoices
read from PDFs, with several problems at once, would be harder.

Until this measurement the model was a stand-in that returned canned answers,
and the cost figures were estimates; both are now real.

## How it works

1. **Rules** (`apps/api/services/rules_engine.py`): required fields, dates,
   exact and fuzzy duplicates, the PO exists and is open, amount and quantity
   within tolerance of the PO, and the vendor matches the PO's.
2. **Three-way match** (`matching_engine.py`): invoice against PO and receipt.
   Everything these two object to becomes a list of flags (`flags.py`).
3. **Review** (`review.py`, `case_file.py`): the model is shown what a person
   would pull up: the invoice, the vendor record with the bank account on
   file, the PO and its terms, the goods receipt, the vendor's recent paid
   invoices, and the flags. It answers in JSON: pay or hold, a reason, a
   confidence and a short explanation citing the documents. An unreadable
   answer is asked again once, then goes to a person.
4. **Decision** (`pipeline_orchestrator.py`): a pay is approved; a hold opens
   an exception for the right person (duplicates and bank changes to the
   controller, quantities to an operator), with a deadline.
5. **Cost and audit**: each call goes through the `claude` command
   (`claude_provider.py`), which reports what it would cost at API list prices;
   that is what is recorded and summed against a daily cap per tenant. Every
   step is written to an audit trail, and a run can be replayed to see whether
   its outcome drifts.

Claude is called through the `claude` command on your own login, so a Claude
subscription pays for the reviews and no API key is needed. A hosted copy
would call the API instead.

## Running it

Tests and the benchmark need Python 3.11+ and [uv](https://docs.astral.sh/uv/);
no Docker and no model calls for the tests.

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest apps/api/tests evals/tests      # 102 tests, on SQLite
```

The benchmark needs the `claude` command, logged in:

```bash
.venv/bin/python -m evals.collect --round 3 --model haiku   # one model's answers
.venv/bin/python -m evals.score --round 3                   # every arm it can score
```

The full app (Postgres, Redis, the API, a worker and a Next.js dashboard) runs
in Docker:

```bash
make dev     # API on :8000 (docs at /docs), dashboard on :3000
make seed    # sample vendors, POs and receipts
make demo    # process the sample invoices
```

The `claude` command is not in the Docker image, so there the review is off
(`REVIEW_WITH_MODELS=false`) and the rules decide alone. That shows their
weakness: all ten sample invoices are flagged, the clean ones because their
sales tax takes them over the pre-tax PO total, so all ten go to a person.

To have Claude review them, run the demo and the API on your machine, against
the database in Docker: `.venv/bin/python scripts/demo.py` and `make dev-api`.
Haiku then pays the four clean invoices (checking their 8% tax against the PO
terms) and holds the other six, each with its reason: a missing PO, a
duplicate, a price above the PO, 25 units billed where 20 arrived, the wrong
vendor, and a second invoice for goods already billed. That run cost under a
cent.

Demo logins: `controller`, `ap_manager` and `bpo_operator`, password `demo123`.

## Settings

| Variable | Default | |
|---|---|---|
| `REVIEW_WITH_MODELS` | `true` | Off, the rules decide alone |
| `REVIEW_SCOPE` | `everything` | Or `flagged`: the model reads only what the rules flag |
| `REVIEW_SECOND_OPINION` | `false` | Opus checks Haiku's pays of $5,000 or more, or below 0.9 confidence |
| `ROUTER_TENANT_DAILY_CAP` | `100.00` | Model spend per tenant per day, in USD; past it, invoices go to a person |
| `AMOUNT_TOLERANCE_PERCENT` | `0.01` | Invoice total against the PO's |
| `QUANTITY_TOLERANCE_PERCENT` | `0.05` | Line quantities against the PO's and the receipt's |
| `FUZZY_MATCH_THRESHOLD` | `0.85` | Invoice-number similarity for a possible duplicate |
| `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET` | local development values | Set for any real deployment |

## API

Interactive docs at `/docs`. The main endpoints:

- `POST /ingest/invoice`: submit an invoice as JSON
- `POST /pipeline/run/{invoice_id}`: process it
- `GET /invoices`, `GET /exceptions`: lists, filterable by status, category and severity
- `POST /exceptions/{id}/resolve`: a person's decision on a held invoice
- `GET /audit/{invoice_id}`: the audit trail
- `POST /audit/replay/{invoice_id}/{run_id}`: replay a run and report drift
- `GET /metrics/cost`: model spend over a period

## Limitations

- Invoices arrive as structured JSON; reading PDFs is not built.
- An invoice billing several POs, or part of a consolidated one, is not
  matched (see `BACKLOG.md`); it goes to the review, which reads it as it is.
- The fuzzy duplicate check only looks a week either side, which is why late
  resubmissions get past the rules.
- Logins are demo accounts with a development secret.
