"""Scores each way of processing invoices against the right answers.

    python -m evals.score --round 1

Each way ("arm") decides every invoice as paid or sent to a person, from the
models' recorded answers. A person is assumed to decide correctly, so the
errors are wrong payments: invoices paid that should have been held. Sending a
payable invoice to a person is not an error but costs their time
(`needless_reviews`). Model cost is what the recorded calls cost at list
prices, including any retry.
"""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from apps.api.services import routing
from apps.api.services.review import Verdict

DATA = Path(__file__).parent / "data"
MODELS = ("haiku", "sonnet", "opus")

ARMS = [
    "rules only",
    *(f"{m} on flagged" for m in MODELS),
    "routed on flagged",
    *(f"{m} on everything" for m in MODELS),
    "routed on everything",
]


@dataclass
class Outcome:
    outcome: str          # "paid" or "person"
    cost: Decimal         # model calls, at list prices
    calls: int = 0


def _cost(answer) -> Decimal:
    return sum((Decimal(a.get("cost_usd") or "0") for a in answer["attempts"]), Decimal(0))


def _verdict(answer) -> Optional[Verdict]:
    last = answer["attempts"][-1]
    return Verdict(**last["verdict"]) if "verdict" in last else None


def _one(model, case_id, answers) -> Outcome:
    answer = answers[model][case_id]
    verdict = _verdict(answer)
    return Outcome("paid" if verdict and verdict.decision == "pay" else "person", _cost(answer),
                   len(answer["attempts"]))


def _routed(case, answers) -> Outcome:
    first = answers[routing.FIRST][case["id"]]
    verdict = _verdict(first)
    if verdict is None or not routing.needs_second_opinion(verdict, Decimal(case["invoice"]["total_amount"])):
        return Outcome("paid" if verdict and verdict.decision == "pay" else "person", _cost(first),
                       len(first["attempts"]))
    second = _one(routing.SECOND, case["id"], answers)
    return Outcome(second.outcome, _cost(first) + second.cost, len(first["attempts"]) + second.calls)


def run(arm: str, cases: List[dict], flagged: Dict[str, bool], answers) -> List[Outcome]:
    if arm == "rules only":
        return [Outcome("person" if flagged[c["id"]] else "paid", Decimal(0)) for c in cases]
    how, _, scope = arm.partition(" on ")
    out = []
    for c in cases:
        if scope == "flagged" and not flagged[c["id"]]:
            out.append(Outcome("paid", Decimal(0)))
        elif how == "routed":
            out.append(_routed(c, answers))
        else:
            out.append(_one(how, c["id"], answers))
    return out


def summarise(cases, outcomes: List[Outcome]) -> dict:
    wrong = [(c, o) for c, o in zip(cases, outcomes) if o.outcome == "paid" and c["truth"]["decision"] == "hold"]
    person = [(c, o) for c, o in zip(cases, outcomes) if o.outcome == "person"]
    cost = sum((o.cost for o in outcomes), Decimal(0))
    return {
        "invoices": len(cases),
        "wrong_payments": len(wrong),
        "wrong_payment_dollars": str(sum((Decimal(c["invoice"]["total_amount"]) for c, _ in wrong), Decimal(0))),
        "wrong_payment_kinds": dict(Counter(c["kind"] for c, _ in wrong)),
        "to_a_person": len(person),
        "needless_reviews": sum(c["truth"]["decision"] == "pay" for c, _ in person),
        "model_calls": sum(o.calls for o in outcomes),
        "model_cost_usd": str(cost.quantize(Decimal("0.0001"))),
        "model_cost_per_invoice_usd": str((cost / len(cases)).quantize(Decimal("0.00001"))),
    }


def by_kind(cases, outcomes) -> dict:
    table = defaultdict(Counter)
    for c, o in zip(cases, outcomes):
        table[c["kind"]][o.outcome] += 1
    return {k: dict(v) for k, v in sorted(table.items())}


def main(number: int):
    folder = DATA / f"round{number}"
    cases = [json.loads(l) for l in (folder / "cases.jsonl").read_text().splitlines()]
    prompts = {p["id"]: p for p in map(json.loads, (folder / "prompts.jsonl").read_text().splitlines())}
    flagged = {i: bool(p["flags"]) for i, p in prompts.items()}
    answers = {}
    for model in MODELS:
        path = folder / f"answers-{model}.jsonl"
        if path.exists():
            answers[model] = {a["id"]: a for a in map(json.loads, path.read_text().splitlines())}
    results = {}
    for arm in ARMS:
        needed = {routing.FIRST, routing.SECOND} if arm.startswith("routed") else \
            set() if arm == "rules only" else {arm.split(" on ")[0]}
        if not all(m in answers and len(answers[m]) == len(cases) for m in needed):
            continue
        outcomes = run(arm, cases, flagged, answers)
        results[arm] = {**summarise(cases, outcomes), "by_kind": by_kind(cases, outcomes)}
    (folder / "results.json").write_text(json.dumps(results, indent=1))
    print(f"{'arm':24} {'wrong paid':>10} {'$ wrong':>10} {'to person':>10} {'needless':>9} {'$/invoice':>10}")
    for arm, r in results.items():
        print(f"{arm:24} {r['wrong_payments']:>10} {r['wrong_payment_dollars']:>10} {r['to_a_person']:>10} "
              f"{r['needless_reviews']:>9} {r['model_cost_per_invoice_usd']:>10}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True)
    main(parser.parse_args().round)
