"""Round 5's arms: what the review is shown of the vendor's documents."""

import pytest

from apps.api.services.retrieval import Passage
from evals import cases, library, rag

ALL = cases.generate(seed=5, counts=cases.COUNTS_5, documents=True)


def first(kind):
    return next(c for c in ALL if c["kind"] == kind)


class FakeEmbedder:
    """Counts a few telling words; enough to rank without a model."""
    WORDS = ("freight", "price", "rush", "expedite", "insurance")

    def encode(self, texts):
        return [[t.lower().count(w) + 0.01 for w in self.WORDS] for t in texts]


class TestTheQuery:
    def test_carries_what_the_invoice_bills_and_who_from(self):
        case = first("rush_fee_approved")
        q = rag.query(case)
        assert case["invoice"]["vendor_name"] in q and case["po"]["po_number"] in q
        for line in case["invoice"]["line_items"]:
            assert line["description"] in q

    def test_never_the_answer(self):
        for case in ALL[:40]:
            q = rag.query(case)
            assert case["kind"] not in q and case["truth"]["reason"] not in q


class TestCandidates:
    def test_are_the_vendors_own_documents_and_the_manual(self):
        case = first("clean")
        ids = {p.id for p in rag.candidates(case)}
        assert ids == {p["id"] for p in case["documents"]} | {p["id"] for p in library.manual()}

    def test_are_passages(self):
        assert all(isinstance(p, Passage) for p in rag.candidates(first("clean")))


class TestWhatEachArmShows:
    def rankings(self, case):
        return rag.rankings([case], FakeEmbedder())[case["id"]]

    def test_po_only_shows_no_documents(self):
        case = first("clean")
        assert rag.shown(case, "po_only", self.rankings(case)) is None

    def test_everything_shows_every_candidate(self):
        case = first("superseded_price")
        shown = rag.shown(case, "everything", self.rankings(case))
        assert {p.id for p in shown} == {p.id for p in rag.candidates(case)}

    @pytest.mark.parametrize("arm", ["keyword", "embeddings", "hybrid"])
    def test_a_retrieval_arm_shows_its_selection_for_each_line(self, arm):
        case = first("msa_freight_not_allowed")
        selected = self.rankings(case)
        shown = rag.shown(case, arm, selected)
        assert [p.id for p in shown] == selected["per_line"][arm]
        assert len(shown) <= rag.PER_LINE * len(case["invoice"]["line_items"])
        assert len(set(p.id for p in shown)) == len(shown)

    def test_the_one_query_baseline_takes_the_top(self):
        case = first("rush_fee_unapproved")
        selected = self.rankings(case)
        for arm in rag.RETRIEVERS:
            assert len(selected["one_query"][arm]) == rag.TOP


class TestPerLine:
    def test_queries_are_what_each_line_bills(self):
        case = first("rush_fee_approved")
        assert rag.line_queries(case) == [l["description"] for l in case["invoice"]["line_items"]]

    def test_interleaves_the_best_of_each_line_first(self):
        assert rag._interleave([["a", "b", "c"], ["x", "a", "y"]], 2) == ["a", "x", "b"]


class TestScoringRetrieval:
    def test_counts_cases_whose_deciding_passages_are_all_in_the_top(self):
        cs = [{"id": "a", "kind": "k", "deciding": ["x", "y"]},
              {"id": "b", "kind": "k", "deciding": ["x"]},
              {"id": "c", "kind": "clean", "deciding": []}]
        chosen = {"a": {"keyword": ["x", "q", "y"]}, "b": {"keyword": ["q", "r", "s"]}, "c": {"keyword": ["z"]}}
        out = rag.retrieval_scores(cs, chosen)["keyword"]
        assert out["decided_cases"] == 2
        assert out["all_found"] == 1
        assert out["missed"] == {"b": ["x"]}
        assert out["by_kind"] == {"k": {"all_found": 1, "cases": 2}}
        assert out["passages_shown"] == round(7 / 3, 1)


class TestPrompts:
    async def test_everything_puts_the_deciding_passage_before_the_model(self):
        case = first("msa_freight_not_allowed")
        ranking = rag.rankings([case], FakeEmbedder())
        built = await rag.prompts([case], "everything", ranking)
        assert library.FREIGHT_INCLUDED in built[case["id"]]["prompt"]

    async def test_po_only_is_todays_prompt(self):
        case = first("msa_freight_not_allowed")
        ranking = rag.rankings([case], FakeEmbedder())
        built = await rag.prompts([case], "po_only", ranking)
        assert "VENDOR'S AGREEMENT" not in built[case["id"]]["prompt"]
        assert built[case["id"]]["shown"] is None

    async def test_a_retrieval_arm_records_what_it_showed(self):
        case = first("msa_freight_not_allowed")
        ranking = rag.rankings([case], FakeEmbedder())
        built = await rag.prompts([case], "keyword", ranking)
        assert built[case["id"]]["shown"] == ranking[case["id"]]["per_line"]["keyword"]
