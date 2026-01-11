"""
Invoice list and detail routes.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_tenant_context, TenantContext
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.schemas.invoice import InvoiceResponse, InvoiceListResponse

router = APIRouter()


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[InvoiceStatus] = Query(None, alias="status"),
    vendor_id: Optional[str] = None,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List invoices with pagination and filtering."""
    # Base query
    query = select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
    count_query = select(func.count(Invoice.id)).where(Invoice.tenant_id == ctx.tenant_id)
    
    # Apply filters
    if status_filter:
        query = query.where(Invoice.status == status_filter)
        count_query = count_query.where(Invoice.status == status_filter)
    
    if vendor_id:
        query = query.where(Invoice.vendor_id == vendor_id)
        count_query = count_query.where(Invoice.vendor_id == vendor_id)
    
    # Get total count
    count_result = await ctx.db.execute(count_query)
    total = count_result.scalar_one()
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(Invoice.created_at.desc()).offset(offset).limit(page_size)
    
    result = await ctx.db.execute(query)
    invoices = result.scalars().all()
    
    pages = (total + page_size - 1) // page_size
    
    return InvoiceListResponse(
        items=[InvoiceResponse.model_validate(inv) for inv in invoices],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get invoice details by ID."""
    query = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.tenant_id == ctx.tenant_id,
    )
    result = await ctx.db.execute(query)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    return InvoiceResponse.model_validate(invoice)
