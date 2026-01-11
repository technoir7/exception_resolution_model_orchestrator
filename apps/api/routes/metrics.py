"""
Cost metrics routes.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_tenant_context, TenantContext
from apps.api.models.cost import CostEvent, ModelTier
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.exception import ExceptionCase
from apps.api.schemas.cost import (
    CostDashboardResponse,
    CostByModelTierResponse,
    CostByExceptionTypeResponse,
    CacheMetricsResponse,
    DailyCostResponse,
)
from apps.api.services.cost_service import CostService

router = APIRouter()


@router.get("/cost", response_model=CostDashboardResponse)
async def get_cost_dashboard(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get cost dashboard with all metrics."""
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()
    
    cost_service = CostService(ctx.db, ctx.tenant_id)
    
    # Total cost
    cost_query = select(func.coalesce(func.sum(CostEvent.cost_usd), 0)).where(
        and_(
            CostEvent.tenant_id == ctx.tenant_id,
            func.date(CostEvent.event_timestamp) >= start_date,
            func.date(CostEvent.event_timestamp) <= end_date,
        )
    )
    total_cost = Decimal(str((await ctx.db.execute(cost_query)).scalar_one() or 0))
    
    # Invoice counts
    inv_query = select(func.count(Invoice.id)).where(
        and_(
            Invoice.tenant_id == ctx.tenant_id,
            func.date(Invoice.created_at) >= start_date,
            func.date(Invoice.created_at) <= end_date,
        )
    )
    total_invoices = (await ctx.db.execute(inv_query)).scalar_one() or 0
    
    approved_query = select(func.count(Invoice.id)).where(
        and_(
            Invoice.tenant_id == ctx.tenant_id,
            Invoice.status == InvoiceStatus.APPROVED,
            func.date(Invoice.created_at) >= start_date,
        )
    )
    touchless_count = (await ctx.db.execute(approved_query)).scalar_one() or 0
    
    exception_query = select(func.count(Invoice.id)).where(
        and_(
            Invoice.tenant_id == ctx.tenant_id,
            Invoice.status == InvoiceStatus.EXCEPTION,
            func.date(Invoice.created_at) >= start_date,
        )
    )
    exception_count = (await ctx.db.execute(exception_query)).scalar_one() or 0
    
    # Calculate averages
    avg_per_invoice = total_cost / total_invoices if total_invoices > 0 else Decimal("0")
    avg_per_verified = total_cost / touchless_count if touchless_count > 0 else Decimal("0")
    touchless_rate = touchless_count / total_invoices if total_invoices > 0 else 0.0
    
    # Cache metrics
    cache_metrics = await cost_service.get_cache_metrics(start_date, end_date)
    
    # Cost by model tier
    tier_query = select(
        CostEvent.model_tier,
        func.sum(CostEvent.cost_usd).label("total_cost"),
        func.count(CostEvent.id).label("call_count"),
        func.sum(CostEvent.total_tokens).label("total_tokens"),
    ).where(
        and_(
            CostEvent.tenant_id == ctx.tenant_id,
            func.date(CostEvent.event_timestamp) >= start_date,
            CostEvent.model_tier.isnot(None),
        )
    ).group_by(CostEvent.model_tier)
    
    tier_result = await ctx.db.execute(tier_query)
    cost_by_tier = []
    for row in tier_result.fetchall():
        if row.model_tier:
            avg_cost = Decimal(str(row.total_cost or 0)) / row.call_count if row.call_count else Decimal("0")
            cost_by_tier.append(CostByModelTierResponse(
                model_tier=row.model_tier,
                total_cost_usd=Decimal(str(row.total_cost or 0)),
                call_count=row.call_count or 0,
                total_tokens=row.total_tokens or 0,
                avg_cost_per_call=avg_cost,
            ))
    
    # Cost by exception type
    exc_cost_query = select(
        ExceptionCase.category,
        func.count(ExceptionCase.id).label("exc_count"),
    ).where(
        and_(
            ExceptionCase.tenant_id == ctx.tenant_id,
            func.date(ExceptionCase.created_at) >= start_date,
        )
    ).group_by(ExceptionCase.category)
    
    exc_result = await ctx.db.execute(exc_cost_query)
    cost_by_exc = []
    for row in exc_result.fetchall():
        cost_by_exc.append(CostByExceptionTypeResponse(
            category=row.category.value if row.category else "other",
            total_cost_usd=Decimal("0.05") * row.exc_count,  # Estimate
            exception_count=row.exc_count,
            avg_cost_per_exception=Decimal("0.05"),
        ))
    
    return CostDashboardResponse(
        total_cost_usd=total_cost,
        total_invoices_processed=total_invoices,
        avg_cost_per_invoice=avg_per_invoice,
        avg_cost_per_verified_invoice=avg_per_verified,
        touchless_count=touchless_count,
        exception_count=exception_count,
        touchless_rate=touchless_rate,
        cache_metrics=CacheMetricsResponse(
            total_requests=cache_metrics["total_requests"],
            cache_hits=cache_metrics["cache_hits"],
            cache_misses=cache_metrics["cache_misses"],
            hit_rate=cache_metrics["hit_rate"],
            total_savings_usd=Decimal("0"),
            avg_savings_per_hit=Decimal("0"),
        ),
        cost_by_model_tier=cost_by_tier,
        cost_by_exception_type=cost_by_exc,
        daily_costs=[],
        start_date=start_date,
        end_date=end_date,
    )
