"""
FastAPI dependencies for dependency injection.

Provides database sessions, current user, tenant context, and service instances.
"""

from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.base import async_session_maker
from apps.api.schemas.auth import TokenPayload, UserRole

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """
    Validate JWT token and return current user payload.
    
    Raises HTTPException if token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        role = payload.get("role")
        
        if user_id is None or tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        
        return TokenPayload(
            sub=UUID(user_id),
            tenant_id=UUID(tenant_id),
            role=UserRole(role),
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[TokenPayload]:
    """Get current user if token provided, otherwise None."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory that checks if user has one of the allowed roles.
    
    Usage:
        @router.post("/admin", dependencies=[Depends(require_role(UserRole.CONTROLLER))])
    """
    async def role_checker(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role} not authorized for this action",
            )
        return current_user
    
    return role_checker


class TenantContext:
    """
    Context object providing tenant-scoped database access.
    
    All queries should use this to ensure proper tenant isolation.
    """
    
    def __init__(self, tenant_id: UUID, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
    
    def scoped_query(self, model):
        """Return a query filtered by tenant_id."""
        from sqlalchemy import select
        return select(model).where(model.tenant_id == self.tenant_id)


async def get_tenant_context(
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TenantContext:
    """Get tenant context with database session scoped to current tenant."""
    return TenantContext(tenant_id=current_user.tenant_id, db=db)
