"""How each way of processing invoices is scored from the models' answers."""

from evals import score


def case(i, kind, amount="1000.00"):
    from evals.cases import PAY
    return {"id": i, "kind": kind, "truth": {"decision": "pay" if kind in PAY else "hold"},
            "invoice": {"total_amount": amount}}


def answer(decision, confidence=0.95, cost="0.001"):
    verdict = None if decision is None else {"decision": decision, "reason": "none", "confidence": confidence,
                                            "explanation": ""}
    attempt = {"cost_usd": cost}
    if verdict:
        attempt["verdict"] = verdict
    return {"attempts": [attempt]}


CASES = [case("a", "clean"), case("b", "partial_delivery"), case("c", "duplicate", "9000.00"),
         case("d", "bank_change")]
FLAGGED = {"a": False, "b": True, "c": True, "d": False}


def outcomes(arm, answers):
    return {c["id"]: o for c, o in zip(CASES, score.run(arm, CASES, FLAGGED, answers))}


def test_rules_only_pays_what_passes_and_sends_the_rest_to_a_person():
    out = outcomes("rules only", {})
    assert {k: v.outcome for k, v in out.items()} == {"a": "paid", "b": "person", "c": "person", "d": "paid"}
    assert all(v.cost == 0 for v in out.values())


def test_a_model_on_flagged_invoices_decides_only_those():
    answers = {"haiku": {"b": answer("pay"), "c": answer("hold")}}
    out = outcomes("haiku on flagged", answers)
    assert {k: v.outcome for k, v in out.items()} == {"a": "paid", "b": "paid", "c": "person", "d": "paid"}


def test_an_unreadable_answer_goes_to_a_person_and_is_still_paid_for():
    out = outcomes("haiku on flagged", {"haiku": {"b": answer(None, cost="0.002"), "c": answer("hold")}})
    assert out["b"].outcome == "person"
    assert out["b"].cost == score.Decimal("0.002")


def test_routing_asks_opus_only_when_the_policy_says():
    answers = {"haiku": {"b": answer("pay", 0.95), "c": answer("pay", 0.99)},
               "opus": {"b": answer("hold", cost="0.02"), "c": answer("hold", cost="0.02")}}
    out = outcomes("routed on flagged", answers)
    assert out["b"].outcome == "paid"            # small and sure: haiku stands
    assert out["c"].outcome == "person"          # 9,000 is large: opus decides
    assert out["c"].cost == score.Decimal("0.021")


def test_screening_everything_reads_the_clean_ones_too():
    answers = {"haiku": {k: answer("pay") for k in "abc"} | {"d": answer("hold")}}
    out = outcomes("haiku on everything", answers)
    assert out["d"].outcome == "person"


def test_a_wrong_payment_is_paying_what_should_be_held():
    out = outcomes("rules only", {})
    summary = score.summarise(CASES, list(out.values()))
    assert summary["wrong_payments"] == 1          # the bank change
    assert summary["wrong_payment_dollars"] == "1000.00"
    assert summary["to_a_person"] == 2
    assert summary["needless_reviews"] == 1        # the partial delivery
