"""
Replay Service for offline evaluation of routing policies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.cost import CostEvent
from apps.api.models.invoice import Invoice
from apps.api.models.pipeline import InvoicePipelineRun, PipelineState
from apps.api.services.cost_service import CostService
from apps.api.services.llm_router import LLMRouter
from apps.api.services.pipeline_orchestrator import PipelineOrchestrator
from apps.api.services.audit_service import AuditService

logger = structlog.get_logger()


@dataclass
class ReplayConfig:
    """Configuration for a replay run."""
    router_tier_a_confidence: float = 0.9
    router_tier_b_confidence: float = 0.7
    high_risk_amount: Decimal = Decimal("1000.00")
    use_mock_llm: bool = True
    mock_failure_rate: float = 0.0


@dataclass
class ReplayResult:
    """Result of a single invoice replay."""
    invoice_id: UUID
    original_run_id: Optional[UUID]
    replay_run_id: UUID
    status: str
    final_decision: str
    total_cost: Decimal
    execution_time_ms: int
    router_decisions: List[Dict[str, Any]] = field(default_factory=list)
    drift_detected: bool = False


class ReplayHarness:
    """
    Harness for running pipeline replays with different configurations.
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(service="replay_harness", tenant_id=str(tenant_id))

    async def run_replay(
        self,
        invoice_ids: List[UUID],
        config: ReplayConfig,
    ) -> List[ReplayResult]:
        """Run replay for a list of invoices."""
        results = []
        
        # Configure a custom router based on config
        # Note: In a real implementation, we would subclass LLMRouter or inject settings
        # For now, we assume we can modify the router instance or pass a configured one
        
        for invoice_id in invoice_ids:
            try:
                result = await self._replay_invoice(invoice_id, config)
                results.append(result)
            except Exception as e:
                self.logger.error("Replay failed", invoice_id=str(invoice_id), error=str(e))
                # Add failure result
                # ...
        
        return results

    async def _replay_invoice(self, invoice_id: UUID, config: ReplayConfig) -> ReplayResult:
        """Replay a single invoice."""
        start_time = datetime.utcnow()
        
        # Fetch invoice
        query = select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == self.tenant_id
        )
        result = await self.db.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        
        # Find original run if exists
        run_query = select(InvoicePipelineRun).where(
            InvoicePipelineRun.invoice_id == invoice_id,
            InvoicePipelineRun.is_replay == False
        ).order_by(InvoicePipelineRun.created_at.desc()).limit(1)
        run_result = await self.db.execute(run_query)
        original_run = run_result.scalar_one_or_none()
        
        # Setup specific services for replay
        # 1. Custom Router with config overrides
        router = LLMRouter(self.db, self.tenant_id)
        router.tier_a_threshold = config.router_tier_a_confidence
        router.tier_b_threshold = config.router_tier_b_confidence
        router.high_risk_amount = config.high_risk_amount
        
        # 2. Replay-specific CostService (to avoid polluting production stats? 
        # Actually we might want to track replay costs separately)
        # For MVP, we use standard cost service but rely on the 'is_replay' flag in pipeline run
        
        # 3. Orchestrator with injected router
        orchestrator = PipelineOrchestrator(
            db=self.db,
            tenant_id=self.tenant_id,
            llm_router=router,
            # We use default verification/rules engines
        )
        
        # Run pipeline
        # is_replay=True ensures we flag this run
        run = await orchestrator.run(
            invoice, 
            is_replay=True,
            original_run_id=original_run.id if original_run else None
        )
        
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        # Calculate cost for this run
        cost_service = CostService(self.db, self.tenant_id)
        # We need a method to get cost for a specific RUN, not just invoice
        # Assuming we key cost events by pipeline_run_id
        # We'll need to extend CostService for this, but for now let's query raw
        cost_query = select(CostEvent).where(
            CostEvent.pipeline_run_id == run.id
        )
        cost_result = await self.db.execute(cost_query)
        cost_events = cost_result.scalars().all()
        total_cost = sum(e.cost_usd for e in cost_events)
        
        return ReplayResult(
            invoice_id=invoice.id,
            original_run_id=original_run.id if original_run else None,
            replay_run_id=run.id,
            status=run.state.value,
            final_decision=run.final_decision or "unknown",
            total_cost=total_cost,
            execution_time_ms=duration_ms,
            drift_detected=False, # TODO: Implement drift check
        )
