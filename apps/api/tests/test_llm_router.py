"""
Tests for the LLM Router.

These tests use mocked database sessions to test routing logic in isolation.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from apps.api.models.cost import ModelTier
from apps.api.models.exception import ExceptionCategory
from apps.api.services.llm_router import LLMRouter, RouterContext, EscalationReason

TEST_TENANT_ID = uuid4()


def create_mock_db(spend_amount=0):
    """Create a mock database session that properly handles async."""
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = spend_amount
    
    async def mock_execute(*args, **kwargs):
        return mock_result
    
    db.execute = mock_execute
    return db


class TestTierSelection:
    """Tests for tier selection based on confidence."""
    
    @pytest.fixture
    def router(self):
        """Create router with mocked DB."""
        return LLMRouter(create_mock_db(0), TEST_TENANT_ID)
    
    @pytest.mark.asyncio
    async def test_high_confidence_selects_tier_a(self, router):
        """Test that high confidence (>90%) selects Tier A."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.95,
            invoice_amount=Decimal("100.00"),
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_A
        assert not decision.is_capped
    
    @pytest.mark.asyncio
    async def test_medium_confidence_selects_tier_b(self, router):
        """Test that medium confidence (70-90%) selects Tier B."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.80,
            invoice_amount=Decimal("100.00"),
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_B
    
    @pytest.mark.asyncio
    async def test_low_confidence_selects_tier_c(self, router):
        """Test that low confidence (<70%) selects Tier C."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.50,
            invoice_amount=Decimal("100.00"),
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_C


class TestMonetaryRiskEscalation:
    """Tests for monetary risk escalation."""
    
    @pytest.fixture
    def router(self):
        return LLMRouter(create_mock_db(0), TEST_TENANT_ID)
    
    @pytest.mark.asyncio
    async def test_high_amount_escalates_tier(self, router):
        """Test that high invoice amount escalates tier."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.95,  # Would be Tier A
            invoice_amount=Decimal("15000.00"),  # High risk (>$10,000)
        )
        
        decision = await router.route(context)
        
        # Should escalate from Tier A to Tier B
        assert decision.tier == ModelTier.TIER_B
        assert decision.escalation_reason == EscalationReason.HIGH_MONETARY_RISK
        assert decision.original_tier == ModelTier.TIER_A
    
    @pytest.mark.asyncio
    async def test_low_amount_no_escalation(self, router):
        """Test that low invoice amount doesn't escalate."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.95,
            invoice_amount=Decimal("500.00"),  # Low risk
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_A
        assert decision.escalation_reason is None


class TestComplexExceptionEscalation:
    """Tests for complex exception type escalation."""
    
    @pytest.fixture
    def router(self):
        return LLMRouter(create_mock_db(0), TEST_TENANT_ID)
    
    @pytest.mark.asyncio
    async def test_amount_variance_escalates(self, router):
        """Test that amount variance exception escalates tier."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.95,
            invoice_amount=Decimal("100.00"),
            exception_category=ExceptionCategory.AMOUNT_VARIANCE,
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_B
        assert decision.escalation_reason == EscalationReason.COMPLEX_EXCEPTION
    
    @pytest.mark.asyncio
    async def test_duplicate_exception_escalates(self, router):
        """Test that duplicate exception escalates tier."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.95,
            invoice_amount=Decimal("100.00"),
            exception_category=ExceptionCategory.DUPLICATE,
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_B
        assert decision.escalation_reason == EscalationReason.COMPLEX_EXCEPTION
    
    @pytest.mark.asyncio
    async def test_simple_exception_no_escalation(self, router):
        """Test that simple exception doesn't escalate."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.95,
            invoice_amount=Decimal("100.00"),
            exception_category=ExceptionCategory.VENDOR_MISMATCH,  # Simple
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_A


class TestRetryEscalation:
    """Tests for retry escalation."""
    
    @pytest.fixture
    def router(self):
        return LLMRouter(create_mock_db(0), TEST_TENANT_ID)
    
    @pytest.mark.asyncio
    async def test_retry_escalates_from_tier_a(self, router):
        """Test that retry escalates from Tier A to B."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.95,
            retry_count=1,
            previous_tier=ModelTier.TIER_A,
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_B
        assert decision.escalation_reason == EscalationReason.RETRY
    
    @pytest.mark.asyncio
    async def test_retry_escalates_from_tier_b(self, router):
        """Test that retry escalates from Tier B to C."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.80,
            retry_count=1,
            previous_tier=ModelTier.TIER_B,
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_C
        assert decision.escalation_reason == EscalationReason.RETRY
    
    @pytest.mark.asyncio
    async def test_retry_caps_at_tier_c(self, router):
        """Test that retry can't escalate beyond Tier C."""
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.50,
            retry_count=2,
            previous_tier=ModelTier.TIER_C,
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_C


class TestSpendCap:
    """Tests for spend cap enforcement."""
    
    @pytest.mark.asyncio
    async def test_spend_cap_enforces_tier_a(self):
        """When spend cap is reached, should use Tier A."""
        router = LLMRouter(create_mock_db(100), TEST_TENANT_ID)  # At $100 cap
        context = RouterContext(
            tenant_id=TEST_TENANT_ID,
            confidence_score=0.50,  # Would normally be Tier C
            invoice_amount=Decimal("100.00"),
        )
        
        decision = await router.route(context)
        
        assert decision.tier == ModelTier.TIER_A
        assert decision.is_capped
