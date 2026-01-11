"""
Semantic cache model for caching LLM responses.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import TenantScopedBase


class SemanticCache(TenantScopedBase):
    """
    Cache for LLM responses keyed by normalized input and policy version.
    
    Enables cost savings by reusing responses for identical or
    semantically similar inputs.
    """
    
    __tablename__ = "semantic_cache"
    
    # Cache key components
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Version tracking
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Cached content
    normalized_input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cached_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Usage tracking
    hit_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Metadata
    original_cost_usd: Mapped[float] = mapped_column(nullable=False)
    savings_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)
    
    __table_args__ = (
        Index("ix_cache_tenant_key", "tenant_id", "cache_key", unique=True),
        Index("ix_cache_versions", "policy_version", "prompt_version", "model_id"),
        Index("ix_cache_expires", "expires_at"),
    )
    
    def record_hit(self) -> None:
        """Record a cache hit and update savings."""
        self.hit_count += 1
        self.last_hit_at = datetime.utcnow()
        self.savings_usd += self.original_cost_usd
    
    def __repr__(self) -> str:
        return f"<SemanticCache(id={self.id}, hits={self.hit_count})>"
