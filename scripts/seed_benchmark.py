#!/usr/bin/env python
"""
Seed script to generate benchmark dataset for replay harness.
Generates 50+ invoices based on fixtures with variations.
"""

import asyncio
import hashlib
import json
import random
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.models.base import async_session_maker, init_db
from apps.api.models.invoice import Invoice, InvoiceStatus
# Import seed functions to ensure dependencies exist
from scripts.seed import seed_tenant, seed_purchase_orders, seed_receipts, TENANT_ID, FIXTURES_DIR

async def seed_benchmark_invoices(target_count=50):
    async with async_session_maker() as db:
        # Load base fixtures
        invoice_fixtures = sorted(FIXTURES_DIR.glob("invoices/*.json"))
        base_invoices = []
        for path in invoice_fixtures:
            with open(path) as f:
                base_invoices.append(json.load(f))
        
        print(f"Loaded {len(base_invoices)} base fixtures")
        
        # Check if invoices already exist to avoid dupes
        result = await db.execute(select(Invoice).where(Invoice.tenant_id == TENANT_ID))
        existing_count = len(result.scalars().all())
        if existing_count >= target_count:
            print(f"✓ Benchmark dataset already exists ({existing_count} invoices)")
            return

        created_count = 0
        
        print(f"Generating {target_count} invoices...")
        
        for i in range(target_count):
            base = base_invoices[i % len(base_invoices)]
            
            # Create a variation
            invoice_num = f"{base['invoice_number']}-BENCH-{i+1:03d}"
            
            # Perturb amount slightly (random +/- 5%) for some "synthetic" ones to create variance
            # Only do this for the "extended" set (i > len(base)), keeping the first few authentic to fixtures
            amount = Decimal(base["total_amount"])
            subtotal = Decimal(base["subtotal"]) if "subtotal" in base else amount
            
            if i >= len(base_invoices): 
                # 20% chance of variance
                if random.random() < 0.2:
                    factor = Decimal(random.uniform(0.95, 1.05))
                    amount = round(amount * factor, 2)
                    # We intentionally DON'T update subtotal to create internal inconsistency for some
            
            # Document hash
            content = json.dumps(base, sort_keys=True)
            doc_hash = hashlib.md5(f"{content}{i}".encode()).hexdigest()
            
            invoice = Invoice(
                id=uuid4(),
                tenant_id=TENANT_ID,
                document_content=content,
                document_hash=doc_hash,
                original_filename=f"{invoice_num}.pdf",
                status=InvoiceStatus.PENDING,
                invoice_number=invoice_num,
                invoice_date=datetime.strptime(base["invoice_date"], "%Y-%m-%d").date(),
                due_date=datetime.strptime(base["due_date"], "%Y-%m-%d").date(),
                vendor_id=base["vendor_id"],
                vendor_name=base["vendor_name"],
                po_number=base["po_number"],
                currency=base["currency"],
                subtotal=subtotal,
                total_amount=amount,
                line_items=base["line_items"],
            )
            db.add(invoice)
            created_count += 1
        
        await db.commit()
        print(f"✓ Created {created_count} benchmark invoices")

async def main():
    print("\n=== Seeding Benchmark Dataset ===\n")
    await init_db()
    # Ensure dependencies
    await seed_tenant()
    await seed_purchase_orders()
    await seed_receipts()
    
    await seed_benchmark_invoices()
    print("\n=== Benchmark Seeding Complete ===\n")

if __name__ == "__main__":
    asyncio.run(main())
