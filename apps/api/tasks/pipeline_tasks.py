"""
Pipeline Celery tasks.
"""

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.tasks.celery_app import celery_app
from apps.api.models.base import async_session_maker
from apps.api.models.invoice import Invoice
from apps.api.services.pipeline_orchestrator import PipelineOrchestrator


def run_async(coro):
    """Run async function in Celery task."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def process_invoice_task(self, invoice_id: str, tenant_id: str):
    """Process a single invoice through the pipeline."""
    return run_async(_process_invoice(invoice_id, tenant_id))


async def _process_invoice(invoice_id: str, tenant_id: str):
    """Async implementation of invoice processing."""
    async with async_session_maker() as db:
        query = select(Invoice).where(Invoice.id == UUID(invoice_id))
        result = await db.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            return {"status": "error", "message": "Invoice not found"}
        
        orchestrator = PipelineOrchestrator(db, UUID(tenant_id))
        run = await orchestrator.run(invoice)
        
        await db.commit()
        
        return {
            "status": "success",
            "run_id": str(run.id),
            "final_state": run.state.value,
            "final_decision": run.final_decision,
        }


@celery_app.task(bind=True)
def process_batch_task(self, invoice_ids: list, tenant_id: str):
    """Process a batch of invoices."""
    results = []
    for invoice_id in invoice_ids:
        try:
            result = run_async(_process_invoice(invoice_id, tenant_id))
            results.append(result)
        except Exception as e:
            results.append({"status": "error", "invoice_id": invoice_id, "error": str(e)})
    
    return {
        "total": len(invoice_ids),
        "successful": sum(1 for r in results if r.get("status") == "success"),
        "failed": sum(1 for r in results if r.get("status") == "error"),
        "results": results,
    }
