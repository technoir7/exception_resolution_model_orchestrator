"""
Authentication schemas.
"""

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User roles for RBAC."""
    CONTROLLER = "controller"
    AP_MANAGER = "ap_manager"
    BPO_OPERATOR = "bpo_operator"


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: UUID = Field(..., description="User ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    role: UserRole = Field(..., description="User role")
    exp: Optional[int] = Field(None, description="Expiration timestamp")


class LoginRequest(BaseModel):
    """Login request body."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Login response with JWT token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token expiration in seconds")
    user: "UserInfo"


class UserInfo(BaseModel):
    """Basic user information."""
    id: UUID
    username: str
    role: UserRole
    tenant_id: UUID
    tenant_name: str


LoginResponse.model_rebuild()
