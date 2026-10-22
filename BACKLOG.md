# Backlog

Known gaps, roughly in order of what would matter most to a real deployment.

## Harder benchmark cases

Round 3 added errors the rules cannot see and look-alike pairs, and round 4
the same invoices as PDFs; Haiku still paid nothing wrongly, so the benchmark
has not yet found where it fails. Next: invoices with several problems at
once, and holds escalated to a stronger model when the cheap one is unsure.
Haiku's needless holds vary from run to run, so a measure of them should
average several runs.

## Scanned and multi-page invoices

The reader is measured only on clean, generated, one-page PDFs, all read
exactly. Scans, photographs, handwriting and invoices running over several
pages would test it, and whether a misread field turns into a wrong payment.

## Numbers as the reader writes them

The reader gives 1552.4 where an invoice prints 1552.40, and the review sees
it so. Round 4 found no effect, but writing amounts to the cent would keep the
review's view the same whichever way an invoice arrives.

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
