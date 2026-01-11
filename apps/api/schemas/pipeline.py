"""
Pipeline schemas for API request/response.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.models.pipeline import PipelineState


class StateTransition(BaseModel):
    """A single state transition in the pipeline."""
    from_state: str
    to_state: str
    timestamp: datetime


class PipelineRunResponse(BaseModel):
    """Pipeline run response."""
    id: UUID
    tenant_id: UUID
    invoice_id: UUID
    state: PipelineState
    
    # Timestamps
    ingested_at: Optional[datetime] = None
    validation_started_at: Optional[datetime] = None
    validation_completed_at: Optional[datetime] = None
    matching_started_at: Optional[datetime] = None
    matching_completed_at: Optional[datetime] = None
    llm_started_at: Optional[datetime] = None
    llm_completed_at: Optional[datetime] = None
    verification_started_at: Optional[datetime] = None
    verification_completed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Metadata
    is_replay: bool = False
    original_run_id: Optional[UUID] = None
    policy_version: str
    router_policy_version: str
    
    # Results
    final_decision: Optional[str] = None
    confidence_score: Optional[float] = None
    error_message: Optional[str] = None
    state_history: List[dict] = Field(default_factory=list)
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PipelineRunRequest(BaseModel):
    """Request to run pipeline on an invoice."""
    force_reprocess: bool = Field(
        default=False,
        description="Force reprocessing even if already processed"
    )
    policy_version: Optional[str] = Field(
        None,
        description="Specific policy version to use (for testing)"
    )


class BatchRunRequest(BaseModel):
    """Request to run pipeline on multiple invoices."""
    invoice_ids: List[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of invoice IDs to process"
    )
    force_reprocess: bool = False
    use_batch_api: bool = Field(
        default=True,
        description="Use batch API for LLM calls (cheaper)"
    )


class BatchRunResponse(BaseModel):
    """Batch run response."""
    batch_id: UUID
    total_invoices: int
    queued: int
    skipped: int
    estimated_completion_time: Optional[datetime] = None
    status: str = "queued"


class PipelineRunSummary(BaseModel):
    """Brief pipeline run summary."""
    id: UUID
    invoice_id: UUID
    state: PipelineState
    final_decision: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
