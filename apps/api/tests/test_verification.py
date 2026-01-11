"""
Tests for the Verification Service.
"""

import pytest
from uuid import uuid4

from apps.api.services.verification import VerificationService
from apps.api.tests.conftest import TEST_TENANT_ID


class TestSchemaValidation:
    """Tests for JSON schema validation."""
    
    def test_valid_response_passes(self):
        """Test that valid response passes verification."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "decision": "approve",
            "confidence": 0.95,
            "match_type": "three_way",
            "reasoning": "All matches verified",
            "variances": [],
            "requires_review": False,
        }
        
        result = service.verify_llm_response(response)
        
        assert result.valid
        assert len(result.errors) == 0
    
    def test_missing_decision_fails(self):
        """Test that missing decision field fails."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "confidence": 0.95,
            "match_type": "three_way",
        }
        
        result = service.verify_llm_response(response)
        
        assert not result.valid
        assert any(e.field == "decision" for e in result.errors)
    
    def test_missing_confidence_fails(self):
        """Test that missing confidence field fails."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "decision": "approve",
            "match_type": "three_way",
        }
        
        result = service.verify_llm_response(response)
        
        assert not result.valid
        assert any(e.field == "confidence" for e in result.errors)
    
    def test_invalid_confidence_range_fails(self):
        """Test that confidence outside 0-1 range fails."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "decision": "approve",
            "confidence": 1.5,  # Invalid: > 1
        }
        
        result = service.verify_llm_response(response)
        
        assert not result.valid
        assert any(e.field == "confidence" for e in result.errors)


class TestInvariantChecks:
    """Tests for invariant validation."""
    
    def test_line_items_sum_matches_subtotal(self):
        """Test that line items sum matching subtotal passes."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "decision": "approve",
            "confidence": 0.95,
        }
        
        invoice_data = {
            "subtotal": "1000.00",
            "line_items": [
                {"amount": "400.00"},
                {"amount": "600.00"},
            ],
        }
        
        result = service.verify_llm_response(response, invoice_data=invoice_data)
        
        invariant_errors = [e for e in result.errors if e.error_type == "invariant_violation"]
        assert len(invariant_errors) == 0
    
    def test_line_items_sum_mismatch_fails(self):
        """Test that line items sum not matching subtotal fails."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "decision": "approve",
            "confidence": 0.95,
        }
        
        invoice_data = {
            "subtotal": "1000.00",
            "line_items": [
                {"amount": "400.00"},
                {"amount": "500.00"},  # Sum = 900, not 1000
            ],
        }
        
        result = service.verify_llm_response(response, invoice_data=invoice_data)
        
        invariant_errors = [e for e in result.errors if e.error_type == "invariant_violation"]
        assert len(invariant_errors) > 0


class TestBusinessLogic:
    """Tests for business logic validation."""
    
    def test_low_confidence_approve_without_review_fails(self):
        """Test that low confidence approval without review flag fails."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "decision": "approve",
            "confidence": 0.5,  # Low confidence
            "requires_review": False,  # Should require review
        }
        
        result = service.verify_llm_response(response)
        
        assert not result.valid
        assert any(e.error_type == "logic_error" for e in result.errors)
    
    def test_low_confidence_approve_with_review_passes(self):
        """Test that low confidence approval with review flag passes."""
        service = VerificationService(TEST_TENANT_ID)
        
        response = {
            "decision": "approve",
            "confidence": 0.5,
            "requires_review": True,  # Correctly flagged
        }
        
        result = service.verify_llm_response(response)
        
        logic_errors = [e for e in result.errors if e.error_type == "logic_error"]
        assert len(logic_errors) == 0


class TestJSONValidation:
    """Tests for JSON structure validation."""
    
    def test_valid_json_passes(self):
        """Test that valid JSON structure passes."""
        service = VerificationService(TEST_TENANT_ID)
        
        content = '{"decision": "approve", "confidence": 0.95}'
        valid, parsed, error = service.verify_json_structure(content)
        
        assert valid
        assert parsed["decision"] == "approve"
        assert error == ""
    
    def test_invalid_json_fails(self):
        """Test that invalid JSON fails."""
        service = VerificationService(TEST_TENANT_ID)
        
        content = '{decision: approve}'  # Invalid JSON (no quotes)
        valid, parsed, error = service.verify_json_structure(content)
        
        assert not valid
        assert parsed is None
        assert "Invalid JSON" in error
    
    def test_non_object_json_fails(self):
        """Test that JSON that's not an object fails."""
        service = VerificationService(TEST_TENANT_ID)
        
        content = '["array", "not", "object"]'
        valid, parsed, error = service.verify_json_structure(content)
        
        assert not valid
        assert "must be a JSON object" in error
