"""
Receipt (Goods Receipt) model for 3-way matching.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import TenantScopedBase


class Receipt(TenantScopedBase):
    """
    Goods Receipt model for 3-way matching.
    
    Records what was physically received against a PO, enabling
    verification that invoiced quantities match received quantities.
    """
    
    __tablename__ = "receipts"
    
    # Receipt identification
    receipt_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # PO reference
    po_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Vendor info
    vendor_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Location
    receiving_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Amounts/quantities
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    
    # Line items with quantities received
    line_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    __table_args__ = (
        Index("ix_receipt_tenant_number", "tenant_id", "receipt_number", unique=True),
        Index("ix_receipt_tenant_po", "tenant_id", "po_number"),
    )
    
    def __repr__(self) -> str:
        return f"<Receipt(id={self.id}, number={self.receipt_number}, po={self.po_number})>"
