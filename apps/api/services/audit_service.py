"""
Audit Service for emit audit events and managing the audit ledger.
"""

import hashlib
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.audit import AuditEvent, AuditStep

logger = structlog.get_logger()


class AuditService:
    """Service for managing the append-only audit ledger."""
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
        self._sequence_cache: Dict[UUID, int] = {}
    
    async def emit(
        self,
        invoice_id: UUID,
        pipeline_run_id: UUID,
        step: AuditStep,
        raw_input: Dict[str, Any],
        raw_output: Dict[str, Any],
        started_at: datetime,
        policy_version: str = "v1",
        prompt_version: Optional[str] = None,
        model_id: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        actor_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Emit an audit event to the ledger."""
        completed_at = datetime.utcnow()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        
        # Get next sequence number
        seq = await self._get_next_sequence(pipeline_run_id)
        
        # Compute hashes
        input_hash = self._compute_hash(raw_input)
        output_hash = self._compute_hash(raw_output)
        
        event = AuditEvent(
            tenant_id=self.tenant_id,
            invoice_id=invoice_id,
            pipeline_run_id=pipeline_run_id,
            step=step,
            sequence_number=seq,
            policy_version=policy_version,
            prompt_version=prompt_version,
            model_id=model_id,
            input_hash=input_hash,
            output_hash=output_hash,
            raw_input=raw_input,
            raw_output=raw_output,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata=metadata,
        )
        
        self.db.add(event)
        
        self.logger.debug(
            "Audit event emitted",
            step=step.value,
            sequence=seq,
            duration_ms=duration_ms,
        )
        
        return event
    
    async def get_timeline(self, invoice_id: UUID) -> List[AuditEvent]:
        """Get all audit events for an invoice."""
        query = (
            select(AuditEvent)
            .where(AuditEvent.invoice_id == invoice_id)
            .order_by(AuditEvent.created_at, AuditEvent.sequence_number)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_run_events(self, pipeline_run_id: UUID) -> List[AuditEvent]:
        """Get all audit events for a specific pipeline run."""
        query = (
            select(AuditEvent)
            .where(AuditEvent.pipeline_run_id == pipeline_run_id)
            .order_by(AuditEvent.sequence_number)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def _get_next_sequence(self, pipeline_run_id: UUID) -> int:
        """Get next sequence number for a pipeline run."""
        if pipeline_run_id in self._sequence_cache:
            self._sequence_cache[pipeline_run_id] += 1
            return self._sequence_cache[pipeline_run_id]
        
        query = select(AuditEvent.sequence_number).where(
            AuditEvent.pipeline_run_id == pipeline_run_id
        ).order_by(AuditEvent.sequence_number.desc()).limit(1)
        
        result = await self.db.execute(query)
        last_seq = result.scalar_one_or_none()
        
        next_seq = (last_seq or 0) + 1
        self._sequence_cache[pipeline_run_id] = next_seq
        return next_seq
    
    @staticmethod
    def _compute_hash(data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of JSON data."""
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def compare_outputs(
        self, original: AuditEvent, replay: AuditEvent
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Compare two audit events for drift detection."""
        if original.output_hash == replay.output_hash:
            return True, None
        
        # Compute diff
        diff = {
            "step": original.step.value,
            "original_hash": original.output_hash,
            "replay_hash": replay.output_hash,
            "original_output": original.raw_output,
            "replay_output": replay.raw_output,
        }
        return False, diff
