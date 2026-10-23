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
from typing import Dict, List, Optional, Tuple

from apps.api.services import routing
from apps.api.services.review import Verdict
from evals import reading as reading_round

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


def _decide(arm: str, case: dict, flagged: Dict[str, bool], answers) -> Outcome:
    if arm == "rules only":
        return Outcome("person" if flagged[case["id"]] else "paid", Decimal(0))
    how, _, scope = arm.partition(" on ")
    if scope == "flagged" and not flagged[case["id"]]:
        return Outcome("paid", Decimal(0))
    return _routed(case, answers) if how == "routed" else _one(how, case["id"], answers)


def run(arm: str, cases: List[dict], flagged: Dict[str, bool], answers, refused=frozenset(),
        reading: Optional[Dict[str, Tuple[Decimal, int]]] = None) -> List[Outcome]:
    """Each case's outcome under the arm. In a reading round every arm first
    pays to read the PDF (`reading`: cost and calls by case), and an invoice
    refused at intake goes to a person unreviewed."""
    out = []
    for c in cases:
        cost, calls = (reading or {}).get(c["id"], (Decimal(0), 0))
        decided = Outcome("person", Decimal(0)) if c["id"] in refused else _decide(arm, c, flagged, answers)
        out.append(Outcome(decided.outcome, decided.cost + cost, decided.calls + calls))
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


def _main_documents(number: int):
    from evals import rag
    results = rag.score(number)
    print(f"{'arm':12} {'wrong paid':>10} {'$ wrong':>10} {'to person':>10} {'needless':>9} {'$/invoice':>10} "
          f"{'tokens in':>10}")
    for arm, r in ((a, r) for a, r in results.items() if a != "retrieval"):
        print(f"{arm:12} {r['wrong_payments']:>10} {r['wrong_payment_dollars']:>10} {r['to_a_person']:>10} "
              f"{r['needless_reviews']:>9} {r['model_cost_per_invoice_usd']:>10} {r['input_tokens_per_invoice']:>10}")
    for mode, by_retriever in results["retrieval"].items():
        for r, s in by_retriever.items():
            print(f"{mode:9} {r:11} retrieval: every deciding passage shown for {s['all_found']} of "
                  f"{s['decided_cases']}")


def main(number: int):
    from evals import rag
    if number in rag.ROUNDS:
        return _main_documents(number)
    folder = DATA / f"round{number}"
    cases = [json.loads(l) for l in (folder / "cases.jsonl").read_text().splitlines()]
    prompts = {p["id"]: p for p in map(json.loads, (folder / "prompts.jsonl").read_text().splitlines())}
    flagged = {i: bool(p["flags"]) for i, p in prompts.items()}
    refused = {i for i, p in prompts.items() if "refused" in p}
    reading, results = None, {}
    if number in reading_round.ROUNDS:
        reads = reading_round.recorded(number)
        reading = {i: (_cost(r), len(r["attempts"])) for i, r in reads.items()}
        results["reading"] = {**reading_round.accuracy(cases, reads), "refused_at_intake":
                              {i: prompts[i]["refused"] for i in sorted(refused)}}
    answers = {}
    for model in MODELS:
        path = folder / f"answers-{model}.jsonl"
        if path.exists():
            answers[model] = {a["id"]: a for a in map(json.loads, path.read_text().splitlines())}
    for arm in ARMS:
        needed = {routing.FIRST, routing.SECOND} if arm.startswith("routed") else \
            set() if arm == "rules only" else {arm.split(" on ")[0]}
        if not all(m in answers and len(answers[m]) == len(cases) - len(refused) for m in needed):
            continue
        outcomes = run(arm, cases, flagged, answers, refused, reading)
        results[arm] = {**summarise(cases, outcomes), "by_kind": by_kind(cases, outcomes)}
    (folder / "results.json").write_text(json.dumps(results, indent=1))
    print(f"{'arm':24} {'wrong paid':>10} {'$ wrong':>10} {'to person':>10} {'needless':>9} {'$/invoice':>10}")
    if "reading" in results:
        r = results["reading"]
        print(f"read exactly: {r['read_exactly']} of {r['invoices']}; unreadable {r['unreadable']}; "
              f"refused at intake {len(r['refused_at_intake'])}; field errors {r['field_errors']}")
    for arm, r in ((a, r) for a, r in results.items() if a != "reading"):
        print(f"{arm:24} {r['wrong_payments']:>10} {r['wrong_payment_dollars']:>10} {r['to_a_person']:>10} "
              f"{r['needless_reviews']:>9} {r['model_cost_per_invoice_usd']:>10}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True)
    main(parser.parse_args().round)
