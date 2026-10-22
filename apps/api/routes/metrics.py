"""
Model spend: over a period, and for one invoice.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from apps.api.config import settings
from apps.api.dependencies import TenantContext, get_tenant_context
from apps.api.models.cost import CostEvent
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.schemas.cost import CostDashboardResponse, InvoiceCostResponse, ModelCall, ModelSpend
from apps.api.services.cost_service import CostService, utc_today

router = APIRouter()


@router.get("/cost", response_model=CostDashboardResponse)
async def get_cost_dashboard(
    start_date: Optional[date] = Query(None, description="Default: 30 days before end_date"),
    end_date: Optional[date] = Query(None, description="Default: today, in UTC"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Model spend over a period, by model, against the invoices received in
    it. The spend includes calls for PDFs refused at intake."""
    end_date = end_date or utc_today()
    start_date = start_date or end_date - timedelta(days=30)

    def in_period(column):
        return and_(func.date(column) >= start_date, func.date(column) <= end_date)

    rows = (await ctx.db.execute(
        select(CostEvent.model_id, func.count(CostEvent.id), func.sum(CostEvent.input_tokens),
               func.sum(CostEvent.output_tokens), func.sum(CostEvent.cost_usd))
        .where(CostEvent.tenant_id == ctx.tenant_id, in_period(CostEvent.event_timestamp))
        .group_by(CostEvent.model_id)
    )).all()
    by_model = sorted(
        (ModelSpend(model_id=model, calls=calls, input_tokens=inputs or 0, output_tokens=outputs or 0,
                    cost_usd=Decimal(str(cost or 0))) for model, calls, inputs, outputs, cost in rows),
        key=lambda m: m.cost_usd, reverse=True)
    total = sum((m.cost_usd for m in by_model), Decimal(0))

    statuses = (await ctx.db.execute(
        select(Invoice.status, func.count(Invoice.id))
        .where(Invoice.tenant_id == ctx.tenant_id, in_period(Invoice.created_at))
        .group_by(Invoice.status)
    )).all()
    by_status = {InvoiceStatus(s).value: n for s, n in statuses}
    invoices = sum(by_status.values())

    return CostDashboardResponse(
        start_date=start_date,
        end_date=end_date,
        total_cost_usd=total,
        invoices_by_status=by_status,
        cost_per_invoice=total / invoices if invoices else Decimal(0),
        spent_today=await CostService(ctx.db, ctx.tenant_id).get_daily_spend(),
        daily_cap_usd=settings.router_tenant_daily_cap,
        by_model=by_model,
    )


@router.get("/cost/invoices/{invoice_id}", response_model=InvoiceCostResponse)
async def get_invoice_cost(
    invoice_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """What reading and reviewing one invoice cost, call by call."""
    found = await ctx.db.scalar(
        select(Invoice.id).where(Invoice.id == invoice_id, Invoice.tenant_id == ctx.tenant_id))
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    events = (await ctx.db.execute(
        select(CostEvent)
        .where(CostEvent.tenant_id == ctx.tenant_id, CostEvent.invoice_id == invoice_id)
        .order_by(CostEvent.event_timestamp)
    )).scalars().all()
    return InvoiceCostResponse(
        invoice_id=invoice_id,
        total_cost_usd=sum((e.cost_usd for e in events), Decimal(0)),
        calls=[ModelCall(model_id=e.model_id, input_tokens=e.input_tokens, output_tokens=e.output_tokens,
                         cost_usd=e.cost_usd, at=e.event_timestamp) for e in events],
    )
