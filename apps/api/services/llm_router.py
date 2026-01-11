"""
Cost-aware LLM Router.

Routes requests to appropriate model tiers based on:
- Exception type and confidence level
- Monetary risk (invoice amount)
- Tenant spend caps
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.cost import CostEvent, ModelTier
from apps.api.models.exception import ExceptionCategory
from apps.api.services.llm_provider import LLMProvider, LLMResponse, MockLLM

logger = structlog.get_logger()


class EscalationReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    HIGH_MONETARY_RISK = "high_monetary_risk"
    COMPLEX_EXCEPTION = "complex_exception"
    VALIDATION_FAILED = "validation_failed"
    RETRY = "retry"


@dataclass
class RouterDecision:
    tier: ModelTier
    model_id: str
    reasoning: str
    escalation_reason: Optional[EscalationReason] = None
    original_tier: Optional[ModelTier] = None
    spend_remaining: Optional[Decimal] = None
    is_capped: bool = False


@dataclass
class RouterContext:
    tenant_id: UUID
    invoice_id: Optional[UUID] = None
    invoice_amount: Decimal = Decimal("0")
    exception_category: Optional[ExceptionCategory] = None
    confidence_score: float = 0.0
    retry_count: int = 0
    previous_tier: Optional[ModelTier] = None


class LLMRouter:
    COMPLEX_EXCEPTIONS = {
        ExceptionCategory.AMOUNT_VARIANCE,
        ExceptionCategory.LLM_VALIDATION_FAILED,
        ExceptionCategory.DUPLICATE,
    }
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(component="llm_router", tenant_id=str(tenant_id))
        self.tier_a_threshold = settings.router_tier_a_confidence
        self.tier_b_threshold = settings.router_tier_b_confidence
        self.high_risk_amount = settings.router_high_risk_amount
        self.daily_cap = settings.router_tenant_daily_cap
        self.max_retries = settings.router_max_retries
        
        # Circuit breaker configuration
        self.circuit_breaker_threshold = 5  # failures before opening circuit
        self.max_consecutive_failures = 5
        self.circuit_states: dict[ModelTier, str] = {
            ModelTier.TIER_A: "closed",
            ModelTier.TIER_B: "closed",
            ModelTier.TIER_C: "closed",
        }
        self._failure_counts: dict[ModelTier, int] = {
            ModelTier.TIER_A: 0,
            ModelTier.TIER_B: 0,
            ModelTier.TIER_C: 0,
        }
        
        # Retry configuration
        self.base_retry_delay = 1.0  # seconds
        self.retry_limit = settings.router_max_retries
        self.charge_failed_calls = False  # Don't charge budget for failures
        self.failed_call_cost = Decimal("0")  # Cost attribution for failed calls
        
        # Budget tracking
        self.remaining_budget: Optional[Decimal] = None
    
    async def route(self, context: RouterContext) -> RouterDecision:
        spend_today = await self._get_tenant_spend_today()
        spend_remaining = self.daily_cap - spend_today
        is_capped = spend_remaining <= 0
        
        if is_capped:
            return RouterDecision(
                tier=ModelTier.TIER_A,
                model_id="mock-gpt-3.5-turbo",
                reasoning=f"Spend cap reached (${spend_today:.2f}/${self.daily_cap})",
                is_capped=True,
                spend_remaining=spend_remaining,
            )
        
        if context.retry_count > 0 and context.previous_tier:
            return self._escalate_tier(context, spend_remaining)
        
        tier = self._select_tier_by_confidence(context.confidence_score)
        escalation_reason = None
        original_tier = None
        
        if context.invoice_amount >= self.high_risk_amount and tier == ModelTier.TIER_A:
            original_tier = tier
            tier = ModelTier.TIER_B
            escalation_reason = EscalationReason.HIGH_MONETARY_RISK
        
        if context.exception_category in self.COMPLEX_EXCEPTIONS and tier != ModelTier.TIER_C:
            original_tier = original_tier or tier
            tier = ModelTier.TIER_B if tier == ModelTier.TIER_A else ModelTier.TIER_C
            escalation_reason = EscalationReason.COMPLEX_EXCEPTION
        
        return RouterDecision(
            tier=tier,
            model_id=self._get_model_id(tier),
            reasoning=f"Selected {tier.value}: conf={context.confidence_score:.2f}",
            escalation_reason=escalation_reason,
            original_tier=original_tier,
            spend_remaining=spend_remaining,
        )
    
    def _select_tier_by_confidence(self, confidence: float) -> ModelTier:
        if confidence >= self.tier_a_threshold:
            return ModelTier.TIER_A
        elif confidence >= self.tier_b_threshold:
            return ModelTier.TIER_B
        return ModelTier.TIER_C
    
    def _escalate_tier(self, context: RouterContext, spend_remaining: Decimal) -> RouterDecision:
        tier_order = [ModelTier.TIER_A, ModelTier.TIER_B, ModelTier.TIER_C]
        current_idx = tier_order.index(context.previous_tier) if context.previous_tier else 0
        new_tier = tier_order[min(current_idx + 1, 2)]
        return RouterDecision(
            tier=new_tier,
            model_id=self._get_model_id(new_tier),
            reasoning=f"Retry #{context.retry_count}: escalated to {new_tier.value}",
            escalation_reason=EscalationReason.RETRY,
            original_tier=context.previous_tier,
            spend_remaining=spend_remaining,
        )
    
    def _get_model_id(self, tier: ModelTier) -> str:
        return {
            ModelTier.TIER_A: "mock-gpt-3.5-turbo",
            ModelTier.TIER_B: "mock-gpt-4-mini",
            ModelTier.TIER_C: "mock-gpt-4",
        }.get(tier, "mock-unknown")
    
    async def _get_tenant_spend_today(self) -> Decimal:
        query = select(func.coalesce(func.sum(CostEvent.cost_usd), 0)).where(
            and_(
                CostEvent.tenant_id == self.tenant_id,
                func.date(CostEvent.event_timestamp) == date.today(),
            )
        )
        result = await self.db.execute(query)
        return Decimal(str(result.scalar_one() or 0))
    
    async def get_provider(self, decision: RouterDecision) -> LLMProvider:
        return MockLLM(tier=decision.tier)
    
    async def call_with_retry(
        self, context: RouterContext, prompt: str, system_prompt: Optional[str] = None
    ) -> tuple[LLMResponse, RouterDecision]:
        last_error = None
        for attempt in range(self.max_retries):
            context.retry_count = attempt
            decision = await self.route(context)
            provider = await self.get_provider(decision)
            try:
                response = await provider.complete(prompt=prompt, system_prompt=system_prompt)
                if response.parsed_json is None:
                    raise ValueError("Invalid JSON response")
                return response, decision
            except Exception as e:
                last_error = e
                context.previous_tier = decision.tier
        raise last_error or Exception("LLM call failed")
