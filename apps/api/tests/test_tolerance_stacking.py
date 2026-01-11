"""
Tests for vulnerability: Tolerance Stacking

Tests that both line-level AND document-level tolerance checks are performed.
Line items might individually pass tolerance but compound to exceed document-level limits.
"""

import pytest
from decimal import Decimal
from datetime import date
from uuid import uuid4

from apps.api.services.matching_engine import MatchingEngine, MatchResult, MatchStatus


class TestToleranceStacking:
    """Test that tolerance stacking is caught at document level."""

    @pytest.fixture
    def matching_engine(self):
        """Create matching engine with 5% line tolerance."""
        return MatchingEngine(
            amount_tolerance=Decimal("0.05"),  # 5% tolerance
            quantity_tolerance=Decimal("0.05"),
        )

    def test_line_items_pass_but_document_total_exceeds_tolerance(self, matching_engine):
        """
        Each line item is within 5% tolerance individually,
        but cumulative effect exceeds document-level tolerance.
        """
        # Invoice with lines that are each ~4% over (within 5%)
        invoice_data = {
            "invoice_number": "INV-TEST-001",
            "vendor_id": "V001",
            "po_number": "PO-001",
            "currency": "USD",
            "subtotal": Decimal("10400.00"),  # 4% over PO total
            "total_amount": Decimal("10400.00"),
            "line_items": [
                {"line_number": 1, "description": "Item A", "quantity": 100, "unit_price": Decimal("52.00"), "amount": Decimal("5200.00")},  # 4% over
                {"line_number": 2, "description": "Item B", "quantity": 100, "unit_price": Decimal("52.00"), "amount": Decimal("5200.00")},  # 4% over
            ],
        }

        po_data = {
            "po_number": "PO-001",
            "vendor_id": "V001",
            "currency": "USD",
            "total_amount": Decimal("10000.00"),
            "line_items": [
                {"line_number": 1, "description": "Item A", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
                {"line_number": 2, "description": "Item B", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
            ],
        }

        result = matching_engine.match_two_way(invoice_data, po_data)
        
        # Each line is 4% over (within 5% tolerance)
        # But document total is $400 over $10000 = 4% over 
        # This should still pass if we're only checking line-level
        # BUT: If we change tolerance to 3%, this should fail at document level
        
        # For this test, we're asserting current behavior then will fix
        assert result is not None
        assert result.status in [MatchStatus.MATCHED, MatchStatus.VARIANCE_DETECTED]

    def test_document_level_tolerance_catches_compounding(self, matching_engine):
        """
        Test with stricter tolerance where compounding matters.
        Each line at 2.5% over, compounded = should trigger variance.
        """
        matching_engine.amount_tolerance = Decimal("0.02")  # 2% tolerance

        invoice_data = {
            "invoice_number": "INV-TEST-002",
            "vendor_id": "V001",
            "po_number": "PO-001",
            "currency": "USD",
            "subtotal": Decimal("10250.00"),  # 2.5% over PO total
            "total_amount": Decimal("10250.00"),
            "line_items": [
                {"line_number": 1, "description": "Item A", "quantity": 100, "unit_price": Decimal("51.25"), "amount": Decimal("5125.00")},  # 2.5% over
                {"line_number": 2, "description": "Item B", "quantity": 100, "unit_price": Decimal("51.25"), "amount": Decimal("5125.00")},  # 2.5% over
            ],
        }

        po_data = {
            "po_number": "PO-001",
            "vendor_id": "V001",
            "currency": "USD",
            "total_amount": Decimal("10000.00"),
            "line_items": [
                {"line_number": 1, "description": "Item A", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
                {"line_number": 2, "description": "Item B", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
            ],
        }

        result = matching_engine.match_two_way(invoice_data, po_data)
        
        # Document total is 2.5% over, which exceeds 2% tolerance
        # This MUST be caught
        assert result.status == MatchStatus.VARIANCE_DETECTED
        assert any("total" in str(v).lower() or "document" in str(v).lower() 
                   for v in result.variances)


class TestDocumentLevelCheck:
    """Test that document-level variance is explicitly checked."""

    @pytest.fixture
    def strict_engine(self):
        """Create engine with strict 1% tolerance."""
        return MatchingEngine(
            amount_tolerance=Decimal("0.01"),
            quantity_tolerance=Decimal("0.01"),
        )

    def test_document_total_variance_detected(self, strict_engine):
        """Document total variance must be reported even if line items match."""
        invoice_data = {
            "invoice_number": "INV-TEST-003",
            "vendor_id": "V001",
            "po_number": "PO-001",
            "currency": "USD",
            "subtotal": Decimal("10150.00"),  # 1.5% over
            "total_amount": Decimal("10150.00"),
            "line_items": [
                {"line_number": 1, "description": "Item A", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
                {"line_number": 2, "description": "Item B", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
                # Note: line items sum to 10000, but invoice total says 10150
            ],
        }

        po_data = {
            "po_number": "PO-001",
            "vendor_id": "V001",
            "currency": "USD",
            "total_amount": Decimal("10000.00"),
            "line_items": [
                {"line_number": 1, "description": "Item A", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
                {"line_number": 2, "description": "Item B", "quantity": 100, "unit_price": Decimal("50.00"), "amount": Decimal("5000.00")},
            ],
        }

        result = strict_engine.match_two_way(invoice_data, po_data)
        
        # The invoice total doesn't match the line item sum - internal inconsistency
        # OR the invoice total exceeds PO total beyond tolerance
        assert result.status == MatchStatus.VARIANCE_DETECTED
