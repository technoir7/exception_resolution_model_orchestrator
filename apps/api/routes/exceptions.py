"""
Exception queue routes.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from apps.api.dependencies import get_tenant_context, get_current_user, TenantContext
from apps.api.models.exception import ExceptionCase, ExceptionStatus, ExceptionCategory
from apps.api.schemas.auth import TokenPayload
from apps.api.schemas.exception import (
    ExceptionResponse,
    ExceptionListResponse,
    ExceptionResolveRequest,
)
from apps.api.services.exception_handler import RESOLUTIONS, ExceptionHandler

router = APIRouter()


async def _find(ctx: TenantContext, exception_id: UUID) -> ExceptionCase:
    """The exception with its invoice loaded, as of now."""
    exception = (await ctx.db.execute(
        select(ExceptionCase)
        .options(selectinload(ExceptionCase.invoice))
        .where(ExceptionCase.id == exception_id, ExceptionCase.tenant_id == ctx.tenant_id)
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    return exception


@router.get("", response_model=ExceptionListResponse)
async def list_exceptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[ExceptionStatus] = Query(None, alias="status"),
    category: Optional[ExceptionCategory] = None,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List exceptions with pagination and filtering."""
    # Base query
    query = select(ExceptionCase).where(ExceptionCase.tenant_id == ctx.tenant_id)
    count_query = select(func.count(ExceptionCase.id)).where(ExceptionCase.tenant_id == ctx.tenant_id)
    
    # Count open and SLA breached
    open_count_query = select(func.count(ExceptionCase.id)).where(
        ExceptionCase.tenant_id == ctx.tenant_id,
        ExceptionCase.status == ExceptionStatus.OPEN,
    )
    sla_count_query = select(func.count(ExceptionCase.id)).where(
        ExceptionCase.tenant_id == ctx.tenant_id,
        ExceptionCase.sla_breached == True,
    )
    
    # Apply filters
    if status_filter:
        query = query.where(ExceptionCase.status == status_filter)
        count_query = count_query.where(ExceptionCase.status == status_filter)
    
    if category:
        query = query.where(ExceptionCase.category == category)
        count_query = count_query.where(ExceptionCase.category == category)
    
    # Get counts
    total = (await ctx.db.execute(count_query)).scalar_one()
    open_count = (await ctx.db.execute(open_count_query)).scalar_one()
    sla_count = (await ctx.db.execute(sla_count_query)).scalar_one()
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = (query.options(selectinload(ExceptionCase.invoice))
             .order_by(ExceptionCase.created_at.desc()).offset(offset).limit(page_size))
    
    result = await ctx.db.execute(query)
    exceptions = result.scalars().all()
    
    pages = (total + page_size - 1) // page_size
    
    return ExceptionListResponse(
        items=[ExceptionResponse.model_validate(exc) for exc in exceptions],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        open_count=open_count,
        sla_breached_count=sla_count,
    )


@router.get("/{exception_id}", response_model=ExceptionResponse)
async def get_exception(
    exception_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get exception details by ID."""
    return ExceptionResponse.model_validate(await _find(ctx, exception_id))


@router.post("/{exception_id}/resolve", response_model=ExceptionResponse)
async def resolve_exception(
    exception_id: UUID,
    request: ExceptionResolveRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: TokenPayload = Depends(get_current_user),
):
    """Resolve an exception with human override."""
    exception = await _find(ctx, exception_id)
    
    if exception.status == ExceptionStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exception is already resolved",
        )
    
    if request.resolution_action not in RESOLUTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resolution action. Must be one of: {', '.join(RESOLUTIONS)}",
        )
    
    handler = ExceptionHandler(ctx.db, ctx.tenant_id)
    await handler.resolve_exception(
        exception=exception,
        resolution=request.resolution,
        resolution_action=request.resolution_action,
        resolved_by=current_user.sub,
    )
    
    await ctx.db.commit()
    return ExceptionResponse.model_validate(await _find(ctx, exception_id))
