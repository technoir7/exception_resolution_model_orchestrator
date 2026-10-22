# Backlog

Known gaps, roughly in order of what would matter most to a real deployment.

## Harder benchmark cases

Round 3 added errors the rules cannot see and look-alike pairs, and Haiku
still paid nothing wrongly, so the benchmark has not yet found where it fails.
Next: invoices with several problems at once, documents read from PDFs, and
holds escalated to a stronger model when the cheap one is unsure (Haiku's one
unsure hold in round 3 would have gone to Opus).

## Reading invoice PDFs

Invoices arrive as structured JSON. Real ones arrive as PDFs and scans, which
would need extraction before the rules and the review, and a measure of how
often extraction errors turn into wrong payments.

## Invoices across several POs

The matching engine assumes one invoice per PO. An invoice that bills two POs,
or part of a consolidated one, is flagged and left to the review, which reads
it as it is. The rules could match it instead.

## Duplicate window

The fuzzy duplicate check looks a week either side of an invoice's date, which
is why resubmissions weeks later pass the rules. The review catches them when
it reads every invoice; the rules alone do not.

## Rate limiting

No rate limiting on the API. The daily model spend cap bounds what a flood of
invoices could cost, but not the load.

## Tenant isolation in the database

Tenant isolation is in the application only; a query that skips the tenant
filter would leak another tenant's data. PostgreSQL row-level security would
enforce it below the application.

## Notifications

No notification when an exception nears or passes its deadline.

## Production deployment

Logins are demo accounts with a development secret. A deployment would need
real identity, secrets management, and CI.
