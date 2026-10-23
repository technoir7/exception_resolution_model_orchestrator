"""Round 5: does the review need retrieval (RAG) to use the terms in a
vendor's documents, or does showing it all of them do as well?

    python -m evals.rag --round 5                               # prompts for every arm; retrieval scored
    python -m evals.collect --round 5 --model haiku --arm everything
    python -m evals.score --round 5

The arms differ only in what the review is shown of the vendor's agreement,
amendments and emails and the AP policy manual (see `evals/library.py`):
nothing (`po_only`, today's prompt), all of it (`everything`), or the
`PER_LINE` passages a retriever ranks highest for each line of the invoice. Retrieval searches the
vendor's own documents and the manual, as the app would: it knows the vendor
from intake. Which passages decide each case is known, so retrieval is scored
before any model is asked anything.
"""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.models.base import Base
from apps.api.services import review
from apps.api.services.case_file import case_file_for
from apps.api.services.retrieval import Passage, fused, keyword_ranking, vector_ranking
from evals import cases as case_set
from evals import library, seed

DATA = Path(__file__).parent / "data"
ROUNDS = {5}
ARMS = ("po_only", "everything", "keyword", "embeddings", "hybrid")
RETRIEVERS = ("keyword", "embeddings", "hybrid")
TOP = 5        # passages for the whole invoice, in the one-query baseline
PER_LINE = 3   # passages for each invoice line, in the arms
EMBEDDING_MODEL = "minishlab/potion-base-8M"


class Embedder(Protocol):
    def encode(self, texts: Sequence[str]): ...


def round_cases(number: int, seed_value: Optional[int] = None) -> List[Dict]:
    return case_set.generate(seed=number if seed_value is None else seed_value,
                             counts=case_set.counts_for(number), documents=True)


def query(case: Dict) -> str:
    """The whole invoice as one query: the obvious way, scored as a baseline."""
    inv = case["invoice"]
    lines = "; ".join(f"{l['description']} {l['quantity']} x {l['unit_price']}" for l in inv["line_items"])
    return (f"{inv['vendor_name']} invoice {inv['invoice_number']} dated {inv['invoice_date']} for "
            f"{inv['po_number']}. {lines}. {inv.get('notes') or ''}").strip()


def line_queries(case: Dict) -> List[str]:
    """One query per invoice line: what it bills, without the identifiers that
    every one of the vendor's documents shares."""
    return [l["description"] for l in case["invoice"]["line_items"]]


def candidates(case: Dict) -> List[Passage]:
    return [Passage(**p) for p in case["documents"] + library.manual()]


def _text(p: Passage) -> str:
    return f"{p.title} {p.text}"


def _rank(texts: List[str], pool: List[Passage], vectors, query_vectors) -> Dict[str, List[List[str]]]:
    """Each retriever's ranking of the pool for each query."""
    by_id = {p.id: list(map(float, v)) for p, v in zip(pool, vectors)}
    out: Dict[str, List[List[str]]] = {r: [] for r in RETRIEVERS}
    for text, qv in zip(texts, query_vectors):
        keyword = keyword_ranking(text, pool)
        embeddings = vector_ranking(list(map(float, qv)), by_id)
        out["keyword"].append(keyword)
        out["embeddings"].append(embeddings)
        out["hybrid"].append(fused(keyword, embeddings))
    return out


def _interleave(rankings: List[List[str]], per: int) -> List[str]:
    """The top `per` of each ranking, best ranks first, without repeats."""
    out: List[str] = []
    for position in range(per):
        for ranking in rankings:
            if position < len(ranking) and ranking[position] not in out:
                out.append(ranking[position])
    return out


def rankings(cases: List[Dict], embedder: Embedder) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
    """For each case and retriever, the passages a review would be shown:
    `per_line` (the method the arms use: the top `PER_LINE` for each line) and
    `one_query` (the top `TOP` for the whole invoice, the baseline)."""
    out = {}
    for case in cases:
        pool = candidates(case)
        lines = line_queries(case)
        texts = [_text(p) for p in pool]
        vectors = embedder.encode(texts + [query(case)] + lines)
        passage_vectors, whole, per_line = vectors[:len(pool)], vectors[len(pool)], vectors[len(pool) + 1:]
        one = _rank([query(case)], pool, passage_vectors, [whole])
        each = _rank(lines, pool, passage_vectors, per_line)
        out[case["id"]] = {
            "per_line": {r: _interleave(each[r], PER_LINE) for r in RETRIEVERS},
            "one_query": {r: one[r][0][:TOP] for r in RETRIEVERS},
        }
    return out


def shown(case: Dict, arm: str, selected: Dict[str, Dict[str, List[str]]]) -> Optional[List[Passage]]:
    if arm == "po_only":
        return None
    pool = candidates(case)
    if arm == "everything":
        return pool
    by_id = {p.id: p for p in pool}
    return [by_id[i] for i in selected["per_line"][arm]]


