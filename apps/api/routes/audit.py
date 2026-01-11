"""
Audit and replay routes.
"""

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_tenant_context, TenantContext
from apps.api.models.audit import AuditEvent
from apps.api.models.invoice import Invoice
from apps.api.models.pipeline import InvoicePipelineRun
from apps.api.schemas.audit import (
    AuditEventResponse,
    AuditTimelineResponse,
    ReplayRequest,
    ReplayResponse,
    DriftReport,
    Drift,
)
from apps.api.schemas.pipeline import PipelineRunResponse
from apps.api.services.audit_service import AuditService
from apps.api.services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter()


@router.get("/{invoice_id}", response_model=AuditTimelineResponse)
async def get_audit_timeline(
    invoice_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get full audit timeline for an invoice."""
    # Verify invoice exists
    inv_query = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.tenant_id == ctx.tenant_id,
    )
    result = await ctx.db.execute(inv_query)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Get audit events
    audit_service = AuditService(ctx.db, ctx.tenant_id)
    events = await audit_service.get_timeline(invoice_id)
    
    # Calculate duration
    total_duration = sum(e.duration_ms for e in events)
    first_event = events[0] if events else None
    last_event = events[-1] if events else None
    
    return AuditTimelineResponse(
        invoice_id=invoice_id,
        events=[AuditEventResponse.model_validate(e) for e in events],
        total_events=len(events),
        first_event_at=first_event.started_at if first_event else None,
        last_event_at=last_event.completed_at if last_event else None,
        total_duration_ms=total_duration,
    )


@router.post("/replay/{invoice_id}/{run_id}", response_model=ReplayResponse)
async def replay_pipeline(
    invoice_id: UUID,
    run_id: UUID,
    request: ReplayRequest = None,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Replay a pipeline run and detect drift."""
    if request is None:
        request = ReplayRequest()
    
    # Get original run
    run_query = select(InvoicePipelineRun).where(
        InvoicePipelineRun.id == run_id,
        InvoicePipelineRun.invoice_id == invoice_id,
        InvoicePipelineRun.tenant_id == ctx.tenant_id,
    )
    result = await ctx.db.execute(run_query)
    original_run = result.scalar_one_or_none()
    
    if not original_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline run not found",
        )
    
    # Get invoice
    inv_query = select(Invoice).where(Invoice.id == invoice_id)
    result = await ctx.db.execute(inv_query)
    invoice = result.scalar_one_or_none()
    
    # Get original audit events
    audit_service = AuditService(ctx.db, ctx.tenant_id)
    original_events = await audit_service.get_run_events(run_id)
    
    # Run replay
    orchestrator = PipelineOrchestrator(ctx.db, ctx.tenant_id)
    replay_run = await orchestrator.run(
        invoice,
        is_replay=True,
        original_run_id=run_id,
    )
    
    await ctx.db.commit()
    
    # Get replay events
    replay_events = await audit_service.get_run_events(replay_run.id)
    
    # Compare for drift
    drifts = []
    matching_steps = 0
    
    for orig, replay in zip(original_events, replay_events):
        matches, diff = audit_service.compare_outputs(orig, replay)
        if matches:
            matching_steps += 1
        else:
            drifts.append(Drift(
                step=orig.step,
                sequence_number=orig.sequence_number,
                original_output_hash=orig.output_hash,
                replay_output_hash=replay.output_hash,
                original_output=orig.raw_output if request.compare_outputs else None,
                replay_output=replay.raw_output if request.compare_outputs else None,
                description=f"Output changed at step {orig.step.value}",
            ))
    
    drift_report = DriftReport(
        original_run_id=run_id,
        replay_run_id=replay_run.id,
        has_drift=len(drifts) > 0,
        drifts=drifts,
        total_steps=len(original_events),
        matching_steps=matching_steps,
        drifting_steps=len(drifts),
        original_policy_version=original_run.policy_version,
        replay_policy_version=replay_run.policy_version,
        comparison_timestamp=datetime.utcnow(),
    )
    
    return ReplayResponse(
        replay_run=PipelineRunResponse.model_validate(replay_run),
        drift_report=drift_report,
    )
