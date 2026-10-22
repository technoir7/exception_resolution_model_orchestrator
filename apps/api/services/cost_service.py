"""
Cost Service for tracking and aggregating LLM costs.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import Integer, select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.cost import CostEvent, CostEventType, ModelTier
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.config import settings

logger = structlog.get_logger()


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


class CostService:
    """Service for tracking and aggregating LLM costs."""
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
        
        self.tier_costs = {
            ModelTier.TIER_A: settings.tier_a_cost_per_1k,
            ModelTier.TIER_B: settings.tier_b_cost_per_1k,
            ModelTier.TIER_C: settings.tier_c_cost_per_1k,
        }
    
    async def record_llm_call(
        self,
        model_tier: ModelTier,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        invoice_id: Optional[UUID] = None,
        pipeline_run_id: Optional[UUID] = None,
        was_cache_hit: bool = False,
        cache_key: Optional[str] = None,
        batch_id: Optional[UUID] = None,
        cost_usd: Optional[Decimal] = None,
    ) -> CostEvent:
        """Record an LLM call cost event: at `cost_usd` where the provider
        reported what the call cost, else at the tier's configured rate."""
        total_tokens = input_tokens + output_tokens
        cost_per_1k = self.tier_costs.get(model_tier, Decimal("0.001"))
        
        if was_cache_hit:
            cost_usd = Decimal("0")
        elif cost_usd is None:
            cost_usd = (Decimal(total_tokens) / 1000) * cost_per_1k
        
        if batch_id:
            cost_usd *= Decimal("0.5")  # 50% batch discount
        
        event = CostEvent(
            tenant_id=self.tenant_id,
            invoice_id=invoice_id,
            pipeline_run_id=pipeline_run_id,
            event_type=CostEventType.CACHE_HIT if was_cache_hit else CostEventType.LLM_CALL,
            model_tier=model_tier,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            cache_key=cache_key,
            was_cache_hit=was_cache_hit,
            batch_id=batch_id,
            batch_discount_percent=Decimal("50") if batch_id else None,
            event_timestamp=datetime.utcnow(),
        )
        
        self.db.add(event)
        return event

    async def record_manual_review_cost(
        self,
        invoice_id: UUID,
        pipeline_run_id: Optional[UUID] = None,
        cost_usd: Decimal = Decimal("5.00"),
        reviewer_id: Optional[UUID] = None,
    ) -> CostEvent:
        """Record a manual review cost event."""
        event = CostEvent(
            tenant_id=self.tenant_id,
            invoice_id=invoice_id,
            pipeline_run_id=pipeline_run_id,
            event_type=CostEventType.MANUAL_REVIEW,
            cost_usd=cost_usd,
            event_timestamp=datetime.utcnow(),
            event_metadata={"reviewer_id": str(reviewer_id)} if reviewer_id else None,
        )
        
        self.db.add(event)
        return event
    
    async def get_cost_per_invoice(self, invoice_id: UUID) -> Decimal:
        """Get total cost for a specific invoice."""
        query = select(func.coalesce(func.sum(CostEvent.cost_usd), 0)).where(
            and_(
                CostEvent.tenant_id == self.tenant_id,
                CostEvent.invoice_id == invoice_id,
            )
        )
        result = await self.db.execute(query)
        return Decimal(str(result.scalar_one() or 0))
    
    async def get_avg_cost_per_verified_invoice(
        self, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> Decimal:
        """Get average cost per verified (approved) invoice."""
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()
        
        # Get verified invoices
        invoice_query = select(Invoice.id).where(
            and_(
                Invoice.tenant_id == self.tenant_id,
                Invoice.status == InvoiceStatus.APPROVED,
                func.date(Invoice.created_at) >= start_date,
                func.date(Invoice.created_at) <= end_date,
            )
        )
        invoice_result = await self.db.execute(invoice_query)
        invoice_ids = [r[0] for r in invoice_result.fetchall()]
        
        if not invoice_ids:
            return Decimal("0")
        
        # Get total cost for those invoices
        cost_query = select(func.coalesce(func.sum(CostEvent.cost_usd), 0)).where(
            CostEvent.invoice_id.in_(invoice_ids)
        )
        cost_result = await self.db.execute(cost_query)
        total_cost = Decimal(str(cost_result.scalar_one() or 0))
        
        return total_cost / len(invoice_ids)
    
    async def get_daily_spend(self) -> Decimal:
        """Today's total spend. Calls are stamped in UTC, so the day is too."""
        query = select(func.coalesce(func.sum(CostEvent.cost_usd), 0)).where(
            and_(
                CostEvent.tenant_id == self.tenant_id,
                func.date(CostEvent.event_timestamp) == utc_today(),
            )
        )
        result = await self.db.execute(query)
        return Decimal(str(result.scalar_one() or 0))
