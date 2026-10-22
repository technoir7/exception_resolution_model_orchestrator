"""
Pipeline execution routes.
"""

from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_tenant_context, TenantContext
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.pipeline import InvoicePipelineRun
from apps.api.schemas.pipeline import (
    PipelineRunRequest,
    PipelineRunResponse,
    BatchRunRequest,
    BatchRunResponse,
)
from apps.api.services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter()

# Statuses read back from the database are plain strings; InvoiceStatus is a
# str enum, so these compare equal either way.
PROCESSABLE = (InvoiceStatus.PENDING, InvoiceStatus.EXCEPTION)


@router.post("/run/{invoice_id}", response_model=PipelineRunResponse)
async def run_pipeline(
    invoice_id: UUID,
    request: PipelineRunRequest = None,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Run the reconciliation pipeline on a single invoice."""
    # Get invoice
    query = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.tenant_id == ctx.tenant_id,
    )
    result = await ctx.db.execute(query)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Check if already processed
    if request is None:
        request = PipelineRunRequest()
    
    if invoice.status not in PROCESSABLE and not request.force_reprocess:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice already processed with status {InvoiceStatus(invoice.status).value}. Use force_reprocess=true to reprocess.",
        )
    
    # Run pipeline
    orchestrator = PipelineOrchestrator(ctx.db, ctx.tenant_id)
    run = await orchestrator.run(invoice)
    
    await ctx.db.commit()
    await ctx.db.refresh(run)
    
    return PipelineRunResponse.model_validate(run)


@router.post("/run_batch", response_model=BatchRunResponse)
async def run_batch_pipeline(
    request: BatchRunRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Run the pipeline on multiple invoices."""
    # Verify all invoices exist
    query = select(Invoice).where(
        Invoice.id.in_(request.invoice_ids),
        Invoice.tenant_id == ctx.tenant_id,
    )
    result = await ctx.db.execute(query)
    invoices = {inv.id: inv for inv in result.scalars().all()}
    
    if len(invoices) != len(request.invoice_ids):
        missing = set(request.invoice_ids) - set(invoices.keys())
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoices not found: {missing}",
        )
    
    # Queue for processing
    queued = 0
    skipped = 0
    
    for invoice_id in request.invoice_ids:
        invoice = invoices[invoice_id]
        if invoice.status in PROCESSABLE or request.force_reprocess:
            queued += 1
            # In MVP, process synchronously (in prod, would queue to Celery)
            orchestrator = PipelineOrchestrator(ctx.db, ctx.tenant_id)
            await orchestrator.run(invoice)
        else:
            skipped += 1
    
    await ctx.db.commit()
    
    return BatchRunResponse(
        batch_id=uuid4(),
        total_invoices=len(request.invoice_ids),
        queued=queued,
        skipped=skipped,
        status="completed",
    )


@router.get("/runs/{invoice_id}", response_model=List[PipelineRunResponse])
async def get_pipeline_runs(
    invoice_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get all pipeline runs for an invoice."""
    query = (
        select(InvoicePipelineRun)
        .where(
            InvoicePipelineRun.invoice_id == invoice_id,
            InvoicePipelineRun.tenant_id == ctx.tenant_id,
        )
        .order_by(InvoicePipelineRun.created_at.desc())
    )
    result = await ctx.db.execute(query)
    runs = result.scalars().all()
    
    return [PipelineRunResponse.model_validate(run) for run in runs]
