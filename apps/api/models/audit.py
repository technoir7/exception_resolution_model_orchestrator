"""
Audit event model for the append-only audit ledger.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import TenantScopedBase


class AuditStep(str, Enum):
    """Pipeline steps that emit audit events."""
    INGESTION = "ingestion"
    VALIDATION = "validation"
    DUPLICATE_CHECK = "duplicate_check"
    PO_LOOKUP = "po_lookup"
    MATCHING = "matching"
    LLM_ROUTING = "llm_routing"
    LLM_CALL = "llm_call"
    SHADOW_ROUTING = "shadow_routing"
    VERIFICATION = "verification"
    EXCEPTION_CREATED = "exception_created"
    EXCEPTION_RESOLVED = "exception_resolved"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"


class AuditEvent(TenantScopedBase):
    """
    Append-only audit event for compliance and replay.
    
    Records all significant pipeline steps with full context
    for deterministic replay and drift detection.
    """
    
    __tablename__ = "audit_events"
    
    # References
    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoice_pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Event identification
    step: Mapped[AuditStep] = mapped_column(String(50), nullable=False)
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    
    # Version tracking for replay
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Input/output hashing for drift detection
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Full input/output for replay (stored as JSON)
    raw_input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(nullable=False)
    
    # Actor (user or system)
    actor_type: Mapped[str] = mapped_column(String(20), default="system", nullable=False)
    actor_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    
    # Additional event metadata
    event_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    pipeline_run: Mapped["InvoicePipelineRun"] = relationship(
        "InvoicePipelineRun",
        back_populates="audit_events",
    )
    
    __table_args__ = (
        Index("ix_audit_tenant_invoice", "tenant_id", "invoice_id"),
        Index("ix_audit_pipeline_run_seq", "pipeline_run_id", "sequence_number"),
        Index("ix_audit_step", "step"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditEvent(id={self.id}, step={self.step}, seq={self.sequence_number})>"


# Import for type hints
from apps.api.models.pipeline import InvoicePipelineRun
