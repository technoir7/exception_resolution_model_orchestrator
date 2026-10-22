"""Reading rounds: an earlier round's invoices printed as PDFs, read by the
app's reader, then checked and reviewed exactly as before.

    python -m evals.reading --round 4      # record the reader's copy of each PDF

The readings are recorded once, like the models' answers, and replayed
through the app's own intake (`intake.ingest_pdf`): the same retry, the same
vendor matching, the same refusals. `evals.collect --round 4` then builds each
review prompt from the invoice as read, and `evals.score --round 4` scores
both the reading and the decisions. Resumable: a PDF already read is skipped.
"""

import argparse
import asyncio
import json
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.models.base import Base
from apps.api.services import extraction, intake, review
from apps.api.services.case_file import case_file_for
from apps.api.services.claude_provider import ClaudeCLI, ClaudeCLIError
from apps.api.services.llm_provider import LLMResponse
from evals import cases as case_set
from evals import render, seed

DATA = Path(__file__).parent / "data"
# A reading round, and the round whose invoices it prints.
ROUNDS = {4: 3}
CONCURRENCY = 4


def printed_cases(number: int) -> List[Dict]:
    source = ROUNDS[number]
    return case_set.generate(seed=source, counts=case_set.counts_for(source))


def as_printed(case: Dict) -> Dict:
    """What a perfect reader would copy from the case's PDF."""
    inv, vendor = case["invoice"], render.issuer(case)
    return {
        "invoice_number": inv["invoice_number"], "invoice_date": inv["invoice_date"], "due_date": inv["due_date"],
        "vendor_name": vendor["name"], "vendor_tax_id": vendor["tax_id"], "po_number": inv["po_number"],
        "currency": inv["currency"],
        "line_items": [{k: line[k] for k in ("description", "quantity", "unit_price", "amount")}
                       for line in inv["line_items"]],
        "subtotal": inv["subtotal"], "tax_amount": inv["tax_amount"], "total_amount": inv["total_amount"],
        "remit_to": inv["remit_to"], "notes": inv["notes"] or None, "service_period": None,
    }


class _Replay:
    """A reader that gives the recorded replies, in order."""

    def __init__(self, record: Dict):
        self.attempts = list(record["attempts"])

    async def read(self, document: bytes, instruction: str) -> LLMResponse:
        if not self.attempts:
            raise RuntimeError("the app asked the reader more times than were recorded")
        a = self.attempts.pop(0)
        return LLMResponse(content=a["reply"], model_id=a["model_id"], cost_usd=Decimal(a["cost_usd"]),
                           input_tokens=a.get("input_tokens", 0), output_tokens=a.get("output_tokens", 0))


