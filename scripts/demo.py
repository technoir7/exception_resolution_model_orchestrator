#!/usr/bin/env python
"""
End-to-end demo script that:
1. Seeds fixtures
2. Ingests 10 invoice fixtures
3. Runs the pipeline on each
4. Prints summary metrics
"""

import asyncio
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID
import hashlib

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.models.base import async_session_maker, init_db
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.exception import ExceptionCase
from apps.api.models.cost import CostEvent
from apps.api.models.pipeline import InvoicePipelineRun, PipelineState
from apps.api.services.pipeline_orchestrator import PipelineOrchestrator
from sqlalchemy import select, func

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
INVOICES_DIR = FIXTURES_DIR / "invoices"
TENANT_ID = UUID("00000000-0000-0000-0000-000000000100")


async def ingest_invoices():
    """Ingest all invoice fixtures."""
    print("\n📄 Ingesting invoices...")
    invoices = []
    
    async with async_session_maker() as db:
        # Get all invoice fixture files
        invoice_files = sorted(INVOICES_DIR.glob("invoice_*.json"))
        
        for invoice_file in invoice_files:
            with open(invoice_file) as f:
                data = json.load(f)
            
            # Compute document hash
            content = json.dumps(data, sort_keys=True)
            doc_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Create invoice
            invoice = Invoice(
                tenant_id=TENANT_ID,
                document_content=content,
                document_hash=doc_hash,
                document_type="json",
                original_filename=invoice_file.name,
                status=InvoiceStatus.PENDING,
                invoice_number=data["invoice_number"],
                invoice_date=datetime.strptime(data["invoice_date"], "%Y-%m-%d").date(),
                due_date=datetime.strptime(data["due_date"], "%Y-%m-%d").date() if data.get("due_date") else None,
                vendor_id=data["vendor_id"],
                vendor_name=data["vendor_name"],
                po_number=data.get("po_number"),
                currency=data.get("currency", "USD"),
                subtotal=Decimal(data["subtotal"]),
                tax_amount=Decimal(data.get("tax_amount", "0")),
                total_amount=Decimal(data["total_amount"]),
                line_items=data.get("line_items", []),
            )
            
            db.add(invoice)
            await db.flush()
            invoices.append(invoice)
            
            fixture_type = data.get("_fixture_type", "unknown")
            print(f"  ✓ {invoice_file.name} ({fixture_type})")
        
        await db.commit()
    
    print(f"\n  Total: {len(invoices)} invoices ingested")
    return invoices


async def run_pipeline_on_all():
    """Run the pipeline on all pending invoices."""
    print("\n⚙️  Running pipeline...")
    
    results = {"approved": 0, "exception": 0, "failed": 0}
    
    async with async_session_maker() as db:
        # Get all pending invoices
        result = await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == TENANT_ID,
                Invoice.status == InvoiceStatus.PENDING,
            )
        )
        invoices = result.scalars().all()
        
        orchestrator = PipelineOrchestrator(db, TENANT_ID)
        
        for invoice in invoices:
            try:
                run = await orchestrator.run(invoice)
                await db.commit()
                
                if run.state == PipelineState.COMPLETED:
                    results["approved"] += 1
                    status_icon = "✅"
                elif run.state == PipelineState.EXCEPTION:
                    results["exception"] += 1
                    status_icon = "⚠️"
                else:
                    results["failed"] += 1
                    status_icon = "❌"
                
                print(f"  {status_icon} {invoice.invoice_number}: {run.state.value}")
                
            except Exception as e:
                results["failed"] += 1
                print(f"  ❌ {invoice.invoice_number}: ERROR - {str(e)[:50]}")
    
    return results


async def get_exception_stats():
    """Get exception statistics."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ExceptionCase.category, func.count(ExceptionCase.id))
            .where(ExceptionCase.tenant_id == TENANT_ID)
            .group_by(ExceptionCase.category)
        )
        return {row[0].value: row[1] for row in result.fetchall()}


async def get_cost_stats():
    """Get cost statistics."""
    async with async_session_maker() as db:
        # Total cost
        result = await db.execute(
            select(func.sum(CostEvent.cost_usd))
            .where(CostEvent.tenant_id == TENANT_ID)
        )
        total_cost = result.scalar_one() or Decimal("0")
        
        # Cache hits
        result = await db.execute(
            select(func.count(CostEvent.id))
            .where(CostEvent.tenant_id == TENANT_ID, CostEvent.was_cache_hit == True)
        )
        cache_hits = result.scalar_one() or 0
        
        # Total calls
        result = await db.execute(
            select(func.count(CostEvent.id))
            .where(CostEvent.tenant_id == TENANT_ID)
        )
        total_calls = result.scalar_one() or 0
        
        return {
            "total_cost": total_cost,
            "cache_hits": cache_hits,
            "total_calls": total_calls,
            "cache_hit_rate": cache_hits / total_calls if total_calls > 0 else 0,
        }


async def print_summary(pipeline_results):
    """Print summary metrics."""
    total = sum(pipeline_results.values())
    touchless = pipeline_results["approved"]
    exceptions = pipeline_results["exception"]
    
    exception_stats = await get_exception_stats()
    cost_stats = await get_cost_stats()
    
    avg_cost = cost_stats["total_cost"] / total if total > 0 else Decimal("0")
    
    print("\n" + "=" * 60)
    print("         AP RECONCILIATION DEMO RESULTS")
    print("=" * 60)
    
    print(f"""
📊 Processing Summary
   ─────────────────────────────────────
   Total Invoices Processed:  {total}
   Touchless (Approved):      {touchless} ({touchless/total*100:.0f}%)
   Exceptions:                {exceptions} ({exceptions/total*100:.0f}%)
   Failed:                    {pipeline_results['failed']}

💰 Cost Metrics
   ─────────────────────────────────────
   Total LLM Cost:            ${cost_stats['total_cost']:.4f}
   Avg Cost per Invoice:      ${avg_cost:.4f}
   Cache Hit Rate:            {cost_stats['cache_hit_rate']*100:.0f}%
""")
    
    if exception_stats:
        print("⚠️  Exception Breakdown")
        print("   ─────────────────────────────────────")
        for exc_type, count in sorted(exception_stats.items(), key=lambda x: -x[1]):
            print(f"   {exc_type:25} {count}")
    
    print("\n" + "=" * 60)
    print("   Touchless Rate:  {:.0f}%".format(touchless/total*100 if total else 0))
    print("   Exception Rate:  {:.0f}%".format(exceptions/total*100 if total else 0))
    print("=" * 60 + "\n")


async def main():
    """Run the full demo."""
    print("\n" + "=" * 60)
    print("     AP RECONCILIATION ORCHESTRATOR - DEMO")
    print("=" * 60)
    
    # Initialize and seed
    print("\n🔧 Initializing database...")
    await init_db()
    
    # Run seed script
    from scripts.seed import seed_tenant, seed_purchase_orders, seed_receipts
    await seed_tenant()
    await seed_purchase_orders()
    await seed_receipts()
    
    # Ingest invoices
    await ingest_invoices()
    
    # Run pipeline
    results = await run_pipeline_on_all()
    
    # Print summary
    await print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
