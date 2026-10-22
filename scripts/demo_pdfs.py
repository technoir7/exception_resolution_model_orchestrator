#!/usr/bin/env python
"""
Three of the benchmark's invoices as PDFs, with the records they are checked
against, to upload on the dashboard's Invoices page:

    python scripts/demo_pdfs.py pdfs/

One asks to be paid into a bank account that is not on file, one is clean,
and one has a line that does not add up. Their vendors, POs, receipts and
paid history are added to the demo tenant, so intake can match the vendor.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.models.base import async_session_maker, init_db
from evals import reading, render, seed
from scripts.demo import TENANT_ID

KINDS = ["unverified_bank_change", "clean", "math_error"]


async def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    await init_db()
    cases = reading.printed_cases(4)
    chosen = [next(c for c in cases if c["kind"] == kind) for kind in KINDS]
    async with async_session_maker() as db:
        for case in chosen:
            await seed.load_records(db, TENANT_ID, case)
        await db.commit()
    for case in chosen:
        path = out / f"{case['invoice']['invoice_number']}.pdf"
        path.write_bytes(render.render(case))
        print(f"{path}  {case['vendor']['name']}  {case['kind'].replace('_', ' ')}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(Path(sys.argv[1])))
