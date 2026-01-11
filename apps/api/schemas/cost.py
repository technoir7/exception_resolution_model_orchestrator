"""
Cost schemas for API request/response.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
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


class CostByExceptionTypeResponse(BaseModel):
    """Cost aggregated by exception type."""
    category: str
    total_cost_usd: Decimal
    exception_count: int
    avg_cost_per_exception: Decimal


class CostByModelTierResponse(BaseModel):
    """Cost aggregated by model tier."""
    model_tier: ModelTier
    total_cost_usd: Decimal
    call_count: int
    total_tokens: int
    avg_cost_per_call: Decimal


class CacheMetricsResponse(BaseModel):
    """Cache performance metrics."""
    total_requests: int
    cache_hits: int
    cache_misses: int
    hit_rate: float = Field(..., ge=0, le=1)
    
    total_savings_usd: Decimal
    avg_savings_per_hit: Decimal


class DailyCostResponse(BaseModel):
    """Daily cost summary."""
    date: date
    total_cost_usd: Decimal
    invoice_count: int
    exception_count: int
    cache_hit_rate: float


class CostDashboardResponse(BaseModel):
    """Full cost dashboard data."""
    # Summary metrics
    total_cost_usd: Decimal
    total_invoices_processed: int
    avg_cost_per_invoice: Decimal
    avg_cost_per_verified_invoice: Decimal
    
    # Touchless rate
    touchless_count: int
    exception_count: int
    touchless_rate: float
    
    # Cache metrics
    cache_metrics: CacheMetricsResponse
    
    # Breakdowns
    cost_by_model_tier: List[CostByModelTierResponse]
    cost_by_exception_type: List[CostByExceptionTypeResponse]
    daily_costs: List[DailyCostResponse]
    
    # Time range
    start_date: date
    end_date: date


class TenantSpendResponse(BaseModel):
    """Tenant spend tracking."""
    tenant_id: UUID
    tenant_name: str
    daily_budget: Decimal
    spent_today: Decimal
    remaining_budget: Decimal
    is_capped: bool
