"""
Invoice schemas for API request/response.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.models.invoice import InvoiceStatus


class LineItem(BaseModel):
    """Invoice line item."""
    line_number: int = Field(..., ge=1)
    description: str = Field(..., max_length=500)
    quantity: Decimal = Field(..., ge=0)
    unit_price: Decimal = Field(...)
    amount: Decimal = Field(...)
    po_line_number: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "line_number": 1,
                "description": "Widget A",
                "quantity": "10.00",
                "unit_price": "25.00",
                "amount": "250.00",
                "po_line_number": 1
            }
        }


class RemitTo(BaseModel):
    """Where the invoice asks to be paid, checked against the vendor's record."""
    bank: str = Field(..., max_length=255)
    account_last4: str = Field(..., min_length=4, max_length=4)


class InvoiceCanonical(BaseModel):
    """Canonical invoice data structure."""
    invoice_number: str = Field(..., max_length=100)
    invoice_date: date
    due_date: Optional[date] = None
    vendor_id: str = Field(..., max_length=100)
    vendor_name: str = Field(..., max_length=255)
    po_number: Optional[str] = Field(None, max_length=100)
    currency: str = Field(default="USD", max_length=3)
    subtotal: Decimal
    tax_amount: Decimal = Field(default=Decimal("0"))
    total_amount: Decimal
    line_items: List[LineItem] = Field(default_factory=list)
    remit_to: Optional[RemitTo] = None
    notes: Optional[str] = Field(None, max_length=2000)
    service_period: Optional[date] = Field(None, description="First day of the period a service invoice bills")

    def review_details(self) -> dict:
        """What the model's review reads beyond the canonical fields."""
        details = {
            "remit_to": self.remit_to.model_dump() if self.remit_to else None,
            "notes": self.notes,
            "service_period": self.service_period.isoformat() if self.service_period else None,
        }
        return {k: v for k, v in details.items() if v is not None}
    
    class Config:
        json_schema_extra = {
            "example": {
                "invoice_number": "INV-2024-001",
                "invoice_date": "2024-01-15",
                "due_date": "2024-02-15",
                "vendor_id": "V001",
                "vendor_name": "Acme Supplies",
                "po_number": "PO-2024-001",
                "currency": "USD",
                "subtotal": "1000.00",
                "tax_amount": "80.00",
                "total_amount": "1080.00",
                "line_items": []
            }
        }


class InvoiceCreate(BaseModel):
    """Request to create/ingest an invoice."""
    # Raw document content (for MVP, accept text/JSON)
    document_content: Optional[str] = Field(None, description="Raw text content")
    document_type: str = Field(default="text", description="text, json, or pdf")
    original_filename: Optional[str] = None
    
    # Or provide canonical data directly
    canonical_data: Optional[InvoiceCanonical] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_type": "json",
                "canonical_data": {
                    "invoice_number": "INV-2024-001",
                    "invoice_date": "2024-01-15",
                    "vendor_id": "V001",
                    "vendor_name": "Acme Supplies",
                    "po_number": "PO-2024-001",
                    "currency": "USD",
                    "subtotal": "1000.00",
                    "tax_amount": "80.00",
                    "total_amount": "1080.00"
                }
            }
        }


class InvoiceResponse(BaseModel):
    """Invoice response."""
    id: UUID
    tenant_id: UUID
    status: InvoiceStatus
    
    # Document info
    document_hash: str
    document_type: str
    original_filename: Optional[str] = None
    
    # Canonical fields
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    po_number: Optional[str] = None
    currency: str = "USD"
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    line_items: Optional[List[LineItem]] = None
    # Remit-to, notes, service period, and the model that read a PDF
    extracted_data: Optional[dict] = None
    
    # Processing info
    validation_errors: Optional[dict] = None
    match_result: Optional[dict] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Paginated list of invoices."""
    items: List[InvoiceResponse]
    total: int
    page: int
    page_size: int
    pages: int


class InvoiceSummary(BaseModel):
    """Brief invoice summary for lists."""
    id: UUID
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    total_amount: Optional[Decimal] = None
    status: InvoiceStatus
    created_at: datetime
    
    class Config:
        from_attributes = True
