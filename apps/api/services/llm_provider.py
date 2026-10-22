"""
The interface every model provider implements, and what a call returns.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any, Type

import structlog
from pydantic import BaseModel

from apps.api.models.cost import ModelTier

logger = structlog.get_logger()


class ModelUnavailable(Exception):
    """The model could not be reached, or answered with an error."""


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
