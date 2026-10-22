"""
Vendor master record: who a vendor is and where its payments go.

The bank account on file is what an invoice's remit-to details are checked
against: a request to pay a different account is a classic invoice fraud.
"""

from typing import Optional

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import TenantScopedBase


class Vendor(TenantScopedBase):
    __tablename__ = "vendors"

    vendor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    remit_bank: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remit_account_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_vendor_tenant_vendor_id", "tenant_id", "vendor_id", unique=True),
    )
