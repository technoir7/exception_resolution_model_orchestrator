#!/usr/bin/env python
"""
Seed script to populate the database with fixture data.
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.models.base import async_session_maker, init_db
from apps.api.models.tenant import Tenant
from apps.api.models.vendor import Vendor
from apps.api.models.purchase_order import PurchaseOrder, POStatus
from apps.api.models.receipt import Receipt

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TENANT_ID = UUID("00000000-0000-0000-0000-000000000100")


async def seed_tenant():
    """Seed the demo tenant."""
    async with async_session_maker() as db:
        # Check if tenant exists
        result = await db.execute(select(Tenant).where(Tenant.id == TENANT_ID))
        if result.scalar_one_or_none():
            print("✓ Tenant already exists")
            return
        
        tenant = Tenant(
            id=TENANT_ID,
            name="Demo Corp",
            slug="demo-corp",
            is_active=True,
            daily_llm_budget=100.0,
        )
        db.add(tenant)
        await db.commit()
        print("✓ Created tenant: Demo Corp")


async def seed_purchase_orders():
    """Seed purchase orders from fixtures."""
    async with async_session_maker() as db:
        # Check if POs exist
        result = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.tenant_id == TENANT_ID)
        )
        if result.scalars().first():
            print("✓ Purchase orders already exist")
            return
        
        with open(FIXTURES_DIR / "purchase_orders.json") as f:
            pos = json.load(f)
        
        for po_data in pos:
            po = PurchaseOrder(
                tenant_id=TENANT_ID,
                po_number=po_data["po_number"],
                po_date=datetime.strptime(po_data["po_date"], "%Y-%m-%d").date(),
                status=POStatus(po_data["status"]),
                vendor_id=po_data["vendor_id"],
                vendor_name=po_data["vendor_name"],
                currency=po_data["currency"],
                total_amount=Decimal(po_data["total_amount"]),
                line_items=po_data["line_items"],
                terms=po_data.get("terms"),
            )
            db.add(po)
        
        await db.commit()
        print(f"✓ Created {len(pos)} purchase orders")


async def seed_receipts():
    """Seed receipts from fixtures."""
    async with async_session_maker() as db:
        # Check if receipts exist
        result = await db.execute(
            select(Receipt).where(Receipt.tenant_id == TENANT_ID)
        )
        if result.scalars().first():
            print("✓ Receipts already exist")
            return
        
        with open(FIXTURES_DIR / "receipts.json") as f:
            receipts = json.load(f)
        
        for rec_data in receipts:
            receipt = Receipt(
                tenant_id=TENANT_ID,
                receipt_number=rec_data["receipt_number"],
                receipt_date=datetime.strptime(rec_data["receipt_date"], "%Y-%m-%d").date(),
                po_number=rec_data["po_number"],
                vendor_id=rec_data["vendor_id"],
                total_amount=Decimal(rec_data["total_amount"]),
                line_items=rec_data["line_items"],
            )
            db.add(receipt)
        
        await db.commit()
        print(f"✓ Created {len(receipts)} receipts")


async def seed_vendors():
    """Seed vendor records, with the bank account each is paid into."""
    async with async_session_maker() as db:
        with open(FIXTURES_DIR / "vendors.json") as f:
            vendors = json.load(f)
        for v in vendors:
            result = await db.execute(select(Vendor).where(Vendor.tenant_id == TENANT_ID, Vendor.vendor_id == v["id"]))
            if result.scalar_one_or_none():
                continue
            db.add(Vendor(tenant_id=TENANT_ID, vendor_id=v["id"], name=v["name"], tax_id=v["tax_id"],
                          remit_bank=v["remit_bank"], remit_account_last4=v["remit_account_last4"],
                          payment_terms=v["payment_terms"]))
        await db.commit()
        print(f"✓ Seeded {len(vendors)} vendors")


async def main():
    """Run all seed functions."""
    print("\n=== AP Reconciliation Orchestrator - Database Seeding ===\n")
    
    print("Initializing database...")
    await init_db()
    print("✓ Database initialized\n")
    
    print("Seeding data...")
    await seed_tenant()
    await seed_vendors()
    await seed_purchase_orders()
    await seed_receipts()
    
    print("\n=== Seeding Complete ===\n")


if __name__ == "__main__":
    asyncio.run(main())