async def prompts(cases: List[Dict], records: Dict[str, Dict]) -> Dict[str, Dict]:
    """Each case's prompt and flags, from its invoice as read; or why intake
    refused it, in which case it goes to a person."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    out = {}
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        for case in cases:
            await seed.load_records(db, seed.TENANT, case)
        await db.flush()
        invoices = {}
        for case in cases:
            try:
                invoices[case["id"]] = await intake.ingest_pdf(db, seed.TENANT, render.render(case),
                                                               _Replay(records[case["id"]]))
            except (extraction.UnreadableInvoice, intake.UnknownVendor) as error:
                out[case["id"]] = {"refused": f"{type(error).__name__}: {error}", "flags": ["refused at intake"],
                                   "amount": case["invoice"]["total_amount"]}
        for case in cases:
            if case["id"] in invoices:
                file = await case_file_for(db, seed.TENANT, invoices[case["id"]], today=case_set.AS_OF)
                out[case["id"]] = {"prompt": review.prompt(file), "flags": file.flags,
                                   "amount": str(file.invoice.total_amount)}
    await engine.dispose()
    return out


def _first_read(record: Dict) -> Optional[extraction.ExtractedInvoice]:
    for attempt in record["attempts"]:
        try:
            return extraction.parse(attempt["reply"])
        except extraction.UnreadableInvoice:
            continue
    return None


def _plain(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _differences(printed: extraction.ExtractedInvoice, read: extraction.ExtractedInvoice):
    for field in ("invoice_number", "vendor_name", "vendor_tax_id", "po_number", "currency", "notes"):
        if _plain(getattr(printed, field)) != _plain(getattr(read, field)):
            yield field, getattr(printed, field), getattr(read, field)
    for field in ("invoice_date", "due_date", "service_period", "subtotal", "tax_amount", "total_amount"):
        if getattr(printed, field) != getattr(read, field):
            yield field, str(getattr(printed, field)), str(getattr(read, field))
    p_remit, r_remit = printed.remit_to, read.remit_to
    if _plain(p_remit and p_remit.bank) != _plain(r_remit and r_remit.bank):
        yield "remit bank", p_remit and p_remit.bank, r_remit and r_remit.bank
    if (p_remit and p_remit.account_last4) != (r_remit and r_remit.account_last4):
        yield "remit account", p_remit and p_remit.account_last4, r_remit and r_remit.account_last4
    if len(printed.line_items) != len(read.line_items):
        yield "line count", len(printed.line_items), len(read.line_items)
        return
    for p, r in zip(printed.line_items, read.line_items):
        if _plain(p.description) != _plain(r.description):
            yield "line description", p.description, r.description
        for field in ("quantity", "unit_price", "amount"):
            if getattr(p, field) != getattr(r, field):
                yield f"line {field.replace('_', ' ')}", str(getattr(p, field)), str(getattr(r, field))


def accuracy(cases: List[Dict], records: Dict[str, Dict]) -> Dict:
    """How many invoices were read exactly as printed, and which fields were
    not. Formatting is not an error: 1430.6 for 1430.60, or spacing."""
    errors, examples, exact, unreadable = {}, [], 0, 0
    for case in cases:
        read = _first_read(records[case["id"]])
        if read is None:
            unreadable += 1
            continue
        found = list(_differences(extraction.ExtractedInvoice.model_validate(as_printed(case)), read))
        exact += not found
        for field, printed, got in found:
            errors[field] = errors.get(field, 0) + 1
            examples.append({"id": case["id"], "kind": case["kind"], "field": field,
                             "printed": printed, "read": got})
    return {"invoices": len(cases), "read_exactly": exact, "unreadable": unreadable,
            "field_errors": dict(sorted(errors.items())), "examples": examples}


def round_dir(number: int) -> Path:
    return DATA / f"round{number}"


def recorded(number: int) -> Dict[str, Dict]:
    path = round_dir(number) / f"reads-{intake.READER}.jsonl"
    return {r["id"]: r for r in map(json.loads, path.read_text().splitlines())}


async def _read(case: Dict) -> Optional[Dict]:
    """The reader's attempts at one PDF, as the app makes them; None if the
    model could not be reached, so that a rerun tries again."""
    reader, pdf, attempts = ClaudeCLI(intake.READER), render.render(case), []
    for _ in range(intake.ATTEMPTS):
        started = time.monotonic()
        try:
            response = await reader.read(pdf, extraction.INSTRUCTION)
        except (ClaudeCLIError, asyncio.TimeoutError) as error:
            print(f"{case['id']}  not reached: {str(error)[:200]}", flush=True)
            return None
        attempts.append({"reply": response.content, "model_id": response.model_id,
                         "cost_usd": str(response.cost_usd), "input_tokens": response.input_tokens,
                         "output_tokens": response.output_tokens, "seconds": round(time.monotonic() - started, 1)})
        try:
            extraction.parse(response.content)
            break
        except extraction.UnreadableInvoice:
            continue
    return {"id": case["id"], "model": intake.READER, "attempts": attempts}


async def main(number: int, limit: Optional[int]):
    folder = round_dir(number)
    folder.mkdir(parents=True, exist_ok=True)
    cases = printed_cases(number)[:limit]
    out = folder / f"reads-{intake.READER}.jsonl"
    done = {json.loads(line)["id"] for line in out.read_text().splitlines()} if out.exists() else set()
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(case):
        async with gate:
            record = await _read(case)
        if record:
            with out.open("a") as f:
                f.write(json.dumps(record) + "\n")
            print(f"{case['id']}  {len(record['attempts'])} attempt(s)  {record['attempts'][-1]['seconds']}s", flush=True)

    await asyncio.gather(*(one(c) for c in cases if c["id"] not in done))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True, choices=sorted(ROUNDS))
    parser.add_argument("--limit", type=int, help="only the first N cases (for a pilot)")
    args = parser.parse_args()
    asyncio.run(main(args.round, args.limit))
