"""
Invoice ingestion routes.
"""

import hashlib
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_db, get_current_user, TenantContext, get_tenant_context
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.schemas.auth import TokenPayload
from apps.api.schemas.invoice import InvoiceCreate, InvoiceResponse

router = APIRouter()


@router.post("/invoice", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def ingest_invoice(
    request: InvoiceCreate,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Ingest a new invoice for processing.
    
    Accepts either raw document content or canonical data directly.
    """
    # Compute document hash
    if request.document_content:
        content = request.document_content
    elif request.canonical_data:
        content = json.dumps(request.canonical_data.model_dump(), sort_keys=True, default=str)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either document_content or canonical_data is required",
        )
    
    document_hash = hashlib.sha256(content.encode()).hexdigest()
    
    # Create invoice
    invoice = Invoice(
        tenant_id=ctx.tenant_id,
        document_content=request.document_content,
        document_hash=document_hash,
        document_type=request.document_type,
        original_filename=request.original_filename,
        status=InvoiceStatus.PENDING,
    )
    
    # If canonical data provided, populate fields directly
    if request.canonical_data:
        cd = request.canonical_data
        invoice.invoice_number = cd.invoice_number
        invoice.invoice_date = cd.invoice_date
        invoice.due_date = cd.due_date
        invoice.vendor_id = cd.vendor_id
        invoice.vendor_name = cd.vendor_name
        invoice.po_number = cd.po_number
        invoice.currency = cd.currency
        invoice.subtotal = cd.subtotal
        invoice.tax_amount = cd.tax_amount
        invoice.total_amount = cd.total_amount
        invoice.line_items = [item.model_dump() for item in cd.line_items]
    
    ctx.db.add(invoice)
    await ctx.db.commit()
    await ctx.db.refresh(invoice)
    
    return InvoiceResponse.model_validate(invoice)
