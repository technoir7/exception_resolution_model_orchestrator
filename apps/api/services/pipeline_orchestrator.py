"""
Pipeline Orchestrator - State machine for invoice processing.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.audit import AuditStep
from apps.api.models.cost import ModelTier
from apps.api.models.exception import ExceptionCategory, ExceptionSeverity
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.pipeline import InvoicePipelineRun, PipelineState
from apps.api.services.audit_service import AuditService
from apps.api.services.cache_service import CacheService
from apps.api.services.cost_service import CostService
from apps.api.services.exception_handler import ExceptionHandler
from apps.api.services.llm_router import LLMRouter, RouterContext
from apps.api.services.matching_engine import MatchingEngine, MatchStatus
from apps.api.services.rules_engine import RulesEngine
from apps.api.services.verification import VerificationService

logger = structlog.get_logger()


class PipelineOrchestrator:
    """Orchestrates the invoice processing pipeline."""
    
    POLICY_VERSION = "v1"
    PROMPT_VERSION = "v1"
    
    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        rules_engine: Optional[RulesEngine] = None,
        matching_engine: Optional[MatchingEngine] = None,
        llm_router: Optional[LLMRouter] = None,
        verification_service: Optional[VerificationService] = None,
        exception_handler: Optional[ExceptionHandler] = None,
        audit_service: Optional[AuditService] = None,
        cost_service: Optional[CostService] = None,
        cache_service: Optional[CacheService] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
        
        # Initialize services or use injected ones
        self.rules_engine = rules_engine or RulesEngine(db, tenant_id)
        self.matching_engine = matching_engine or MatchingEngine(db, tenant_id)
        self.llm_router = llm_router or LLMRouter(db, tenant_id)
        self.verification = verification_service or VerificationService(tenant_id)
        self.exception_handler = exception_handler or ExceptionHandler(db, tenant_id)
        self.audit_service = audit_service or AuditService(db, tenant_id)
        self.cost_service = cost_service or CostService(db, tenant_id)
        self.cache_service = cache_service or CacheService(db, tenant_id)
    
    async def run(
        self,
        invoice: Invoice,
        is_replay: bool = False,
        original_run_id: Optional[UUID] = None,
    ) -> InvoicePipelineRun:
        """Run the full pipeline on an invoice."""
        
        # Create pipeline run
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
        
        self.logger.info("Pipeline started", invoice_id=str(invoice.id), run_id=str(run.id))
        
        try:
            # Step 1: Validation
            await self._step_validation(invoice, run)
            if run.state == PipelineState.EXCEPTION:
                return run
            
            # Step 2: Matching
            await self._step_matching(invoice, run)
            if run.state == PipelineState.EXCEPTION:
                return run
            
            # Step 3: LLM Processing (if needed)
            await self._step_llm_processing(invoice, run)
            if run.state == PipelineState.EXCEPTION:
                return run
            
            # Step 4: Verification
            await self._step_verification(invoice, run)
            if run.state == PipelineState.EXCEPTION:
                return run
            
            # Complete
            run.transition_to(PipelineState.COMPLETED)
            run.final_decision = "approved"
            invoice.status = InvoiceStatus.APPROVED
            
            await self.audit_service.emit(
                invoice_id=invoice.id,
                pipeline_run_id=run.id,
                step=AuditStep.PIPELINE_COMPLETED,
                raw_input={"invoice_id": str(invoice.id)},
                raw_output={"decision": "approved", "confidence": run.confidence_score},
                started_at=datetime.utcnow(),
                policy_version=self.POLICY_VERSION,
            )
            
            self.logger.info("Pipeline completed", invoice_id=str(invoice.id), decision="approved")
            
        except Exception as e:
            run.state = PipelineState.FAILED
            run.error_message = str(e)
            self.logger.error("Pipeline failed", invoice_id=str(invoice.id), error=str(e))
            raise
        
        return run
    
    async def _step_validation(self, invoice: Invoice, run: InvoicePipelineRun) -> None:
        """Run validation rules."""
        started_at = datetime.utcnow()
        run.transition_to(PipelineState.VALIDATING)
        run.validation_started_at = started_at
        
        result = await self.rules_engine.validate(invoice)
        
        run.validation_completed_at = datetime.utcnow()
        
        # Emit audit event
        await self.audit_service.emit(
            invoice_id=invoice.id,
            pipeline_run_id=run.id,
            step=AuditStep.VALIDATION,
            raw_input={"invoice_number": invoice.invoice_number, "po_number": invoice.po_number},
            raw_output={
                "passed": result.passed,
                "violation_count": len(result.violations),
                "violations": [{"type": v.rule_type.value, "message": v.message} for v in result.violations],
            },
            started_at=started_at,
            policy_version=self.POLICY_VERSION,
        )
        
        if not result.passed:
            # Create exception for first high-severity violation
            high_violations = [v for v in result.violations if v.severity == "high"]
            if high_violations:
                await self.exception_handler.create_from_violation(
                    invoice, high_violations[0], run.id
                )
                run.transition_to(PipelineState.EXCEPTION)
                run.final_decision = "exception"
                
                await self.audit_service.emit(
                    invoice_id=invoice.id,
                    pipeline_run_id=run.id,
                    step=AuditStep.EXCEPTION_CREATED,
                    raw_input={"violation_type": high_violations[0].rule_type.value},
                    raw_output={"reason": high_violations[0].message},
                    started_at=datetime.utcnow(),
                    policy_version=self.POLICY_VERSION,
                )
        
        invoice.validation_errors = {
            "passed": result.passed,
            "violations": [v.__dict__ for v in result.violations],
        }
    
    async def _step_matching(self, invoice: Invoice, run: InvoicePipelineRun) -> None:
        """Run matching engine."""
        started_at = datetime.utcnow()
        run.transition_to(PipelineState.MATCHING)
        run.matching_started_at = started_at
        
        result = await self.matching_engine.match(invoice)
        
        run.matching_completed_at = datetime.utcnow()
        run.confidence_score = result.confidence
        
        # Emit audit event
        await self.audit_service.emit(
            invoice_id=invoice.id,
            pipeline_run_id=run.id,
            step=AuditStep.MATCHING,
            raw_input={"po_number": invoice.po_number, "total_amount": str(invoice.total_amount)},
            raw_output=result.to_dict(),
            started_at=started_at,
            policy_version=self.POLICY_VERSION,
        )
        
        invoice.match_result = result.to_dict()
        
        # Create exception for no match or partial match with low confidence
        if result.status == MatchStatus.NO_MATCH:
            await self.exception_handler.create_exception(
                invoice=invoice,
                category=ExceptionCategory.MISSING_PO,
                title="No matching PO found",
                description=result.summary,
                pipeline_run_id=run.id,
            )
            run.transition_to(PipelineState.EXCEPTION)
            run.final_decision = "exception"
    
    async def _step_llm_processing(self, invoice: Invoice, run: InvoicePipelineRun) -> None:
        """Run LLM analysis."""
        started_at = datetime.utcnow()
        run.transition_to(PipelineState.LLM_PROCESSING)
        run.llm_started_at = started_at
        
        # Check cache first
        normalized_input = {
            "invoice_number": invoice.invoice_number,
            "vendor_id": invoice.vendor_id,
            "total_amount": str(invoice.total_amount),
            "match_result": invoice.match_result,
        }
        
        cached = await self.cache_service.get(
            normalized_input,
            self.POLICY_VERSION,
            self.PROMPT_VERSION,
            "mock-gpt-*",
        )
        
        if cached:
            llm_output = cached
            was_cache_hit = True
            model_tier = ModelTier.TIER_A
            model_id = cached.get("model", "cached")
        else:
            # Route and call LLM
            context = RouterContext(
                tenant_id=self.tenant_id,
                invoice_id=invoice.id,
                invoice_amount=invoice.total_amount or Decimal("0"),
                confidence_score=run.confidence_score or 0.5,
            )
            
            prompt = self._build_analysis_prompt(invoice)
            response, decision = await self.llm_router.call_with_retry(context, prompt)
            
            llm_output = response.parsed_json or {}
            was_cache_hit = False
            model_tier = decision.tier
            model_id = decision.model_id
            
            # Cache the result
            await self.cache_service.set(
                normalized_input,
                llm_output,
                self.POLICY_VERSION,
                self.PROMPT_VERSION,
                model_id,
                float(response.total_tokens * Decimal("0.001")),
            )
        
        run.llm_completed_at = datetime.utcnow()
        
        # Record cost
        await self.cost_service.record_llm_call(
            model_tier=model_tier,
            model_id=model_id,
            input_tokens=150,
            output_tokens=100,
            invoice_id=invoice.id,
            pipeline_run_id=run.id,
            was_cache_hit=was_cache_hit,
        )
        
        # Emit audit event
        await self.audit_service.emit(
            invoice_id=invoice.id,
            pipeline_run_id=run.id,
            step=AuditStep.LLM_CALL,
            raw_input=normalized_input,
            raw_output=llm_output,
            started_at=started_at,
            policy_version=self.POLICY_VERSION,
            prompt_version=self.PROMPT_VERSION,
            model_id=model_id,
        )
        
        # Update confidence from LLM
        if "confidence" in llm_output:
            run.confidence_score = llm_output["confidence"]
        
        # Check LLM decision
        if llm_output.get("decision") == "reject":
            await self.exception_handler.create_exception(
                invoice=invoice,
                category=ExceptionCategory.DUPLICATE if "duplicate" in llm_output.get("reasoning", "").lower() else ExceptionCategory.OTHER,
                title=f"LLM rejected: {llm_output.get('reasoning', 'Unknown reason')[:100]}",
                description=llm_output.get("reasoning"),
                details=llm_output,
                severity=ExceptionSeverity.HIGH,
                pipeline_run_id=run.id,
            )
            run.transition_to(PipelineState.EXCEPTION)
            run.final_decision = "rejected"
        elif llm_output.get("requires_review"):
            await self.exception_handler.create_exception(
                invoice=invoice,
                category=self._categorize_llm_exception(llm_output),
                title=f"Review required: {llm_output.get('reasoning', 'Manual review needed')[:100]}",
                description=llm_output.get("reasoning"),
                details=llm_output,
                pipeline_run_id=run.id,
            )
            run.transition_to(PipelineState.EXCEPTION)
            run.final_decision = "review"
    
    async def _step_verification(self, invoice: Invoice, run: InvoicePipelineRun) -> None:
        """Run verification checks."""
        started_at = datetime.utcnow()
        run.transition_to(PipelineState.VERIFYING)
        run.verification_started_at = started_at
        
        # Get LLM output from match result
        llm_output = invoice.match_result or {}
        invoice_data = {
            "subtotal": str(invoice.subtotal) if invoice.subtotal else None,
            "total_amount": str(invoice.total_amount) if invoice.total_amount else None,
            "currency": invoice.currency,
            "line_items": invoice.line_items,
        }
        
        result = self.verification.verify_llm_response(llm_output, invoice_data=invoice_data)
        
        run.verification_completed_at = datetime.utcnow()
        
        # Emit audit event
        await self.audit_service.emit(
            invoice_id=invoice.id,
            pipeline_run_id=run.id,
            step=AuditStep.VERIFICATION,
            raw_input={"llm_output": llm_output, "invoice_data": invoice_data},
            raw_output=result.to_dict(),
            started_at=started_at,
            policy_version=self.POLICY_VERSION,
        )
        
        if not result.valid:
            await self.exception_handler.create_exception(
                invoice=invoice,
                category=ExceptionCategory.LLM_VALIDATION_FAILED,
                title="Verification failed",
                description="; ".join(e.message for e in result.errors),
                details={"errors": [e.__dict__ for e in result.errors]},
                severity=ExceptionSeverity.HIGH,
                pipeline_run_id=run.id,
            )
            run.transition_to(PipelineState.EXCEPTION)
            run.final_decision = "verification_failed"
    
    def _build_analysis_prompt(self, invoice: Invoice) -> str:
        """Build the analysis prompt for LLM."""
        return f"""Analyze this invoice for accounts payable processing:

