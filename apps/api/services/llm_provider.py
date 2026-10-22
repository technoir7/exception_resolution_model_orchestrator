"""
LLM Provider interface and MockLLM implementation.

Provides a pluggable interface for LLM providers with:
- Schema-first prompts
- Strict JSON validation
- Retry with escalation
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List, Type
from uuid import UUID

import structlog
from pydantic import BaseModel, ValidationError

from apps.api.models.cost import ModelTier

logger = structlog.get_logger()


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    parsed_json: Optional[Dict[str, Any]] = None
    model_id: str = ""
    model_tier: ModelTier = ModelTier.TIER_A
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    was_cached: bool = False
    raw_response: Optional[Dict[str, Any]] = None
    # What the call cost at list prices, where the provider reports it.
    cost_usd: Optional[Decimal] = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Implementations should handle:
    - API calls to the specific provider
    - Token counting
    - Error handling and retries
    """
    
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0 for deterministic)
            max_tokens: Maximum tokens in response
            response_schema: Optional Pydantic model for JSON validation
            
        Returns:
            LLMResponse with content and metadata
        """
        pass
    
    @abstractmethod
    def get_model_id(self) -> str:
        """Get the model identifier."""
        pass
    
    @abstractmethod
    def get_tier(self) -> ModelTier:
        """Get the model tier."""
        pass
    
    @abstractmethod
    def get_cost_per_1k_tokens(self) -> Decimal:
        """Get cost per 1000 tokens."""
        pass


# =============================================================================
# Mock LLM for Demo
# =============================================================================

class MockLLMScenario(str, Enum):
    """Scenarios for mock LLM responses."""
    CLEAN_MATCH = "clean_match"
    AMOUNT_VARIANCE = "amount_variance"
    QUANTITY_VARIANCE = "quantity_variance"
    MISSING_PO = "missing_po"
    DUPLICATE = "duplicate"
    VENDOR_MISMATCH = "vendor_mismatch"
    NEEDS_REVIEW = "needs_review"


@dataclass
class MockLLMConfig:
    """Configuration for mock LLM behavior."""
    default_scenario: MockLLMScenario = MockLLMScenario.CLEAN_MATCH
    failure_rate: float = 0.0  # Simulate failures
    latency_ms: int = 100
    tokens_per_response: int = 150


class MockLLM(LLMProvider):
    """
    Mock LLM that returns deterministic outputs for testing/demo.
    
    Inspects the input to determine what scenario to simulate,
    then returns appropriate structured responses.
    """
    
    def __init__(
        self,
        tier: ModelTier = ModelTier.TIER_A,
        config: Optional[MockLLMConfig] = None,
    ):
        self.tier = tier
        self.config = config or MockLLMConfig()
        self.logger = logger.bind(provider="mock_llm", tier=tier.value)
        
        # Cost per 1K tokens by tier
        self._costs = {
            ModelTier.TIER_A: Decimal("0.0001"),
            ModelTier.TIER_B: Decimal("0.001"),
            ModelTier.TIER_C: Decimal("0.01"),
        }
    
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        """
        Generate a mock completion.
        
        Analyzes the prompt to determine scenario and returns
        appropriate structured response.
        """
        self.logger.debug("Mock LLM called", prompt_length=len(prompt))
        
        # Determine scenario from prompt content
        scenario = self._determine_scenario(prompt)
        
        # Generate response based on scenario
        response_json = self._generate_response(scenario, prompt)
        
        # Validate against schema if provided
        if response_schema:
            try:
                validated = response_schema.model_validate(response_json)
                response_json = validated.model_dump()
            except ValidationError as e:
                self.logger.warning("Schema validation failed", error=str(e))
        
        content = json.dumps(response_json, indent=2)
        
        # Simulate token counts
        input_tokens = len(prompt.split()) * 2
        output_tokens = self.config.tokens_per_response
        
        return LLMResponse(
            content=content,
            parsed_json=response_json,
            model_id=self.get_model_id(),
            model_tier=self.tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=self.config.latency_ms,
            was_cached=False,
        )
    
    def _determine_scenario(self, prompt: str) -> MockLLMScenario:
        """Analyze prompt to determine which scenario to simulate."""
        prompt_lower = prompt.lower()
        
        # Look for keywords in the prompt
        if "variance" in prompt_lower and "amount" in prompt_lower:
            return MockLLMScenario.AMOUNT_VARIANCE
        elif "variance" in prompt_lower and "quantity" in prompt_lower:
            return MockLLMScenario.QUANTITY_VARIANCE
        elif "duplicate" in prompt_lower:
            return MockLLMScenario.DUPLICATE
        elif "missing" in prompt_lower and "po" in prompt_lower:
            return MockLLMScenario.MISSING_PO
        elif "vendor" in prompt_lower and "mismatch" in prompt_lower:
            return MockLLMScenario.VENDOR_MISMATCH
        elif "review" in prompt_lower or "exception" in prompt_lower:
            return MockLLMScenario.NEEDS_REVIEW
        
        return self.config.default_scenario
    
    def _generate_response(
        self, scenario: MockLLMScenario, prompt: str
    ) -> Dict[str, Any]:
        """Generate appropriate response for scenario."""
        
        base_response = {
            "analysis_complete": True,
            "timestamp": datetime.utcnow().isoformat(),
            "model": self.get_model_id(),
        }
        
        if scenario == MockLLMScenario.CLEAN_MATCH:
            return {
                **base_response,
                "decision": "approve",
                "confidence": 0.95,
                "match_type": "three_way",
                "reasoning": "Invoice matches PO and receipt. All amounts and quantities within tolerance.",
                "variances": [],
                "requires_review": False,
            }
        
        elif scenario == MockLLMScenario.AMOUNT_VARIANCE:
            return {
                **base_response,
                "decision": "review",
                "confidence": 0.75,
                "match_type": "partial",
                "reasoning": "Invoice amount differs from PO amount by more than allowed tolerance.",
                "variances": [
                    {
                        "type": "amount",
                        "field": "total_amount",
                        "invoice_value": "1080.00",
                        "po_value": "1000.00",
                        "variance_percent": 8.0,
                    }
                ],
                "requires_review": True,
                "suggested_action": "escalate_to_ap_manager",
            }
        
        elif scenario == MockLLMScenario.QUANTITY_VARIANCE:
            return {
                **base_response,
                "decision": "review",
                "confidence": 0.80,
                "match_type": "partial",
                "reasoning": "Line item quantities don't match receipt quantities.",
                "variances": [
                    {
                        "type": "quantity",
                        "line_number": 1,
                        "invoice_quantity": 12,
                        "receipt_quantity": 10,
                        "variance_percent": 20.0,
                    }
                ],
                "requires_review": True,
                "suggested_action": "verify_with_receiving",
            }
        
        elif scenario == MockLLMScenario.DUPLICATE:
            return {
                **base_response,
                "decision": "reject",
                "confidence": 0.98,
                "match_type": "none",
                "reasoning": "Invoice appears to be a duplicate of an existing invoice.",
                "duplicate_indicators": [
                    "Same invoice number",
                    "Same vendor",
                    "Same date",
                    "Same amount",
                ],
                "requires_review": True,
                "suggested_action": "mark_as_duplicate",
            }
        
        elif scenario == MockLLMScenario.MISSING_PO:
            return {
                **base_response,
                "decision": "review",
                "confidence": 0.60,
                "match_type": "none",
                "reasoning": "No matching purchase order found for this invoice.",
                "variances": [],
                "requires_review": True,
                "suggested_action": "request_po_from_requestor",
            }
        
        elif scenario == MockLLMScenario.VENDOR_MISMATCH:
            return {
                **base_response,
                "decision": "review",
                "confidence": 0.70,
                "match_type": "partial",
                "reasoning": "Invoice vendor does not match the PO vendor.",
                "variances": [
                    {
                        "type": "vendor",
                        "invoice_vendor": "ABC Supplies Inc",
                        "po_vendor": "ABC Supplies LLC",
                    }
                ],
                "requires_review": True,
                "suggested_action": "verify_vendor_entity",
            }
        
        else:  # NEEDS_REVIEW
            return {
                **base_response,
                "decision": "review",
                "confidence": 0.50,
                "match_type": "uncertain",
                "reasoning": "Unable to confidently match invoice. Manual review required.",
                "variances": [],
                "requires_review": True,
                "suggested_action": "manual_review",
            }
    
    def get_model_id(self) -> str:
        """Get mock model identifier based on tier."""
        tier_models = {
            ModelTier.TIER_A: "mock-gpt-3.5-turbo",
            ModelTier.TIER_B: "mock-gpt-4-mini",
            ModelTier.TIER_C: "mock-gpt-4",
        }
        return tier_models.get(self.tier, "mock-unknown")
    
    def get_tier(self) -> ModelTier:
        return self.tier
    
    def get_cost_per_1k_tokens(self) -> Decimal:
        return self._costs.get(self.tier, Decimal("0.001"))


# =============================================================================
# Response Schemas for LLM
# =============================================================================

class MatchDecision(str, Enum):
    """Possible match decisions."""
    APPROVE = "approve"
    REJECT = "reject"
    REVIEW = "review"


class VarianceDetail(BaseModel):
    """Details about a detected variance."""
    type: str
    field: Optional[str] = None
    line_number: Optional[int] = None
    invoice_value: Optional[str] = None
    po_value: Optional[str] = None
    receipt_value: Optional[str] = None
    variance_percent: Optional[float] = None


class InvoiceAnalysisResponse(BaseModel):
    """Expected response schema for invoice analysis."""
    analysis_complete: bool
    decision: MatchDecision
    confidence: float
    match_type: str
    reasoning: str
    variances: List[VarianceDetail] = []
    requires_review: bool
    suggested_action: Optional[str] = None


# Factory function for getting LLM provider
def get_llm_provider(tier: ModelTier) -> LLMProvider:
    """
    Factory function to get an LLM provider for the given tier.
    
    In production, this would return real providers.
    For MVP, returns MockLLM.
    """
    return MockLLM(tier=tier)
