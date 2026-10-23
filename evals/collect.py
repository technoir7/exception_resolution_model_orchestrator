"""Asks each model for its verdict on every invoice in a round.

    python -m evals.collect --round 1 --model haiku [--limit 10] [--seed 0]
    python -m evals.collect --round 5 --model haiku --arm everything

For round 5 (see `evals.rag`) the prompts for each arm are built first, by
`python -m evals.rag --round 5`, and each arm's answers are kept apart.

For a reading round (see `evals.reading`), the prompts are built from the
invoices as read from their PDFs, so the readings must be recorded first.

Every invoice goes to every model, flagged or not, so that any way of
combining them (rules first, a cheap model first, the strongest model on
everything) can be scored afterwards from the same answers, without a model
call per combination. An answer the app could not read is retried once, as
the app does; both calls are paid for.

Resumable: an invoice already in the answers file is skipped.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.models.base import Base
from apps.api.services import review
from apps.api.services.case_file import case_file_for
from apps.api.services.claude_provider import ClaudeCLI, ClaudeCLIError
from evals import cases as case_set
from evals import rag, reading, seed

DATA = Path(__file__).parent / "data"
ATTEMPTS = 2
CONCURRENCY = 4


def round_dir(number: int) -> Path:
    return DATA / f"round{number}"


async def prompts(cases):
    """Each case's prompt and flags, as the app builds them, from a database
    holding exactly the round's records."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        invoices = await seed.load(db, seed.TENANT, cases)
        out = {}
        for case in cases:
            file = await case_file_for(db, seed.TENANT, invoices[case["id"]], today=case_set.AS_OF)
            out[case["id"]] = {"prompt": review.prompt(file), "flags": file.flags,
                               "amount": str(file.invoice.total_amount)}
    await engine.dispose()
    return out


async def ask(model: str, case_id: str, text: str) -> dict:
    provider = ClaudeCLI(model)
    attempts = []
    for _ in range(ATTEMPTS):
        started = time.monotonic()
        try:
            response = await provider.complete(text)
        except (ClaudeCLIError, asyncio.TimeoutError) as error:
            attempts.append({"error": str(error)[:500], "seconds": round(time.monotonic() - started, 1)})
            continue
        attempt = {"reply": response.content, "model_id": response.model_id, "cost_usd": str(response.cost_usd),
                   "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                   "seconds": round(time.monotonic() - started, 1)}
        try:
            attempt["verdict"] = review.parse(response.content).__dict__
        except review.UnreadableVerdict as error:
            attempt["unreadable"] = str(error)[:300]
        attempts.append(attempt)
        if "verdict" in attempt:
            break
    return {"id": case_id, "model": model, "attempts": attempts}


def _arm_prompts(folder: Path, arm: str, limit):
    cases = [json.loads(l) for l in (folder / "cases.jsonl").read_text().splitlines()][:limit]
    built = {p["id"]: p for p in map(json.loads, (folder / f"prompts-{arm}.jsonl").read_text().splitlines())}
    return cases, built


async def main(number: int, model: str, seed_value: int, limit, arm=None):
    folder = round_dir(number)
    if number in rag.ROUNDS and seed_value != number:
        folder = rag.DATA / f"pilot{number}-seed{seed_value}"  # a pilot set, built by evals.rag --seed
    folder.mkdir(parents=True, exist_ok=True)
    if number in rag.ROUNDS:
        if arm not in rag.ARMS:
            raise SystemExit(f"round {number} needs --arm, one of {', '.join(rag.ARMS)}")
        cases, built = _arm_prompts(folder, arm, limit)
    elif number in reading.ROUNDS:
        cases = reading.printed_cases(number)[:limit]
        built = await reading.prompts(cases, reading.recorded(number))
    else:
        cases = case_set.generate(seed=seed_value, counts=case_set.counts_for(number))[:limit]
        built = await prompts(cases)
    cases_path = folder / "cases.jsonl"
    if number in rag.ROUNDS:
        pass  # cases and prompts were written by evals.rag
    elif not cases_path.exists():
        cases_path.write_text("".join(json.dumps(c) + "\n" for c in cases))
    prompts_path = folder / "prompts.jsonl"
    if number not in rag.ROUNDS and not prompts_path.exists():
        prompts_path.write_text("".join(json.dumps({"id": i, **p}) + "\n" for i, p in built.items()))

    out = folder / (f"answers-{model}-{arm}.jsonl" if number in rag.ROUNDS else f"answers-{model}.jsonl")
    done = {json.loads(line)["id"] for line in out.read_text().splitlines()} if out.exists() else set()
    # An invoice refused at intake goes to a person without a review.
    todo = [c["id"] for c in cases if c["id"] not in done and "prompt" in built[c["id"]]]
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(case_id):
        async with gate:
            answer = await ask(model, case_id, built[case_id]["prompt"])
        with out.open("a") as f:
            f.write(json.dumps(answer) + "\n")
        last = answer["attempts"][-1]
        print(f"{case_id}  {model}  {last.get('verdict', {}).get('decision') or last.get('error') or 'unreadable'}"
              f"  {last.get('seconds')}s", flush=True)

    await asyncio.gather(*(one(i) for i in todo))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--model", required=True, choices=["haiku", "sonnet", "opus"])
    parser.add_argument("--seed", type=int, help="which case set (default: the round number)")
    parser.add_argument("--limit", type=int, help="only the first N cases (for a pilot)")
    parser.add_argument("--arm", choices=rag.ARMS, help="round 5: what the review is shown of the documents")
    args = parser.parse_args()
    asyncio.run(main(args.round, args.model, args.seed if args.seed is not None else args.round, args.limit,
                     args.arm))
