"""
Cost schemas for API request/response.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.models.cost import CostEventType, ModelTier


class CostEventResponse(BaseModel):
    """Cost event response."""
    id: UUID
    tenant_id: UUID
    invoice_id: Optional[UUID] = None
    pipeline_run_id: Optional[UUID] = None
    exception_id: Optional[UUID] = None
    
    event_type: CostEventType
    model_tier: Optional[ModelTier] = None
    model_id: Optional[str] = None
    
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Decimal
    
    was_cache_hit: bool = False
    batch_id: Optional[UUID] = None
    
    event_timestamp: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class CostByInvoiceResponse(BaseModel):
    """Cost aggregated by invoice."""
    invoice_id: UUID
    invoice_number: Optional[str] = None
    total_cost_usd: Decimal
    llm_calls: int
    cache_hits: int
    total_tokens: int
    final_status: str


class ModelSpend(BaseModel):
    """What one model was paid over a period."""
    model_id: Optional[str] = None
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class CostDashboardResponse(BaseModel):
    """Model spend over a period, against the invoices received in it."""
    start_date: date
    end_date: date
    total_cost_usd: Decimal
    invoices_by_status: Dict[str, int]
    cost_per_invoice: Decimal
    spent_today: Decimal
    daily_cap_usd: Decimal
    by_model: List[ModelSpend]


class ModelCall(BaseModel):
    model_id: Optional[str] = None
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    at: datetime


class InvoiceCostResponse(BaseModel):
    """What reading and reviewing one invoice cost, call by call."""
    invoice_id: UUID
    total_cost_usd: Decimal
    calls: List[ModelCall]


class TenantSpendResponse(BaseModel):
    """Tenant spend tracking."""
    tenant_id: UUID
    tenant_name: str
    daily_budget: Decimal
    spent_today: Decimal
    remaining_budget: Decimal
    is_capped: bool
