"""
Invoice ingestion routes.
"""

import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.api.config import settings
from apps.api.dependencies import TenantContext, get_tenant_context
from apps.api.schemas.invoice import InvoiceCreate, InvoiceResponse
from apps.api.services import extraction, intake
from apps.api.services.claude_provider import ClaudeCLI, ClaudeCLIError


router = APIRouter()


@router.post("/invoice", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def ingest_invoice(
    request: InvoiceCreate,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Ingest an invoice given as data."""
    if not request.canonical_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="canonical_data is required; send a PDF to /ingest/invoice-pdf")
    data = request.canonical_data
    document_hash = (hashlib.sha256(request.document_content.encode()).hexdigest() if request.document_content
                     else intake.hash_of_data(data))
    invoice = intake.new_invoice(ctx.tenant_id, data, document_hash, request.document_type,
                                 request.original_filename, request.document_content)
    ctx.db.add(invoice)
    await ctx.db.commit()
    await ctx.db.refresh(invoice)
    return InvoiceResponse.model_validate(invoice)


@router.post("/invoice-pdf", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED,
             openapi_extra={"requestBody": {"content": {"application/pdf": {"schema": {"type": "string",
                                                                                     "format": "binary"}}}}})
async def ingest_invoice_pdf(
    request: Request,
    filename: Optional[str] = None,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Ingest an invoice PDF, sent as the request body: Claude reads it into
    the same invoice data as /ingest/invoice takes."""
    if not settings.review_with_models:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="reading PDFs needs a model (REVIEW_WITH_MODELS is off)")
    try:
        invoice = await intake.ingest_pdf(ctx.db, ctx.tenant_id, await request.body(), ClaudeCLI(intake.READER), filename)
    except intake.NotAcceptable as error:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error))
    except (extraction.UnreadableInvoice, intake.UnknownVendor) as error:
        await ctx.db.commit()  # the model calls were made, and are paid for
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))
    except intake.SpendCapReached as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error))
    except ClaudeCLIError as error:
        await ctx.db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"the model could not be reached: {error}")
    await ctx.db.commit()
    await ctx.db.refresh(invoice)
    return InvoiceResponse.model_validate(invoice)
