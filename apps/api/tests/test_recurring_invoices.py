"""
Tests for vulnerability: Duplicate Detection False Positives

Tests that recurring invoices (same vendor, same amount, different dates)
are not incorrectly flagged as duplicates.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from uuid import uuid4

from apps.api.services.rules_engine import RulesEngine, RulesResult


class TestRecurringInvoices:
    """Test that recurring invoices are handled correctly."""

    @pytest.fixture
    def rules_engine(self):
        """Create rules engine instance."""
        return RulesEngine()

    def test_monthly_recurring_invoice_not_flagged_as_duplicate(self, rules_engine):
        """
        Monthly software license invoices should not be flagged as duplicates.
        Same vendor, same amount, different invoice numbers, 30 days apart.
        """
        # First invoice (already in system)
        existing_invoices = [
            {
                "id": str(uuid4()),
                "invoice_number": "INV-JAN-001",
                "vendor_id": "V001",
                "vendor_name": "Acme Software Inc",
                "total_amount": Decimal("1000.00"),
                "invoice_date": date(2024, 1, 1),
                "document_hash": "hash_january",
            }
        ]

        # New invoice (February recurring)
        new_invoice = {
            "invoice_number": "INV-FEB-001",
            "vendor_id": "V001",
            "vendor_name": "Acme Software Inc",
            "total_amount": Decimal("1000.00"),
            "invoice_date": date(2024, 2, 1),  # 31 days later
            "document_hash": "hash_february",
        }

        # Should NOT be flagged as duplicate
        result = rules_engine.check_duplicate(new_invoice, existing_invoices)
        
        assert result.is_valid is True, (
            f"Monthly recurring invoice incorrectly flagged as duplicate: {result.message}"
        )

    def test_weekly_recurring_invoice_not_flagged(self, rules_engine):
        """Weekly invoices from same vendor should not be duplicates."""
        existing_invoices = [
            {
                "id": str(uuid4()),
                "invoice_number": "INV-W01",
                "vendor_id": "V001",
                "vendor_name": "Cleaning Services Co",
                "total_amount": Decimal("500.00"),
                "invoice_date": date(2024, 1, 1),
                "document_hash": "hash_week1",
            }
        ]

        new_invoice = {
            "invoice_number": "INV-W02",
            "vendor_id": "V001",
            "vendor_name": "Cleaning Services Co",
            "total_amount": Decimal("500.00"),
            "invoice_date": date(2024, 1, 8),  # 7 days later
            "document_hash": "hash_week2",
        }

        result = rules_engine.check_duplicate(new_invoice, existing_invoices)
        
        assert result.is_valid is True, (
            f"Weekly recurring invoice incorrectly flagged as duplicate: {result.message}"
        )

    def test_same_day_same_vendor_different_invoice_numbers_flagged(self, rules_engine):
        """
        Same vendor, same amount, same day, different invoice numbers
        should trigger a fuzzy duplicate warning.
        """
        existing_invoices = [
            {
                "id": str(uuid4()),
                "invoice_number": "INV-001",
                "vendor_id": "V001",
                "vendor_name": "Acme Corp",
                "total_amount": Decimal("5000.00"),
                "invoice_date": date(2024, 1, 15),
                "document_hash": "hash_original",
            }
        ]

        new_invoice = {
            "invoice_number": "INV-001-COPY",  # Different number
            "vendor_id": "V001",
            "vendor_name": "Acme Corp",
            "total_amount": Decimal("5000.00"),
            "invoice_date": date(2024, 1, 15),  # Same day
            "document_hash": "hash_copy",  # Different content
        }

        result = rules_engine.check_duplicate(new_invoice, existing_invoices)
        
        # Same day, same vendor, same amount = fuzzy duplicate
        assert result.is_valid is False, "Same-day invoice from same vendor should be flagged"

    def test_exact_duplicate_always_flagged(self, rules_engine):
        """Exact hash match should always be flagged regardless of date."""
        existing_invoices = [
            {
                "id": str(uuid4()),
                "invoice_number": "INV-001",
                "vendor_id": "V001",
                "vendor_name": "Acme Corp",
                "total_amount": Decimal("5000.00"),
                "invoice_date": date(2024, 1, 15),
                "document_hash": "exact_same_hash",
            }
        ]

        new_invoice = {
            "invoice_number": "INV-002",  # Different number
            "vendor_id": "V001",
            "vendor_name": "Acme Corp",
            "total_amount": Decimal("5000.00"),
            "invoice_date": date(2024, 2, 15),  # Different date
            "document_hash": "exact_same_hash",  # SAME hash = exact duplicate
        }

        result = rules_engine.check_duplicate(new_invoice, existing_invoices)
        
        assert result.is_valid is False, "Exact hash duplicate must always be flagged"
        assert "exact" in result.message.lower() or "duplicate" in result.message.lower()


class TestDuplicateTimeWindow:
    """Test that duplicate detection respects time windows."""

    @pytest.fixture
    def rules_engine(self):
        return RulesEngine()

    def test_fuzzy_duplicate_window_configurable(self, rules_engine):
        """
        Fuzzy duplicate detection should have a configurable time window.
        Invoices outside the window should not be flagged.
        """
        # Set a 7-day window for fuzzy duplicate detection
        rules_engine.fuzzy_duplicate_days = 7

        existing_invoices = [
            {
                "id": str(uuid4()),
                "invoice_number": "INV-001",
                "vendor_id": "V001",
                "vendor_name": "Acme Corp",
                "total_amount": Decimal("1000.00"),
                "invoice_date": date(2024, 1, 1),
                "document_hash": "hash_1",
            }
        ]

        # Invoice 10 days later - outside 7-day window
        new_invoice = {
            "invoice_number": "INV-002",
            "vendor_id": "V001",
            "vendor_name": "Acme Corp",
            "total_amount": Decimal("1000.00"),
            "invoice_date": date(2024, 1, 11),  # 10 days later
            "document_hash": "hash_2",
        }

        result = rules_engine.check_duplicate(new_invoice, existing_invoices)
        
        # Outside time window, should not be flagged as fuzzy duplicate
        assert result.is_valid is True, (
            f"Invoice outside duplicate window incorrectly flagged: {result.message}"
        )
