"""
Tests for the Rules Engine.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.models.purchase_order import PurchaseOrder, POStatus
from apps.api.services.rules_engine import RulesEngine, RuleViolationType
from apps.api.tests.conftest import TEST_TENANT_ID


class TestRequiredFieldValidation:
    """Tests for required field validation."""
    
    @pytest.mark.asyncio
    async def test_missing_invoice_number(self, db_session):
        """Test that missing invoice number is detected."""
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="test123",
            status=InvoiceStatus.PENDING,
            invoice_number=None,  # Missing
            invoice_date=date.today(),
            vendor_id="V001",
            total_amount=Decimal("100.00"),
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        assert not result.passed
        assert any(
            v.rule_type == RuleViolationType.MISSING_REQUIRED_FIELD and v.field == "invoice_number"
            for v in result.violations
        )
    
    @pytest.mark.asyncio
    async def test_missing_total_amount(self, db_session):
        """Test that missing total amount is detected."""
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="test456",
            status=InvoiceStatus.PENDING,
            invoice_number="INV-001",
            invoice_date=date.today(),
            vendor_id="V001",
            total_amount=None,  # Missing
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        assert not result.passed
        assert any(v.field == "total_amount" for v in result.violations)
    
    @pytest.mark.asyncio
    async def test_all_fields_present_passes(self, db_session):
        """Test that invoice with all required fields passes."""
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="test789",
            status=InvoiceStatus.PENDING,
            invoice_number="INV-002",
            invoice_date=date.today(),
            vendor_id="V001",
            total_amount=Decimal("100.00"),
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        # Should pass required field validation
        missing_field_violations = [
            v for v in result.violations 
            if v.rule_type == RuleViolationType.MISSING_REQUIRED_FIELD
        ]
        assert len(missing_field_violations) == 0


class TestDuplicateDetection:
    """Tests for duplicate detection."""
    
    @pytest.mark.asyncio
    async def test_exact_duplicate_detected(self, db_session):
        """Test that exact duplicate by hash is detected."""
        # Create first invoice
        invoice1 = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="duplicate_hash",
            status=InvoiceStatus.APPROVED,
            invoice_number="INV-100",
            invoice_date=date.today(),
            vendor_id="V001",
            total_amount=Decimal("500.00"),
        )
        db_session.add(invoice1)
        await db_session.flush()
        
        # Create duplicate invoice
        invoice2 = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="duplicate_hash",  # Same hash
            status=InvoiceStatus.PENDING,
            invoice_number="INV-101",
            invoice_date=date.today(),
            vendor_id="V001",
            total_amount=Decimal("500.00"),
        )
        db_session.add(invoice2)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice2)
        
        assert not result.passed
        assert any(v.rule_type == RuleViolationType.EXACT_DUPLICATE for v in result.violations)
    
    @pytest.mark.asyncio
    async def test_unique_hash_passes(self, db_session):
        """Test that unique hash doesn't trigger duplicate detection."""
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="unique_hash_12345",
            status=InvoiceStatus.PENDING,
            invoice_number="INV-200",
            invoice_date=date.today(),
            vendor_id="V001",
            total_amount=Decimal("100.00"),
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        duplicate_violations = [
            v for v in result.violations 
            if v.rule_type in (RuleViolationType.EXACT_DUPLICATE, RuleViolationType.FUZZY_DUPLICATE)
        ]
        assert len(duplicate_violations) == 0


class TestPOLookup:
    """Tests for PO lookup validation."""
    
    @pytest.mark.asyncio
    async def test_po_not_found(self, db_session):
        """Test that missing PO is detected."""
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="po_test_1",
            status=InvoiceStatus.PENDING,
            invoice_number="INV-300",
            invoice_date=date.today(),
            vendor_id="V001",
            po_number="PO-NONEXISTENT",
            total_amount=Decimal("100.00"),
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        assert not result.passed
        assert any(v.rule_type == RuleViolationType.PO_NOT_FOUND for v in result.violations)
    
    @pytest.mark.asyncio
    async def test_po_found_passes(self, db_session, sample_po):
        """Test that valid PO lookup passes."""
        db_session.add(sample_po)
        await db_session.flush()
        
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="po_test_2",
            status=InvoiceStatus.PENDING,
            invoice_number="INV-301",
            invoice_date=date.today(),
            vendor_id="V001",
            po_number=sample_po.po_number,
            total_amount=Decimal("1000.00"),
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        po_violations = [
            v for v in result.violations 
            if v.rule_type in (RuleViolationType.PO_NOT_FOUND, RuleViolationType.PO_CLOSED)
        ]
        assert len(po_violations) == 0
        assert result.po_match is not None


class TestToleranceChecks:
    """Tests for amount tolerance validation."""
    
    @pytest.mark.asyncio
    async def test_amount_within_tolerance(self, db_session, sample_po):
        """Test that amount within tolerance passes."""
        db_session.add(sample_po)
        await db_session.flush()
        
        # 0.5% variance - within 1% tolerance
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="tolerance_test_1",
            status=InvoiceStatus.PENDING,
            invoice_number="INV-400",
            invoice_date=date.today(),
            vendor_id="V001",
            po_number=sample_po.po_number,
            total_amount=Decimal("1005.00"),  # 0.5% over
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        amount_violations = [
            v for v in result.violations 
            if v.rule_type == RuleViolationType.AMOUNT_EXCEEDS_TOLERANCE
        ]
        assert len(amount_violations) == 0
    
    @pytest.mark.asyncio
    async def test_amount_exceeds_tolerance(self, db_session, sample_po):
        """Test that amount exceeding tolerance is detected."""
        db_session.add(sample_po)
        await db_session.flush()
        
        # 10% variance - exceeds tolerance
        invoice = Invoice(
            id=uuid4(),
            tenant_id=TEST_TENANT_ID,
            document_hash="tolerance_test_2",
            status=InvoiceStatus.PENDING,
            invoice_number="INV-401",
            invoice_date=date.today(),
            vendor_id="V001",
            po_number=sample_po.po_number,
            total_amount=Decimal("1100.00"),  # 10% over
        )
        db_session.add(invoice)
        await db_session.flush()
        
        engine = RulesEngine(db_session, TEST_TENANT_ID)
        result = await engine.validate(invoice)
        
        assert not result.passed
        assert any(v.rule_type == RuleViolationType.AMOUNT_EXCEEDS_TOLERANCE for v in result.violations)
