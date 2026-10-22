"""
Everything the deterministic checks object to about an invoice, in words.

An invoice with no flags matches its PO and receipt and repeats nothing the
vendor has billed; one with flags needs a judgement - from a model or a person -
before it is paid. The words are what that judgement is shown.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.invoice import Invoice
from apps.api.services.matching_engine import MatchingEngine, MatchResult, MatchStatus
from apps.api.services.rules_engine import RulesEngine, RulesResult


def describe(rules: RulesResult, match: MatchResult) -> List[str]:
    flags = [v.message for v in rules.violations]
    if match.status == MatchStatus.NO_MATCH and not match.variances:
        flags.append(match.summary)
    for v in match.variances:
        if v.within_tolerance:
            continue
        against = [f"PO {v.po_value}" if v.po_value is not None else None,
                   f"receipt {v.receipt_value}" if v.receipt_value is not None else None]
        flags.append(f"Match: {v.field} is {v.invoice_value} on the invoice against "
                     + ", ".join(a for a in against if a))
    return flags


async def flags_for(
    db: AsyncSession, tenant_id: UUID, invoice: Invoice, today: Optional[date] = None
) -> List[str]:
    rules = await RulesEngine(db, tenant_id, today=today).validate(invoice)
    match = await MatchingEngine(db, tenant_id).match(invoice)
    return describe(rules, match)
