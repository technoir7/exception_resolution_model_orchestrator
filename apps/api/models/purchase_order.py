"""
Purchase Order model with canonical data structure.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Text, Date, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import TenantScopedBase


class POStatus(str, Enum):
    """Purchase order status."""
    OPEN = "open"
    PARTIALLY_RECEIVED = "partially_received"
    FULLY_RECEIVED = "fully_received"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class PurchaseOrder(TenantScopedBase):
    """
    Purchase Order model with canonical fields for matching.
    
    Used for 2-way and 3-way matching against invoices.
    """
    
    __tablename__ = "purchase_orders"
    
    # PO identification
    po_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    po_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Status
    status: Mapped[POStatus] = mapped_column(
        String(20),
        default=POStatus.OPEN,
        nullable=False,
    )
    
    # Vendor info
    vendor_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Ship to
    ship_to_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Amounts
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    
    # Line items
    line_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Commercial terms in words (pricing, freight, tax, payment), which decide
    # whether a charge on an invoice is allowed.
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Received quantities tracking
    received_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        default=Decimal("0"),
        nullable=False,
    )
    
    __table_args__ = (
        Index("ix_po_tenant_number", "tenant_id", "po_number", unique=True),
        Index("ix_po_tenant_vendor", "tenant_id", "vendor_id"),
    )
    
    def __repr__(self) -> str:
        return f"<PurchaseOrder(id={self.id}, number={self.po_number}, status={self.status})>"
