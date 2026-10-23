"""Ranking a vendor's documents against an invoice."""

import pytest

from apps.api.services.retrieval import Passage, fused, keyword_ranking, vector_ranking


def p(id, text, title=""):
    return Passage(id=id, source="agreement", title=title, text=text)


class TestKeywordRanking:
    def test_ranks_the_passage_sharing_the_rare_words_first(self):
        passages = [
            p("ins", "Supplier shall maintain general liability insurance of not less than $1,000,000."),
            p("frt", "Freight is billable at cost, not to exceed $150 per shipment."),
            p("law", "This agreement is governed by the laws of the State of California."),
        ]
        assert keyword_ranking("Freight charges 1 x 142.00", passages)[0] == "frt"

    def test_a_word_in_every_passage_counts_for_little(self):
        passages = [
            p("a", "supplier supplier supplier shall deliver"),
            p("b", "supplier shall invoice the expedite fee"),
        ]
        assert keyword_ranking("supplier expedite", passages)[0] == "b"

    def test_searches_the_title_too(self):
        passages = [p("a", "Charges at cost.", title="Freight"), p("b", "Charges at cost.", title="Notices")]
        assert keyword_ranking("freight", passages)[0] == "a"

    def test_ignores_case_and_punctuation(self):
        passages = [p("a", "Unit price of HEX BOLT M10 x 40, zinc"), p("b", "Bearing 6205-2RS")]
        assert keyword_ranking("hex bolt m10", passages)[0] == "a"

    def test_returns_every_passage_once(self):
        passages = [p(str(i), f"clause {i}") for i in range(5)]
        ranking = keyword_ranking("clause 3", passages)
        assert sorted(ranking) == sorted(x.id for x in passages)
        assert ranking[0] == "3"

    def test_keeps_the_given_order_for_ties(self):
        passages = [p("first", "same words"), p("second", "same words")]
        assert keyword_ranking("nothing shared", passages) == ["first", "second"]

    def test_an_empty_library_ranks_nothing(self):
        assert keyword_ranking("anything", []) == []


class TestVectorRanking:
    def test_ranks_by_cosine_similarity(self):
        vectors = {"near": [1.0, 0.1], "far": [-1.0, 0.0], "middle": [0.5, 0.5]}
        assert vector_ranking([1.0, 0.0], vectors) == ["near", "middle", "far"]

    def test_length_does_not_matter(self):
        assert vector_ranking([1.0, 0.0], {"long": [10.0, 1.0], "short": [0.1, 0.0]}) == ["short", "long"]

    def test_a_zero_vector_ranks_last(self):
        assert vector_ranking([1.0, 0.0], {"zero": [0.0, 0.0], "some": [0.2, 1.0]}) == ["some", "zero"]


class TestFused:
    def test_a_passage_near_the_top_of_both_beats_one_top_of_only_one(self):
        keyword = ["a", "b", "x"]
        vector = ["c", "b", "y"]
        assert fused(keyword, vector)[0] == "b"

    def test_includes_passages_from_either_ranking(self):
        assert sorted(fused(["a", "b"], ["c"])) == ["a", "b", "c"]

    def test_one_ranking_is_unchanged(self):
        assert fused(["x", "y", "z"]) == ["x", "y", "z"]

    def test_needs_a_ranking(self):
        with pytest.raises(ValueError):
            fused()
