"""
Invoice model with canonical data structure.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import TenantScopedBase


class InvoiceStatus(str, Enum):
    """Invoice processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    MATCHED = "matched"
    EXCEPTION = "exception"
    APPROVED = "approved"
    REJECTED = "rejected"


class Invoice(TenantScopedBase):
    """
    Invoice model with raw document storage and canonical fields.
    
    Stores both the original document content and normalized/extracted fields
    for matching and processing.
    """
    
    __tablename__ = "invoices"
    
    # Document storage
    document_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(20), default="text")  # text, pdf, image
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Status
    status: Mapped[InvoiceStatus] = mapped_column(
        String(20),
        default=InvoiceStatus.PENDING,
        nullable=False,
        index=True,
    )
    
    # Canonical fields (extracted/normalized)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Vendor info
    vendor_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # PO reference
    po_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    # Amounts
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    
    # Line items as JSON
    line_items: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Processing metadata
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    validation_errors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    match_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    pipeline_runs: Mapped[list["InvoicePipelineRun"]] = relationship(
        "InvoicePipelineRun",
        back_populates="invoice",
        lazy="selectin",
    )
    exceptions: Mapped[list["ExceptionCase"]] = relationship(
        "ExceptionCase",
        back_populates="invoice",
        lazy="selectin",
    )
    
    __table_args__ = (
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_tenant_vendor", "tenant_id", "vendor_id"),
        Index("ix_invoices_tenant_po", "tenant_id", "po_number"),
    )
    
    def __repr__(self) -> str:
        return f"<Invoice(id={self.id}, number={self.invoice_number}, status={self.status})>"


# Import for type hints
from apps.api.models.pipeline import InvoicePipelineRun
from apps.api.models.exception import ExceptionCase
