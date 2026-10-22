"""
Audit schemas for API request/response.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.models.audit import AuditStep


class AuditEventResponse(BaseModel):
    """Audit event response."""
    id: UUID
    invoice_id: UUID
    pipeline_run_id: UUID
    
    # Event details
    step: AuditStep
    sequence_number: int
    
    # Versions
    policy_version: str
    prompt_version: Optional[str] = None
    model_id: Optional[str] = None
    
    # Hashes
    input_hash: str
    output_hash: str
    
    # Content (may be redacted in some cases)
    raw_input: Optional[dict] = None
    raw_output: Optional[dict] = None
    
    # Timing
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    
    # Actor
    actor_type: str
    actor_id: Optional[UUID] = None
    
    # The model's `metadata` attribute is SQLAlchemy's table registry; the
    # event's own is stored as `event_metadata`.
    metadata: Optional[dict] = Field(None, validation_alias="event_metadata")
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class AuditTimelineResponse(BaseModel):
    """Full audit timeline for an invoice."""
    invoice_id: UUID
    events: List[AuditEventResponse]
    total_events: int
    
    # Summary
    first_event_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    total_duration_ms: int = 0


class ReplayRequest(BaseModel):
    """Request to replay a pipeline run."""
    use_original_inputs: bool = Field(
        default=True,
        description="Use stored inputs from original run"
    )
    compare_outputs: bool = Field(
        default=True,
        description="Compare outputs with original run"
    )


class Drift(BaseModel):
    """A single drift between original and replay."""
    step: AuditStep
    sequence_number: int
    original_output_hash: str
    replay_output_hash: str
    original_output: Optional[dict] = None
    replay_output: Optional[dict] = None
    description: str = ""


class DriftReport(BaseModel):
    """Report comparing original run with replay."""
    original_run_id: UUID
    replay_run_id: UUID
    has_drift: bool
    drifts: List[Drift] = Field(default_factory=list)
    
    # Summary
    total_steps: int
    matching_steps: int
    drifting_steps: int
    
    # Metadata
    original_policy_version: str
    replay_policy_version: str
    comparison_timestamp: datetime


class ReplayResponse(BaseModel):
    """Response from replay endpoint."""
    replay_run: "PipelineRunResponse"
    drift_report: DriftReport


# Import for type hint
from apps.api.schemas.pipeline import PipelineRunResponse
ReplayResponse.model_rebuild()
