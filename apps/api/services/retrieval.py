"""
Which passages of a vendor's documents a review should be shown.

A vendor's agreement, its amendments and its emails, with the buyer's AP
policy manual, run to thousands of words, most of it boilerplate that decides
nothing. These rank passages against an invoice so that only the few that
matter go into the prompt. Pure functions: an embedding model, if one is
used, belongs to the caller, who passes in its vectors.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence

SOURCES = ("agreement", "amendment", "email", "policy")


@dataclass(frozen=True)
class Passage:
    id: str
    source: str
    title: str
    text: str
    vendor_id: Optional[str] = None  # None for the buyer's own policy
    dated: Optional[str] = None      # ISO date: an amendment's effective date, an email's date


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def keyword_ranking(query: str, passages: Sequence[Passage], k1: float = 1.5, b: float = 0.75) -> List[str]:
    """Passage ids, best first, by BM25. Ties keep the order given."""
    docs = [_words(f"{p.title} {p.text}") for p in passages]
    if not docs:
        return []
    average = sum(map(len, docs)) / len(docs)
    containing = Counter(w for d in docs for w in set(d))
    idf = {w: math.log(1 + (len(docs) - n + 0.5) / (n + 0.5)) for w, n in containing.items()}
    query_words = set(_words(query))

    def score(doc: List[str]) -> float:
        counts = Counter(doc)
        norm = k1 * (1 - b + b * len(doc) / average) if average else k1
        return sum(idf[w] * counts[w] * (k1 + 1) / (counts[w] + norm) for w in query_words if w in counts)

    scores = [score(d) for d in docs]
    order = sorted(range(len(passages)), key=lambda i: -scores[i])
    return [passages[i].id for i in order]


def vector_ranking(query: Sequence[float], vectors: Mapping[str, Sequence[float]]) -> List[str]:
    """Ids, best first, by cosine similarity to the query."""
    def norm(v: Sequence[float]) -> float:
        return math.sqrt(sum(x * x for x in v))

    q = norm(query)

    def cosine(v: Sequence[float]) -> float:
        n = norm(v)
        return sum(a * b for a, b in zip(query, v)) / (q * n) if q and n else -math.inf

    return sorted(vectors, key=lambda i: -cosine(vectors[i]))


def fused(*rankings: Sequence[str], k: int = 60) -> List[str]:
    """Reciprocal rank fusion: a passage near the top of several rankings
    beats one at the top of only one."""
    if not rankings:
        raise ValueError("fused() needs at least one ranking")
    scores: Dict[str, float] = {}
    for ranking in rankings:
        for rank, id in enumerate(ranking, 1):
            scores[id] = scores.get(id, 0.0) + 1 / (k + rank)
    return sorted(scores, key=lambda i: -scores[i])
