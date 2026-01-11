"""
Tests for replay and drift detection.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from apps.api.models.audit import AuditEvent, AuditStep
from apps.api.services.audit_service import AuditService
from apps.api.tests.conftest import TEST_TENANT_ID


class TestAuditEventEmission:
    """Tests for audit event emission."""
    
    @pytest.mark.asyncio
    async def test_emit_creates_event(self, db_session):
        """Test that emit creates an audit event."""
        service = AuditService(db_session, TEST_TENANT_ID)
        invoice_id = uuid4()
        run_id = uuid4()
        
        event = await service.emit(
            invoice_id=invoice_id,
            pipeline_run_id=run_id,
            step=AuditStep.VALIDATION,
            raw_input={"test": "input"},
            raw_output={"test": "output"},
            started_at=datetime.utcnow(),
            policy_version="v1",
        )
        
        assert event is not None
        assert event.invoice_id == invoice_id
        assert event.pipeline_run_id == run_id
        assert event.step == AuditStep.VALIDATION
        assert event.sequence_number == 1
    
    @pytest.mark.asyncio
    async def test_sequence_numbers_increment(self, db_session):
        """Test that sequence numbers increment correctly."""
        service = AuditService(db_session, TEST_TENANT_ID)
        invoice_id = uuid4()
        run_id = uuid4()
        
        event1 = await service.emit(
            invoice_id=invoice_id,
            pipeline_run_id=run_id,
            step=AuditStep.VALIDATION,
            raw_input={},
            raw_output={},
            started_at=datetime.utcnow(),
            policy_version="v1",
        )
        
        event2 = await service.emit(
            invoice_id=invoice_id,
            pipeline_run_id=run_id,
            step=AuditStep.MATCHING,
            raw_input={},
            raw_output={},
            started_at=datetime.utcnow(),
            policy_version="v1",
        )
        
        assert event1.sequence_number == 1
        assert event2.sequence_number == 2


class TestHashComputation:
    """Tests for hash computation."""
    
    def test_same_input_same_hash(self):
        """Test that same input produces same hash."""
        hash1 = AuditService._compute_hash({"key": "value", "number": 123})
        hash2 = AuditService._compute_hash({"key": "value", "number": 123})
        
        assert hash1 == hash2
    
    def test_different_input_different_hash(self):
        """Test that different input produces different hash."""
        hash1 = AuditService._compute_hash({"key": "value1"})
        hash2 = AuditService._compute_hash({"key": "value2"})
        
        assert hash1 != hash2
    
    def test_key_order_independent(self):
        """Test that hash is independent of key order."""
        hash1 = AuditService._compute_hash({"a": 1, "b": 2})
        hash2 = AuditService._compute_hash({"b": 2, "a": 1})
        
        assert hash1 == hash2


class TestDriftDetection:
    """Tests for drift detection between runs."""
    
    @pytest.mark.asyncio
    async def test_identical_outputs_no_drift(self, db_session):
        """Test that identical outputs produce no drift."""
        service = AuditService(db_session, TEST_TENANT_ID)
        
        # Create two events with same output
        output = {"decision": "approve", "confidence": 0.95}
        
        event1 = AuditEvent(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            invoice_id=uuid4(),
            pipeline_run_id=uuid4(),
            step=AuditStep.VALIDATION,
            sequence_number=1,
            policy_version="v1",
            input_hash="abc",
            output_hash=service._compute_hash(output),
            raw_input={},
            raw_output=output,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        
        event2 = AuditEvent(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            invoice_id=uuid4(),
            pipeline_run_id=uuid4(),
            step=AuditStep.VALIDATION,
            sequence_number=1,
            policy_version="v1",
            input_hash="abc",
            output_hash=service._compute_hash(output),
            raw_input={},
            raw_output=output,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        
        matches, diff = service.compare_outputs(event1, event2)
        
        assert matches
        assert diff is None
    
    @pytest.mark.asyncio
    async def test_different_outputs_detect_drift(self, db_session):
        """Test that different outputs are detected as drift."""
        service = AuditService(db_session, TEST_TENANT_ID)
        
        output1 = {"decision": "approve", "confidence": 0.95}
        output2 = {"decision": "reject", "confidence": 0.90}
        
        event1 = AuditEvent(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            invoice_id=uuid4(),
            pipeline_run_id=uuid4(),
            step=AuditStep.VALIDATION,
            sequence_number=1,
            policy_version="v1",
            input_hash="abc",
            output_hash=service._compute_hash(output1),
            raw_input={},
            raw_output=output1,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        
        event2 = AuditEvent(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            invoice_id=uuid4(),
            pipeline_run_id=uuid4(),
            step=AuditStep.VALIDATION,
            sequence_number=1,
            policy_version="v1",
            input_hash="abc",
            output_hash=service._compute_hash(output2),
            raw_input={},
            raw_output=output2,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
        )
        
        matches, diff = service.compare_outputs(event1, event2)
        
        assert not matches
        assert diff is not None
        assert diff["original_output"] == output1
        assert diff["replay_output"] == output2
