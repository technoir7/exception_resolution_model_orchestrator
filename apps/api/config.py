"""
Application configuration using Pydantic Settings.

All configuration is loaded from environment variables with sensible defaults.
"""

from decimal import Decimal
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://ap_user:ap_password@localhost:5432/ap_reconciliation",
        alias="DATABASE_URL"
    )
    database_url_sync: str = Field(
        default="postgresql://ap_user:ap_password@localhost:5432/ap_reconciliation",
        alias="DATABASE_URL_SYNC"
    )
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    
    # Celery
    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND")
    
    # JWT Auth
    jwt_secret: str = Field(default="dev-secret-change-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, alias="JWT_EXPIRATION_HOURS")
    
    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        alias="CORS_ORIGINS"
    )
    
    # LLM Router Policy - Tier thresholds
    router_tier_a_confidence: float = Field(
        default=0.9,
        description="Confidence threshold for Tier A (cheapest) model",
        alias="ROUTER_TIER_A_CONFIDENCE"
    )
    router_tier_b_confidence: float = Field(
        default=0.7,
        description="Confidence threshold for Tier B (mid) model",
        alias="ROUTER_TIER_B_CONFIDENCE"
    )
    
    # LLM Router Policy - Risk thresholds
    router_high_risk_amount: Decimal = Field(
        default=Decimal("10000"),
        description="Amount threshold that triggers escalation to higher tier",
        alias="ROUTER_HIGH_RISK_AMOUNT"
    )
    
    # Review by models (apps/api/services/review.py)
    review_with_models: bool = Field(
        default=True,
        description="Have Claude review invoices; off, every flagged invoice goes to a person",
        alias="REVIEW_WITH_MODELS",
    )
    # Every invoice, not only the flagged ones: in the benchmark (evals/) that
    # is what caught payments to a new bank account and duplicates the rules
    # miss, for under a tenth of a cent an invoice with Haiku.
    review_scope: str = Field(
        default="everything",
        description="'flagged': models read the invoices the rules flag; 'everything': every invoice",
        alias="REVIEW_SCOPE",
    )
    # Off: in the benchmark the stronger model never changed Haiku's decision.
    review_second_opinion: bool = Field(
        default=False,
        description="Have the strongest model check large or unsure pays (apps/api/services/routing.py)",
        alias="REVIEW_SECOND_OPINION",
    )

    # How Claude is called (apps/api/services/claude.py)
    claude_via: str = Field(
        default="cli",
        description="'cli': the `claude` command on your login; 'api': the Claude API with ANTHROPIC_API_KEY",
        alias="CLAUDE_VIA",
    )
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY", repr=False)

    # LLM Router Policy - Cost caps
    router_tenant_daily_cap: Decimal = Field(
        default=Decimal("100.00"),
        description="Maximum daily LLM spend per tenant",
        alias="ROUTER_TENANT_DAILY_CAP"
    )
    
    # LLM Router - Retry settings
    router_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts with tier escalation",
        alias="ROUTER_MAX_RETRIES"
    )
    
    # Matching tolerances
    amount_tolerance_percent: Decimal = Field(
        default=Decimal("0.01"),
        description="Allowed variance for amount matching (1%)",
        alias="AMOUNT_TOLERANCE_PERCENT"
    )
    quantity_tolerance_percent: Decimal = Field(
        default=Decimal("0.05"),
        description="Allowed variance for quantity matching (5%)",
        alias="QUANTITY_TOLERANCE_PERCENT"
    )
    
    # Duplicate detection
    fuzzy_match_threshold: float = Field(
        default=0.85,
        description="Similarity threshold for fuzzy duplicate detection",
        alias="FUZZY_MATCH_THRESHOLD"
    )
    
    # Model tier costs (per 1K tokens)
    tier_a_cost_per_1k: Decimal = Field(default=Decimal("0.0001"), alias="TIER_A_COST_PER_1K")
    tier_b_cost_per_1k: Decimal = Field(default=Decimal("0.001"), alias="TIER_B_COST_PER_1K")
    tier_c_cost_per_1k: Decimal = Field(default=Decimal("0.01"), alias="TIER_C_COST_PER_1K")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