Invoice Number: {invoice.invoice_number}
Vendor: {invoice.vendor_name} ({invoice.vendor_id})
Date: {invoice.invoice_date}
PO Number: {invoice.po_number}
Total Amount: {invoice.currency} {invoice.total_amount}

Match Result: {invoice.match_result}

Determine if this invoice should be:
1. APPROVED - All matches verified, within tolerance
2. REJECTED - Clear issues (duplicate, fraud indicators)
3. REVIEW - Needs human review (variances, missing info)

Respond with JSON containing: decision, confidence, reasoning, variances, requires_review"""

    def _categorize_llm_exception(self, llm_output: Dict[str, Any]) -> ExceptionCategory:
        """Categorize exception based on LLM output."""
        variances = llm_output.get("variances", [])
        reasoning = llm_output.get("reasoning", "").lower()
        
        for var in variances:
            var_type = var.get("type", "")
            if var_type == "amount":
                return ExceptionCategory.AMOUNT_VARIANCE
            elif var_type == "quantity":
                return ExceptionCategory.QUANTITY_VARIANCE
            elif var_type == "vendor":
                return ExceptionCategory.VENDOR_MISMATCH
        
        if "duplicate" in reasoning:
            return ExceptionCategory.DUPLICATE
        elif "po" in reasoning and "missing" in reasoning:
            return ExceptionCategory.MISSING_PO
        
        return ExceptionCategory.OTHER
