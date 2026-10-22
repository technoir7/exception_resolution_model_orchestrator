"""The pipeline: rules first, then a model's review, then pay or a person."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from apps.api.models.cost import CostEvent
from apps.api.models.exception import ExceptionCase, ExceptionCategory
from apps.api.models.invoice import InvoiceStatus
from apps.api.models.pipeline import PipelineState
from apps.api.services import routing
from apps.api.services.llm_provider import LLMProvider, LLMResponse
from apps.api.services.pipeline_orchestrator import PipelineOrchestrator
from apps.api.tests.conftest import TEST_TENANT_ID
from evals import cases, seed

ALL = cases.generate(seed=1)


def a(kind, large=None):
    return next(c for c in ALL if c["kind"] == kind and (
        large is None or (Decimal(c["invoice"]["total_amount"]) >= routing.LARGE) == large))


def verdict(decision, confidence=0.95, reason="none"):
    return json.dumps({"decision": decision, "reason": reason, "confidence": confidence, "explanation": "x"})


class FakeModel(LLMProvider):
    def __init__(self, replies, cost="0.001"):
        self.replies, self.cost, self.prompts = list(replies), Decimal(cost), []

    async def complete(self, prompt, **_):
        self.prompts.append(prompt)
        return LLMResponse(content=self.replies.pop(0), model_id="fake", cost_usd=self.cost,
                           input_tokens=100, output_tokens=20, total_tokens=120)

    def get_model_id(self): return "fake"
    def get_tier(self): raise NotImplementedError
    def get_cost_per_1k_tokens(self): raise NotImplementedError


async def run(db, case, scope="flagged", second_opinion=False, **replies):
    """Runs `case` with fake models answering `replies` (by model name)."""
    models = {name: FakeModel(r) for name, r in replies.items()}
    invoice = (await seed.load(db, TEST_TENANT_ID, [case]))[case["id"]]
    pipeline = PipelineOrchestrator(db, TEST_TENANT_ID, models=lambda name: models[name],
                                    scope=scope, second_opinion=second_opinion, today=cases.AS_OF)
    result = await pipeline.run(invoice)
    return result, invoice, models


async def costs(db):
    return list((await db.execute(select(CostEvent))).scalars().all())


async def exceptions(db):
    return list((await db.execute(select(ExceptionCase))).scalars().all())


class TestWhatGetsPaid:
    async def test_a_clean_invoice_is_paid_without_asking_a_model(self, db_session):
        result, invoice, _ = await run(db_session, a("clean"))
        assert result.state == PipelineState.COMPLETED
        assert invoice.status == InvoiceStatus.APPROVED
        assert await costs(db_session) == []

    async def test_a_flagged_invoice_the_model_would_pay_is_paid(self, db_session):
        result, invoice, models = await run(db_session, a("partial_delivery", large=False),
                                            haiku=[verdict("pay")])
        assert invoice.status == InvoiceStatus.APPROVED
        assert "Line" in models["haiku"].prompts[0] or "Match" in models["haiku"].prompts[0]

    async def test_a_hold_goes_to_a_person(self, db_session):
        result, invoice, _ = await run(db_session, a("price_increase"), haiku=[verdict("hold", reason="price")])
        assert result.state == PipelineState.EXCEPTION
        [case] = await exceptions(db_session)
        assert case.category == ExceptionCategory.AMOUNT_VARIANCE

    async def test_reading_everything_asks_about_clean_invoices_too(self, db_session):
        result, _, models = await run(db_session, a("bank_change"), scope="everything",
                                      haiku=[verdict("hold", reason="bank_details")])
        assert result.state == PipelineState.EXCEPTION
        assert len(models["haiku"].prompts) == 1


class TestTheSecondOpinion:
    async def test_is_off_by_default_since_it_changed_no_decision_in_the_benchmark(self, db_session):
        invoice = (await seed.load(db_session, TEST_TENANT_ID, [a("tax_correct")]))[a("tax_correct")["id"]]
        assert PipelineOrchestrator(db_session, TEST_TENANT_ID).second_opinion is False

    async def test_reads_every_invoice_by_default(self, db_session):
        assert PipelineOrchestrator(db_session, TEST_TENANT_ID).scope == "everything"

    async def test_without_it_the_cheap_models_pay_stands(self, db_session):
        result, _, models = await run(db_session, a("partial_delivery", large=True),
                                      haiku=[verdict("pay")], opus=[])
        assert result.state == PipelineState.COMPLETED

    async def test_a_pay_on_a_large_invoice_is_checked_by_the_stronger_model(self, db_session):
        result, _, models = await run(db_session, a("partial_delivery", large=True), second_opinion=True,
                                      haiku=[verdict("pay")], opus=[verdict("hold", reason="quantity")])
        assert result.state == PipelineState.EXCEPTION
        assert len(models["opus"].prompts) == 1
        assert len(await costs(db_session)) == 2

    async def test_a_hold_is_not_checked(self, db_session):
        result, _, models = await run(db_session, a("price_increase", large=True), second_opinion=True,
                                      haiku=[verdict("hold", reason="price")], opus=[])
        assert result.state == PipelineState.EXCEPTION


class TestWhenTheModelFails:
    async def test_an_unreadable_answer_is_asked_again_once_then_goes_to_a_person(self, db_session):
        result, _, models = await run(db_session, a("partial_delivery", large=False), haiku=["Pay it.", "Pay it."])
        assert result.state == PipelineState.EXCEPTION
        assert len(models["haiku"].prompts) == 2
        [case] = await exceptions(db_session)
        assert case.category == ExceptionCategory.LLM_VALIDATION_FAILED

    async def test_without_models_a_clean_invoice_is_still_paid(self, db_session):
        invoice = (await seed.load(db_session, TEST_TENANT_ID, [a("clean")]))[a("clean")["id"]]
        result = await PipelineOrchestrator(db_session, TEST_TENANT_ID, models=None, scope="everything",
                                            today=cases.AS_OF).run(invoice)
        assert result.state == PipelineState.COMPLETED

    async def test_without_models_a_flagged_invoice_goes_to_a_person(self, db_session):
        invoice = (await seed.load(db_session, TEST_TENANT_ID, [a("tax_correct")]))[a("tax_correct")["id"]]
        result = await PipelineOrchestrator(db_session, TEST_TENANT_ID, models=None, today=cases.AS_OF).run(invoice)
        assert result.state == PipelineState.EXCEPTION


class TestCost:
    async def test_each_call_is_recorded_at_what_it_cost(self, db_session):
        await run(db_session, a("partial_delivery", large=False), haiku=[verdict("pay")])
        [event] = await costs(db_session)
        assert event.cost_usd == Decimal("0.001")
        assert event.model_id == "fake"

    async def test_past_the_daily_cap_invoices_go_to_a_person_unasked(self, db_session, monkeypatch):
        from apps.api.config import settings
        monkeypatch.setattr(settings, "router_tenant_daily_cap", Decimal("0"))
        result, _, models = await run(db_session, a("tax_correct"), haiku=[])
        assert result.state == PipelineState.EXCEPTION
        assert models["haiku"].prompts == []


class TestTheRecord:
    """The last audit event says what was decided, why, and what the rules
    flagged, so a person can see it without replaying the run."""

    async def last_event(self, db, invoice):
        from apps.api.services.audit_service import AuditService
        return (await AuditService(db, TEST_TENANT_ID).get_timeline(invoice.id))[-1].raw_output

    async def test_of_a_hold(self, db_session):
        _, invoice, _ = await run(db_session, a("price_increase"), haiku=[verdict("hold", reason="price")])
        last = await self.last_event(db_session, invoice)
        assert (last["decision"], last["why"]) == ("review", "x")
        assert last["flags"]

    async def test_of_a_pay(self, db_session):
        _, invoice, _ = await run(db_session, a("partial_delivery", large=False), haiku=[verdict("pay")])
        last = await self.last_event(db_session, invoice)
        assert (last["decision"], last["why"]) == ("approved", "x")
        assert last["flags"]
