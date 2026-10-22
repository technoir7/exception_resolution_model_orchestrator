"""
Pipeline: the rules and the three-way match first, then a model's review of
what they flag, then payment or a person.

A model's verdict is pay or hold, and a hold puts the invoice in front of a
person: no model rejects an invoice, and none pays one the rules flagged
without reading its documents. By default the cheapest model reads every
invoice; optionally the strongest checks its pays where a mistake would cost
most (`routing.py`). Every call is recorded at what it cost, and past the
tenant's daily cap invoices go to a person without one. The defaults are what
the benchmark in `evals/` supports.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Callable, List, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.audit import AuditStep
from apps.api.models.exception import ExceptionCategory, ExceptionSeverity
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.pipeline import InvoicePipelineRun, PipelineState
from apps.api.services import review, routing
from apps.api.services.audit_service import AuditService
from apps.api.services.case_file import case_file_for
from apps.api.services.claude_provider import TIER_MODELS, ClaudeCLI, ClaudeCLIError
from apps.api.services.cost_service import CostService
from apps.api.services.exception_handler import ExceptionHandler
from apps.api.services.flags import describe
from apps.api.services.llm_provider import LLMProvider
from apps.api.services.matching_engine import MatchingEngine
from apps.api.services.rules_engine import RulesEngine

logger = structlog.get_logger()

# What a hold is about, for routing the exception to the right person.
HOLD_CATEGORY = {
    "price": ExceptionCategory.AMOUNT_VARIANCE,
    "charges": ExceptionCategory.AMOUNT_VARIANCE,
    "tax": ExceptionCategory.AMOUNT_VARIANCE,
    "quantity": ExceptionCategory.QUANTITY_VARIANCE,
    "duplicate": ExceptionCategory.DUPLICATE,
    "vendor": ExceptionCategory.VENDOR_MISMATCH,
    "bank_details": ExceptionCategory.BANK_DETAILS,
}
TIERS = {model: tier for tier, model in TIER_MODELS.items()}
# One retry, as an unreadable answer is usually a formatting slip.
ATTEMPTS = 2


class PipelineOrchestrator:
    POLICY_VERSION = "v2"
    PROMPT_VERSION = "v2"

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        models: Optional[Callable[[str], LLMProvider]] = ClaudeCLI,
        scope: Optional[str] = None,
        second_opinion: Optional[bool] = None,
        today: Optional[date] = None,
        exception_handler: Optional[ExceptionHandler] = None,
        audit_service: Optional[AuditService] = None,
        cost_service: Optional[CostService] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
        self.models = models if settings.review_with_models else None
        self.scope = scope or settings.review_scope
        if self.scope not in ("flagged", "everything"):
            raise ValueError(f"review scope must be 'flagged' or 'everything', not {self.scope!r}")
        self.second_opinion = settings.review_second_opinion if second_opinion is None else second_opinion
        self.today = today
        self.exception_handler = exception_handler or ExceptionHandler(db, tenant_id)
        self.audit_service = audit_service or AuditService(db, tenant_id)
        self.cost_service = cost_service or CostService(db, tenant_id)

    async def run(
        self,
        invoice: Invoice,
        is_replay: bool = False,
        original_run_id: Optional[UUID] = None,
    ) -> InvoicePipelineRun:
        run = InvoicePipelineRun(
            tenant_id=self.tenant_id,
            invoice_id=invoice.id,
            state=PipelineState.INGESTED,
            ingested_at=datetime.utcnow(),
            policy_version=self.POLICY_VERSION,
            router_policy_version=self.POLICY_VERSION,
            is_replay=is_replay,
            original_run_id=original_run_id,
        )
        self.db.add(run)
        await self.db.flush()

        try:
            flags = await self._check(invoice, run)
            if not flags and self.scope == "flagged":
                return await self._pay(invoice, run, "passed every check")

            run.transition_to(PipelineState.LLM_PROCESSING)
            if self.models is None:
                return await self._to_a_person(invoice, run, ExceptionCategory.OTHER,
                                               "Flagged for review", "; ".join(flags), flags)
            verdict = await self._review(invoice, run, flags)
            if verdict is None:
                return await self._to_a_person(
                    invoice, run, ExceptionCategory.LLM_VALIDATION_FAILED, "No usable review",
                    "The models gave no readable verdict, or the daily spend cap was reached.", flags)
            if verdict.decision == "pay":
                return await self._pay(invoice, run, verdict.explanation)
            return await self._to_a_person(
                invoice, run, HOLD_CATEGORY.get(verdict.reason, ExceptionCategory.OTHER),
                f"Held: {verdict.explanation[:150]}", verdict.explanation, flags)
        except Exception as error:
            run.state = PipelineState.FAILED
            run.error_message = str(error)
            self.logger.error("Pipeline failed", invoice_id=str(invoice.id), error=str(error))
            raise

    async def _check(self, invoice: Invoice, run: InvoicePipelineRun) -> List[str]:
        """The rules, then the match against the PO and receipt; what they flag."""
        run.transition_to(PipelineState.VALIDATING)
        started = datetime.utcnow()
        rules = await RulesEngine(self.db, self.tenant_id, today=self.today).validate(invoice)
        run.validation_completed_at = datetime.utcnow()
        await self._audit(invoice, run, AuditStep.VALIDATION, {"invoice_number": invoice.invoice_number},
                          {"passed": rules.passed,
                           "violations": [{"type": v.rule_type.value, "message": v.message} for v in rules.violations]},
                          started)

        run.transition_to(PipelineState.MATCHING)
        started = datetime.utcnow()
        match = await MatchingEngine(self.db, self.tenant_id).match(invoice)
        run.matching_completed_at = datetime.utcnow()
        run.confidence_score = match.confidence
        await self._audit(invoice, run, AuditStep.MATCHING, {"po_number": invoice.po_number}, match.to_dict(), started)

        invoice.validation_errors = {"passed": rules.passed, "violations": [v.__dict__ for v in rules.violations]}
        invoice.match_result = match.to_dict()
        return describe(rules, match)

    async def _review(self, invoice: Invoice, run: InvoicePipelineRun, flags: List[str]) -> Optional[review.Verdict]:
        file = await case_file_for(self.db, self.tenant_id, invoice, today=self.today, flags=flags)
        text = review.prompt(file)
        first = await self._ask(routing.FIRST, text, invoice, run)
        if first is None or not self.second_opinion or \
                not routing.needs_second_opinion(first, invoice.total_amount or Decimal(0)):
            return first
        return await self._ask(routing.SECOND, text, invoice, run)

    async def _ask(self, model: str, text: str, invoice: Invoice, run: InvoicePipelineRun) -> Optional[review.Verdict]:
        """The model's verdict, or None if it gave none readable in two tries,
        could not be reached, or the day's budget is spent."""
        provider = self.models(model)
        for _ in range(ATTEMPTS):
            if await self.cost_service.get_daily_spend() >= settings.router_tenant_daily_cap:
                self.logger.warning("Daily model spend cap reached", invoice_id=str(invoice.id))
                return None
            started = datetime.utcnow()
            try:
                response = await provider.complete(text)
            except ClaudeCLIError as error:
                self.logger.error("Model call failed", model=model, error=str(error))
                return None
            await self.cost_service.record_llm_call(
                model_tier=TIERS[model], model_id=response.model_id, input_tokens=response.input_tokens,
                output_tokens=response.output_tokens, invoice_id=invoice.id, pipeline_run_id=run.id,
                cost_usd=response.cost_usd,
            )
            try:
                verdict = review.parse(response.content)
            except review.UnreadableVerdict as error:
                await self._audit(invoice, run, AuditStep.LLM_CALL, {"model": model},
                                  {"unreadable": str(error)}, started, model_id=response.model_id)
                continue
            await self._audit(invoice, run, AuditStep.LLM_CALL, {"model": model}, verdict.__dict__, started,
                              model_id=response.model_id)
            return verdict
        return None

    async def _pay(self, invoice: Invoice, run: InvoicePipelineRun, why: str) -> InvoicePipelineRun:
        run.transition_to(PipelineState.COMPLETED)
        run.final_decision = "approved"
        invoice.status = InvoiceStatus.APPROVED
        await self._audit(invoice, run, AuditStep.PIPELINE_COMPLETED, {"invoice_id": str(invoice.id)},
                          {"decision": "approved", "why": why}, datetime.utcnow())
        return run

    async def _to_a_person(self, invoice: Invoice, run: InvoicePipelineRun, category: ExceptionCategory,
                           title: str, description: str, flags: List[str]) -> InvoicePipelineRun:
        await self.exception_handler.create_exception(
            invoice=invoice, category=category, title=title[:200], description=description,
            details={"flags": flags}, severity=ExceptionSeverity.HIGH
            if category in (ExceptionCategory.DUPLICATE, ExceptionCategory.BANK_DETAILS) else None,
            pipeline_run_id=run.id,
        )
        run.transition_to(PipelineState.EXCEPTION)
        run.final_decision = "review"
        invoice.status = InvoiceStatus.EXCEPTION
        await self._audit(invoice, run, AuditStep.EXCEPTION_CREATED, {"category": category.value},
                          {"title": title}, datetime.utcnow())
        return run

    async def _audit(self, invoice, run, step, raw_input, raw_output, started, model_id=None):
        await self.audit_service.emit(
            invoice_id=invoice.id, pipeline_run_id=run.id, step=step, raw_input=raw_input,
            raw_output=raw_output, started_at=started, policy_version=self.POLICY_VERSION,
            prompt_version=self.PROMPT_VERSION, model_id=model_id,
        )