async def prompts(cases: List[Dict], arm: str, ranked: Dict[str, Dict[str, List[str]]]) -> Dict[str, Dict]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    out = {}
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        invoices = await seed.load(db, seed.TENANT, cases)
        for case in cases:
            file = await case_file_for(db, seed.TENANT, invoices[case["id"]], today=case_set.AS_OF)
            file.documents = shown(case, arm, ranked[case["id"]])
            out[case["id"]] = {"prompt": review.prompt(file), "flags": file.flags,
                               "amount": str(file.invoice.total_amount),
                               "shown": None if file.documents is None else [p.id for p in file.documents]}
    await engine.dispose()
    return out


def retrieval_scores(cases: List[Dict], selected: Dict[str, Dict[str, List[str]]]) -> Dict:
    """For each retriever: of the cases a document decides, how many were
    shown every deciding passage, by kind, which passages were missed, and how
    many passages were shown on average. `selected`: by case, by retriever."""
    out = {}
    retrievers = sorted({r for chosen in selected.values() for r in chosen})
    decided = [c for c in cases if c["deciding"]]
    for r in retrievers:
        found, missed, kinds = 0, {}, defaultdict(Counter)
        for c in decided:
            lost = [p for p in c["deciding"] if p not in set(selected[c["id"]][r])]
            kinds[c["kind"]]["cases"] += 1
            if lost:
                missed[c["id"]] = lost
            else:
                found += 1
                kinds[c["kind"]]["all_found"] += 1
        sizes = [len(selected[c["id"]][r]) for c in cases]
        out[r] = {"decided_cases": len(decided), "all_found": found, "missed": missed,
                  "passages_shown": round(sum(sizes) / len(sizes), 1),
                  "by_kind": {k: {"all_found": v["all_found"], "cases": v["cases"]} for k, v in sorted(kinds.items())}}
    return out


def _model() -> Embedder:
    from model2vec import StaticModel  # optional: only round 5 needs it
    return StaticModel.from_pretrained(EMBEDDING_MODEL)


def round_dir(number: int) -> Path:
    return DATA / f"round{number}"


async def main(number: int, limit: Optional[int], seed_value: Optional[int] = None):
    """With `seed_value`, a pilot set, written to its own folder."""
    folder = round_dir(number) if seed_value is None else DATA / f"pilot{number}-seed{seed_value}"
    folder.mkdir(parents=True, exist_ok=True)
    cases = round_cases(number, seed_value)[:limit]
    ranked = rankings(cases, _model())
    (folder / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
    (folder / "rankings.json").write_text(json.dumps(ranked))
    scores = {mode: retrieval_scores(cases, {i: ranked[i][mode] for i in ranked}) for mode in ("per_line", "one_query")}
    (folder / "retrieval.json").write_text(json.dumps(scores, indent=1))
    for arm in ARMS:
        built = await prompts(cases, arm, ranked)
        (folder / f"prompts-{arm}.jsonl").write_text("".join(json.dumps({"id": i, **p}) + "\n"
                                                             for i, p in built.items()))
        words = sum(len(p["prompt"].split()) for p in built.values()) / len(built)
        print(f"{arm:11} prompts: {len(built)}, {words:,.0f} words on average")
    for mode, by_retriever in scores.items():
        for r, s in by_retriever.items():
            print(f"{mode:9} {r:11} every deciding passage shown for {s['all_found']} of {s['decided_cases']} "
                  f"cases, {s['passages_shown']} passages shown on average")


def score(number: int) -> Dict:
    """Each arm's outcomes from Haiku's recorded answers, as `evals.score`
    scores the other rounds, with the tokens each prompt cost."""
    from evals import score as scoring
    folder = round_dir(number)
    cases = [json.loads(l) for l in (folder / "cases.jsonl").read_text().splitlines()]
    results = {"retrieval": json.loads((folder / "retrieval.json").read_text())}
    for arm in ARMS:
        path = folder / f"answers-haiku-{arm}.jsonl"
        if not path.exists():
            continue
        answers = {a["id"]: a for a in map(json.loads, path.read_text().splitlines())}
        if len(answers) != len(cases):
            continue
        outcomes = [scoring._one("haiku", c["id"], {"haiku": answers}) for c in cases]
        tokens = [sum(a.get("input_tokens", 0) for a in answers[c["id"]]["attempts"]) for c in cases]
        results[arm] = {**scoring.summarise(cases, outcomes), "by_kind": scoring.by_kind(cases, outcomes),
                        "input_tokens_per_invoice": round(sum(tokens) / len(tokens))}
    (folder / "results.json").write_text(json.dumps(results, indent=1))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True, choices=sorted(ROUNDS))
    parser.add_argument("--limit", type=int, help="only the first N cases (for a pilot)")
    parser.add_argument("--seed", type=int, help="a pilot case set, kept apart from the round's")
    args = parser.parse_args()
    asyncio.run(main(args.round, args.limit, args.seed))
