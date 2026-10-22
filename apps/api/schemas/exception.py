"""
Exception schemas for API request/response.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.models.exception import (
    ExceptionCategory,
    ExceptionSeverity,
    ExceptionStatus,
    OwnerRole,
)
from apps.api.schemas.invoice import InvoiceSummary


class ExceptionResponse(BaseModel):
    """Exception case response."""
    id: UUID
    tenant_id: UUID
    invoice_id: UUID
    invoice: Optional[InvoiceSummary] = None
    pipeline_run_id: Optional[UUID] = None
    
    # Classification
    category: ExceptionCategory
    severity: ExceptionSeverity
    
    # Status
    status: ExceptionStatus
    owner_role: OwnerRole
    assigned_to: Optional[UUID] = None
    
    # Details
    title: str
    description: Optional[str] = None
    details: Optional[dict] = None
    
    # SLA
    sla_deadline: datetime
    sla_breached: bool = False
    
    # Resolution
    resolution: Optional[str] = None
    resolution_action: Optional[str] = None
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ExceptionListResponse(BaseModel):
    """Paginated list of exceptions."""
    items: List[ExceptionResponse]
    total: int
    page: int
    page_size: int
    pages: int
    
    # Summary stats
    open_count: int = 0
    sla_breached_count: int = 0


class ExceptionResolveRequest(BaseModel):
    """Request to resolve an exception."""
    resolution: str = Field(..., min_length=1, max_length=2000)
    resolution_action: str = Field(
        ...,
        description="approve, reject, escalate, or reprocess"
    )
    notes: Optional[str] = Field(None, max_length=1000)


class ExceptionSummary(BaseModel):
    """Brief exception summary for lists."""
    id: UUID
    invoice_id: UUID
    category: ExceptionCategory
    severity: ExceptionSeverity
    status: ExceptionStatus
    title: str
    sla_deadline: datetime
    sla_breached: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class ExceptionCreateInternal(BaseModel):
    """Internal schema for creating exceptions (not exposed via API)."""
    tenant_id: UUID
    invoice_id: UUID
    pipeline_run_id: Optional[UUID] = None
    category: ExceptionCategory
    severity: ExceptionSeverity
    title: str
    description: Optional[str] = None
    details: Optional[dict] = None
