"""
Pytest fixtures and configuration.
"""

import asyncio
from datetime import date
from decimal import Decimal
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from apps.api.models.base import Base
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.purchase_order import PurchaseOrder, POStatus
from apps.api.models.receipt import Receipt

# Test tenant ID
TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000100")

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
def sample_invoice(db_session: AsyncSession) -> Invoice:
    """Create a sample invoice for testing."""
    return Invoice(
        id=uuid4(),
        tenant_id=TEST_TENANT_ID,
        document_content="test content",
        document_hash="abc123",
        document_type="text",
        status=InvoiceStatus.PENDING,
        invoice_number="INV-001",
        invoice_date=date(2024, 1, 15),
        vendor_id="V001",
        vendor_name="Acme Supplies",
        po_number="PO-001",
        currency="USD",
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("80.00"),
        total_amount=Decimal("1080.00"),
    )


@pytest.fixture
def sample_po(db_session: AsyncSession) -> PurchaseOrder:
    """Create a sample purchase order for testing."""
    return PurchaseOrder(
        id=uuid4(),
        tenant_id=TEST_TENANT_ID,
        po_number="PO-001",
        po_date=date(2024, 1, 10),
        status=POStatus.OPEN,
        vendor_id="V001",
        vendor_name="Acme Supplies",
        currency="USD",
        total_amount=Decimal("1000.00"),
        line_items=[
            {"line_number": 1, "description": "Widget A", "quantity": 10, "unit_price": 100, "amount": 1000}
        ],
    )


@pytest.fixture
def sample_receipt(db_session: AsyncSession) -> Receipt:
    """Create a sample receipt for testing."""
    return Receipt(
        id=uuid4(),
        tenant_id=TEST_TENANT_ID,
        receipt_number="REC-001",
        receipt_date=date(2024, 1, 14),
        po_number="PO-001",
        vendor_id="V001",
        total_amount=Decimal("1000.00"),
        line_items=[
            {"line_number": 1, "description": "Widget A", "quantity": 10}
        ],
    )
