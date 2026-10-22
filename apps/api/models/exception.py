"""
Exception case model for the exception queue.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy import Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import TenantScopedBase


class ExceptionCategory(str, Enum):
    """Exception taxonomy categories."""
    MISSING_PO = "missing_po"
    DUPLICATE = "duplicate"
    AMOUNT_VARIANCE = "amount_variance"
    QUANTITY_VARIANCE = "quantity_variance"
    VENDOR_MISMATCH = "vendor_mismatch"
    MISSING_RECEIPT = "missing_receipt"
    LLM_VALIDATION_FAILED = "llm_validation_failed"
    MISSING_FIELDS = "missing_fields"
    CURRENCY_MISMATCH = "currency_mismatch"
    OTHER = "other"


class ExceptionSeverity(str, Enum):
    """Exception severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExceptionStatus(str, Enum):
    """Exception resolution status."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    REJECTED = "rejected"


class OwnerRole(str, Enum):
    """Roles that can own exceptions."""
    CONTROLLER = "controller"
    AP_MANAGER = "ap_manager"
    BPO_OPERATOR = "bpo_operator"


# Default SLA hours by category
EXCEPTION_SLA_HOURS = {
    ExceptionCategory.MISSING_PO: 24,
    ExceptionCategory.DUPLICATE: 4,
    ExceptionCategory.AMOUNT_VARIANCE: 8,
    ExceptionCategory.QUANTITY_VARIANCE: 24,
    ExceptionCategory.VENDOR_MISMATCH: 48,
    ExceptionCategory.MISSING_RECEIPT: 24,
    ExceptionCategory.LLM_VALIDATION_FAILED: 4,
    ExceptionCategory.MISSING_FIELDS: 24,
    ExceptionCategory.CURRENCY_MISMATCH: 8,
    ExceptionCategory.OTHER: 48,
}

# Default owner role by category
EXCEPTION_OWNER_ROLE = {
    ExceptionCategory.MISSING_PO: OwnerRole.AP_MANAGER,
    ExceptionCategory.DUPLICATE: OwnerRole.CONTROLLER,
    ExceptionCategory.AMOUNT_VARIANCE: OwnerRole.AP_MANAGER,
    ExceptionCategory.QUANTITY_VARIANCE: OwnerRole.BPO_OPERATOR,
    ExceptionCategory.VENDOR_MISMATCH: OwnerRole.BPO_OPERATOR,
    ExceptionCategory.MISSING_RECEIPT: OwnerRole.BPO_OPERATOR,
    ExceptionCategory.LLM_VALIDATION_FAILED: OwnerRole.CONTROLLER,
    ExceptionCategory.MISSING_FIELDS: OwnerRole.BPO_OPERATOR,
    ExceptionCategory.CURRENCY_MISMATCH: OwnerRole.AP_MANAGER,
    ExceptionCategory.OTHER: OwnerRole.AP_MANAGER,
}


class ExceptionCase(TenantScopedBase):
    """
    Exception case for the exception queue.
    
    Tracks issues found during invoice processing that require
    human review and resolution.
    """
    
    __tablename__ = "exception_cases"
    
    # Invoice reference
    invoice_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Pipeline run that created this exception
    pipeline_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(),
        ForeignKey("invoice_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Exception classification
    category: Mapped[ExceptionCategory] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    severity: Mapped[ExceptionSeverity] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    
    # Status and assignment
    status: Mapped[ExceptionStatus] = mapped_column(
        String(20),
        default=ExceptionStatus.OPEN,
        nullable=False,
        index=True,
    )
    owner_role: Mapped[OwnerRole] = mapped_column(
        String(20),
        nullable=False,
    )
    assigned_to: Mapped[Optional[UUID]] = mapped_column(Uuid(), nullable=True)
    
    # Description and details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # SLA tracking
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_breached: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    # Resolution
    resolution: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    resolution_action: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resolved_by: Mapped[Optional[UUID]] = mapped_column(Uuid(), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    invoice: Mapped["Invoice"] = relationship(
        "Invoice",
        back_populates="exceptions",
    )
    
    __table_args__ = (
        Index("ix_exception_tenant_status", "tenant_id", "status"),
        Index("ix_exception_tenant_category", "tenant_id", "category"),
        Index("ix_exception_tenant_severity", "tenant_id", "severity"),
        Index("ix_exception_sla_deadline", "sla_deadline"),
    )
    
    def __repr__(self) -> str:
        return f"<ExceptionCase(id={self.id}, category={self.category}, status={self.status})>"


# Import for type hints
from apps.api.models.invoice import Invoice
