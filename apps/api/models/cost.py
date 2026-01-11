"""
Cost event model for LLM cost tracking.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import TenantScopedBase


class CostEventType(str, Enum):
    """Types of cost events."""
    LLM_CALL = "llm_call"
    CACHE_HIT = "cache_hit"
    BATCH_PROCESSING = "batch_processing"


class ModelTier(str, Enum):
    """LLM model tiers."""
    TIER_A = "tier_a"  # Cheap/fast (e.g., GPT-3.5-turbo)
    TIER_B = "tier_b"  # Mid-tier (e.g., GPT-4-mini)
    TIER_C = "tier_c"  # Premium (e.g., GPT-4)


class CostEvent(TenantScopedBase):
    """
    Tracks LLM and processing costs for cost accounting.
    
    Enables cost-per-verified-invoice calculations and
    cost dashboard metrics.
    """
    
    __tablename__ = "cost_events"
    
    # References
    invoice_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pipeline_run_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoice_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    exception_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exception_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Event type
    event_type: Mapped[CostEventType] = mapped_column(String(30), nullable=False)
    
    # Model info
    model_tier: Mapped[Optional[ModelTier]] = mapped_column(String(20), nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Token usage
    input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    
    # Cost
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    
    # Cache info
    cache_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    was_cache_hit: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    # Batch info
    batch_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    batch_discount_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    
    # Timing
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    # Additional metadata
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    pipeline_run: Mapped[Optional["InvoicePipelineRun"]] = relationship(
        "InvoicePipelineRun",
        back_populates="cost_events",
    )
    
    __table_args__ = (
        Index("ix_cost_tenant_invoice", "tenant_id", "invoice_id"),
        Index("ix_cost_tenant_timestamp", "tenant_id", "event_timestamp"),
        Index("ix_cost_event_type", "event_type"),
        Index("ix_cost_model_tier", "model_tier"),
    )
    
    def __repr__(self) -> str:
        return f"<CostEvent(id={self.id}, type={self.event_type}, cost=${self.cost_usd})>"


# Import for type hints
from apps.api.models.pipeline import InvoicePipelineRun
