"""
Authentication routes.
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt

from apps.api.config import settings
from apps.api.dependencies import get_current_user
from apps.api.schemas.auth import LoginRequest, LoginResponse, TokenPayload, UserInfo, UserRole

router = APIRouter()

# Demo users for MVP
DEMO_USERS = {
    "controller": {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "password": "demo123",
        "role": UserRole.CONTROLLER,
        "tenant_id": UUID("00000000-0000-0000-0000-000000000100"),
        "tenant_name": "Demo Corp",
    },
    "ap_manager": {
        "id": UUID("00000000-0000-0000-0000-000000000002"),
        "password": "demo123",
        "role": UserRole.AP_MANAGER,
        "tenant_id": UUID("00000000-0000-0000-0000-000000000100"),
        "tenant_name": "Demo Corp",
    },
    "bpo_operator": {
        "id": UUID("00000000-0000-0000-0000-000000000003"),
        "password": "demo123",
        "role": UserRole.BPO_OPERATOR,
        "tenant_id": UUID("00000000-0000-0000-0000-000000000100"),
        "tenant_name": "Demo Corp",
    },
}


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login and receive JWT token."""
    user = DEMO_USERS.get(request.username)
    
    if not user or user["password"] != request.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    expires = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
    
    token_payload = {
        "sub": str(user["id"]),
        "tenant_id": str(user["tenant_id"]),
        "role": user["role"].value,
        "exp": expires,
    }
    
    access_token = jwt.encode(
        token_payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_hours * 3600,
        user=UserInfo(
            id=user["id"],
            username=request.username,
            role=user["role"],
            tenant_id=user["tenant_id"],
            tenant_name=user["tenant_name"],
        ),
    )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(current_user: TokenPayload = Depends(get_current_user)):
    """The user the token belongs to."""
    username, user = next(((name, u) for name, u in DEMO_USERS.items() if u["id"] == current_user.sub),
                          (None, None))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return UserInfo(id=user["id"], username=username, role=user["role"], tenant_id=user["tenant_id"],
                    tenant_name=user["tenant_name"])
