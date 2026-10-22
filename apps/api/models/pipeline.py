"""
Pipeline run model for tracking invoice processing state machine.
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


class PipelineState(str, Enum):
    """Pipeline processing states."""
    INGESTED = "ingested"
    VALIDATING = "validating"
    MATCHING = "matching"
    LLM_PROCESSING = "llm_processing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    EXCEPTION = "exception"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"  # Permanently failed after max retries
    FAILED_PERMANENTLY = "dead_letter"  # Alias for dead letter


class InvoicePipelineRun(TenantScopedBase):
    """
    Tracks a single pipeline execution for an invoice.
    
    Each invoice can have multiple runs (e.g., after reprocessing).
    The state machine transitions are persisted for audit and replay.
    """
    
    __tablename__ = "invoice_pipeline_runs"
    
    # Invoice reference
    invoice_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Current state
    state: Mapped[PipelineState] = mapped_column(
        String(30),
        default=PipelineState.INGESTED,
        nullable=False,
    )
    
    # State transition timestamps
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    matching_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    matching_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    llm_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    llm_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Run metadata
    is_replay: Mapped[bool] = mapped_column(default=False, nullable=False)
    original_run_id: Mapped[Optional[UUID]] = mapped_column(Uuid(), nullable=True)
    
    # Policy versions used
    policy_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    router_policy_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    
    # Results
    final_decision: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Recovery and checkpoint tracking
    last_checkpoint: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Last successful step
    completed_steps: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(default=0, nullable=False)
    processing_timeout: Mapped[int] = mapped_column(default=300, nullable=False)  # seconds
    
    # State history as JSON array
    state_history: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    
    # Relationships
    invoice: Mapped["Invoice"] = relationship(
        "Invoice",
        back_populates="pipeline_runs",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="pipeline_run",
        lazy="selectin",
    )
    cost_events: Mapped[list["CostEvent"]] = relationship(
        "CostEvent",
        back_populates="pipeline_run",
        lazy="selectin",
    )
    
    __table_args__ = (
        Index("ix_pipeline_run_tenant_invoice", "tenant_id", "invoice_id"),
        Index("ix_pipeline_run_tenant_state", "tenant_id", "state"),
    )
    
    def transition_to(self, new_state: PipelineState) -> None:
        """
        Transition to a new state, recording the history.
        """
        now = datetime.utcnow()
        self.state_history.append({
            "from_state": self.state.value,
            "to_state": new_state.value,
            "timestamp": now.isoformat(),
        })
        self.state = new_state
        
        # Update corresponding timestamp
        timestamp_map = {
            PipelineState.VALIDATING: "validation_started_at",
            PipelineState.MATCHING: "matching_started_at",
            PipelineState.LLM_PROCESSING: "llm_started_at",
            PipelineState.VERIFYING: "verification_started_at",
            PipelineState.COMPLETED: "completed_at",
        }
        if new_state in timestamp_map:
            setattr(self, timestamp_map[new_state], now)
    
    @property
    def can_resume(self) -> bool:
        """Check if this run can be resumed from a failed state."""
        return self.state in [PipelineState.FAILED, PipelineState.EXCEPTION] and self.failure_count < 3
    
    @property
    def is_resumable(self) -> bool:
        """Alias for can_resume."""
        return self.can_resume
    
    @property
    def is_stuck(self) -> bool:
        """Check if this run appears to be stuck in processing."""
        if self.state not in [PipelineState.VALIDATING, PipelineState.MATCHING, 
                               PipelineState.LLM_PROCESSING, PipelineState.VERIFYING]:
            return False
        # Check if processing started but hasn't progressed
        started_at = getattr(self, f"{self.state.value.split('_')[0]}_started_at", None)
        if started_at and (datetime.utcnow() - started_at).total_seconds() > self.processing_timeout:
            return True
        return False
    
    def __repr__(self) -> str:
        return f"<InvoicePipelineRun(id={self.id}, invoice_id={self.invoice_id}, state={self.state})>"


# Import for type hints
from apps.api.models.invoice import Invoice
from apps.api.models.audit import AuditEvent
from apps.api.models.cost import CostEvent
