"""
Cache Service for semantic caching of LLM responses.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.cache import SemanticCache

logger = structlog.get_logger()


class CacheService:
    """Service for semantic caching of LLM responses."""
    
    DEFAULT_TTL_HOURS = 24 * 7  # 1 week
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
    
    async def get(
        self,
        normalized_input: Dict[str, Any],
        policy_version: str,
        prompt_version: str,
        model_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get cached response if available."""
        cache_key = self._compute_cache_key(
            normalized_input, policy_version, prompt_version, model_id
        )
        
        query = select(SemanticCache).where(
            and_(
                SemanticCache.tenant_id == self.tenant_id,
                SemanticCache.cache_key == cache_key,
                SemanticCache.expires_at > datetime.utcnow(),
            )
        )
        
        result = await self.db.execute(query)
        cached = result.scalar_one_or_none()
        
        if cached:
            cached.record_hit()
            self.logger.debug("Cache hit", cache_key=cache_key[:16])
            return cached.cached_output
        
        return None
    
    async def set(
        self,
        normalized_input: Dict[str, Any],
        output: Dict[str, Any],
        policy_version: str,
        prompt_version: str,
        model_id: str,
        cost_usd: float,
        ttl_hours: Optional[int] = None,
    ) -> SemanticCache:
        """Store a response in cache."""
        cache_key = self._compute_cache_key(
            normalized_input, policy_version, prompt_version, model_id
        )
        input_hash = self._compute_hash(normalized_input)
        
        ttl = ttl_hours or self.DEFAULT_TTL_HOURS
        expires_at = datetime.utcnow() + timedelta(hours=ttl)
        
        # Check for existing entry
        query = select(SemanticCache).where(
            and_(
                SemanticCache.tenant_id == self.tenant_id,
                SemanticCache.cache_key == cache_key,
            )
        )
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.cached_output = output
            existing.expires_at = expires_at
            self.logger.debug("Cache updated", cache_key=cache_key[:16])
            return existing
        
        cache_entry = SemanticCache(
            tenant_id=self.tenant_id,
            cache_key=cache_key,
            input_hash=input_hash,
            policy_version=policy_version,
            prompt_version=prompt_version,
            model_id=model_id,
            normalized_input=normalized_input,
            cached_output=output,
            original_cost_usd=cost_usd,
            expires_at=expires_at,
        )
        
        self.db.add(cache_entry)
        self.logger.debug("Cache set", cache_key=cache_key[:16])
        return cache_entry
    
    def _compute_cache_key(
        self,
        normalized_input: Dict[str, Any],
        policy_version: str,
        prompt_version: str,
        model_id: str,
    ) -> str:
        """Compute cache key from input and version info."""
        key_parts = {
            "input": normalized_input,
            "policy": policy_version,
            "prompt": prompt_version,
            "model": model_id,
        }
        return self._compute_hash(key_parts)
    
    @staticmethod
    def _compute_hash(data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of data."""
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    async def invalidate(self, cache_key: str) -> bool:
        """Invalidate a cache entry."""
        query = select(SemanticCache).where(
            and_(
                SemanticCache.tenant_id == self.tenant_id,
                SemanticCache.cache_key == cache_key,
            )
        )
        result = await self.db.execute(query)
        cached = result.scalar_one_or_none()
        
        if cached:
            await self.db.delete(cached)
            return True
        return False
