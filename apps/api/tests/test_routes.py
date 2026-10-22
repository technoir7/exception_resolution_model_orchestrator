"""The routes the dashboard reads and acts through, called as it calls them:
logged in, with a token."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from apps.api.models.cost import CostEvent, CostEventType
from apps.api.models.exception import ExceptionStatus
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.tests.conftest import TEST_TENANT_ID
from apps.api.tests.test_pipeline import a, exceptions, run, verdict


@pytest.fixture
async def api(db_session):
    from apps.api.dependencies import get_db
    from apps.api.main import app

    async def the_test_session():
        yield db_session

    app.dependency_overrides[get_db] = the_test_session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def login(api, user="ap_manager"):
    reply = await api.post("/auth/login", json={"username": user, "password": "demo123"})
    return {"Authorization": f"Bearer {reply.json()['access_token']}"}


def invoice(status=InvoiceStatus.PENDING, **fields):
    return Invoice(id=uuid4(), tenant_id=TEST_TENANT_ID, document_hash=uuid4().hex, document_type="pdf",
                   status=status, invoice_number="INV-1", vendor_id="V001", vendor_name="Acme",
                   currency="USD", subtotal=Decimal("100"), total_amount=Decimal("100"), **fields)


def spend(model, cost, invoice_id=None):
    return CostEvent(tenant_id=TEST_TENANT_ID, invoice_id=invoice_id, event_type=CostEventType.LLM_CALL,
                     model_id=model, input_tokens=1000, output_tokens=50, total_tokens=1050,
                     cost_usd=Decimal(cost), event_timestamp=datetime.utcnow())


class TestWhoIsLoggedIn:
    async def test_is_the_user_the_token_belongs_to(self, api):
        me = (await api.get("/auth/me", headers=await login(api, "bpo_operator"))).json()
        assert (me["username"], me["role"]) == ("bpo_operator", "bpo_operator")

    async def test_needs_a_token(self, api):
        assert (await api.get("/auth/me")).status_code in (401, 403)


class TestResolvingAnException:
    async def held(self, db):
        _, held, _ = await run(db, a("price_increase"), haiku=[verdict("hold", reason="price")])
        await db.commit()
        [case] = await exceptions(db)
        return held, case

    async def resolve(self, api, case, action):
        return await api.post(f"/exceptions/{case.id}/resolve", headers=await login(api),
                              json={"resolution": "checked with the vendor", "resolution_action": action})

    async def test_approving_pays_the_invoice(self, api, db_session):
        held, case = await self.held(db_session)
        assert (await self.resolve(api, case, "approve")).status_code == 200
        await db_session.refresh(held)
        assert held.status == InvoiceStatus.APPROVED
        assert case.status == ExceptionStatus.RESOLVED

    async def test_rejecting_rejects_it(self, api, db_session):
        held, case = await self.held(db_session)
        await self.resolve(api, case, "reject")
        await db_session.refresh(held)
        assert held.status == InvoiceStatus.REJECTED

    async def test_escalating_leaves_it_held_for_someone_else(self, api, db_session):
        held, case = await self.held(db_session)
        reply = (await self.resolve(api, case, "escalate")).json()
        await db_session.refresh(held)
        assert reply["status"] == "escalated" and held.status == InvoiceStatus.EXCEPTION
        assert (await self.resolve(api, case, "approve")).status_code == 200

    async def test_reprocessing_sends_it_back_through_the_pipeline(self, api, db_session):
        held, case = await self.held(db_session)
        await self.resolve(api, case, "reprocess")
        await db_session.refresh(held)
        assert held.status == InvoiceStatus.PENDING

    async def test_is_recorded_with_who_decided(self, api, db_session):
        held, case = await self.held(db_session)
        await self.resolve(api, case, "approve")
        events = (await api.get(f"/audit/{held.id}", headers=await login(api))).json()["events"]
        assert events[-1]["step"] == "exception_resolved"
        assert events[-1]["actor_type"] == "user" and events[-1]["actor_id"]
        assert events[-1]["raw_output"]["action"] == "approve"


class TestAnInvoice:
    async def test_shows_where_it_asks_to_be_paid_and_who_read_it(self, api, db_session):
        read = invoice(extracted_data={"remit_to": {"bank": "First Bank", "account_last4": "4321"},
                                       "read_by": "claude-haiku-5-5"})
        db_session.add(read)
        await db_session.commit()
        body = (await api.get(f"/invoices/{read.id}", headers=await login(api))).json()
        assert body["extracted_data"]["remit_to"]["account_last4"] == "4321"
        assert body["extracted_data"]["read_by"] == "claude-haiku-5-5"


class TestCost:
    async def test_is_what_was_spent_by_each_model(self, api, db_session):
        db_session.add_all([invoice(InvoiceStatus.APPROVED), invoice(InvoiceStatus.APPROVED),
                            invoice(InvoiceStatus.EXCEPTION), invoice(InvoiceStatus.PENDING),
                            spend("claude-haiku-5-5", "0.001"), spend("claude-haiku-5-5", "0.002"),
                            spend("claude-opus-5-5", "0.02")])
        await db_session.commit()
        body = (await api.get("/metrics/cost", headers=await login(api))).json()
        assert Decimal(body["total_cost_usd"]) == Decimal("0.023")
        assert body["invoices_by_status"] == {"approved": 2, "exception": 1, "pending": 1}
        assert Decimal(body["cost_per_invoice"]) == Decimal("0.00575")
        assert Decimal(body["spent_today"]) == Decimal("0.023")
        assert Decimal(body["daily_cap_usd"]) > 0
        assert [(m["model_id"], m["calls"], Decimal(m["cost_usd"])) for m in body["by_model"]] == [
            ("claude-opus-5-5", 1, Decimal("0.02")), ("claude-haiku-5-5", 2, Decimal("0.003"))]

    async def test_reports_nothing_it_does_not_measure(self, api):
        body = (await api.get("/metrics/cost", headers=await login(api))).json()
        assert not {k for k in body if "cache" in k or "exception_type" in k or "tier" in k}

    async def test_of_one_invoice_lists_its_calls(self, api, db_session):
        one = invoice()
        db_session.add(one)
        await db_session.flush()
        db_session.add_all([spend("claude-haiku-5-5", "0.001", one.id), spend("claude-haiku-5-5", "0.0005", one.id),
                            spend("claude-haiku-5-5", "0.9")])
        await db_session.commit()
        body = (await api.get(f"/metrics/cost/invoices/{one.id}", headers=await login(api))).json()
        assert Decimal(body["total_cost_usd"]) == Decimal("0.0015")
        assert [c["model_id"] for c in body["calls"]] == ["claude-haiku-5-5"] * 2

    async def test_of_an_unknown_invoice_is_not_found(self, api):
        reply = await api.get(f"/metrics/cost/invoices/{uuid4()}", headers=await login(api))
        assert reply.status_code == 404


class TestTheQueue:
    async def test_says_which_invoice_each_exception_holds(self, api, db_session):
        held, _ = await TestResolvingAnException().held(db_session)
        [item] = (await api.get("/exceptions?status=open", headers=await login(api))).json()["items"]
        assert item["invoice"]["invoice_number"] == held.invoice_number
        assert item["invoice"]["vendor_name"] == held.vendor_name
        assert Decimal(item["invoice"]["total_amount"]) == held.total_amount

    async def test_and_so_does_one_exception_and_its_resolution(self, api, db_session):
        held, case = await TestResolvingAnException().held(db_session)
        assert (await api.get(f"/exceptions/{case.id}", headers=await login(api))).json()["invoice"]["id"] == str(held.id)
        resolved = await TestResolvingAnException().resolve(api, case, "approve")
        assert resolved.json()["invoice"]["status"] == "approved"

    async def test_can_be_narrowed_to_one_invoice(self, api, db_session):
        held, case = await TestResolvingAnException().held(db_session)
        headers = await login(api)
        assert [e["id"] for e in (await api.get(f"/exceptions?invoice_id={held.id}", headers=headers)).json()["items"]] == [str(case.id)]
        assert (await api.get(f"/exceptions?invoice_id={uuid4()}", headers=headers)).json()["items"] == []


class TestProcessing:
    """Statuses come back from the database as plain strings, not enums."""

    @pytest.fixture
    async def stored(self, db_session, monkeypatch):
        from apps.api.config import settings
        from evals import seed
        monkeypatch.setattr(settings, "review_with_models", False)
        invoice = (await seed.load(db_session, TEST_TENANT_ID, [a("clean")]))[a("clean")["id"]]
        await db_session.commit()
        stored = invoice.id
        db_session.expire_all()
        return stored

    async def test_one_invoice_read_back_from_the_database(self, api, stored):
        reply = await api.post(f"/pipeline/run/{stored}", headers=await login(api))
        assert reply.status_code == 200, reply.text
        again = await api.post(f"/pipeline/run/{stored}", headers=await login(api))
        assert again.status_code in (200, 400), again.text

    async def test_a_batch(self, api, stored):
        reply = await api.post("/pipeline/run_batch", json={"invoice_ids": [str(stored)]}, headers=await login(api))
        assert reply.status_code == 200, reply.text
        assert reply.json()["queued"] == 1

    async def test_without_the_key_the_api_needs_says_so(self, api, stored, monkeypatch):
        from apps.api.config import settings
        monkeypatch.setattr(settings, "review_with_models", True)
        monkeypatch.setattr(settings, "claude_via", "api")
        monkeypatch.setattr(settings, "anthropic_api_key", None)
        reply = await api.post(f"/pipeline/run/{stored}", headers=await login(api))
        assert reply.status_code == 502 and "ANTHROPIC_API_KEY" in reply.json()["detail"]
