"""
Matching Engine for 2-way and 3-way invoice matching.
"""

from dataclasses import dataclass, field as dc_field
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.invoice import Invoice
from apps.api.models.purchase_order import PurchaseOrder
from apps.api.models.receipt import Receipt

logger = structlog.get_logger()


class MatchType(str, Enum):
    TWO_WAY = "two_way"      # Invoice vs PO
    THREE_WAY = "three_way"  # Invoice vs PO vs Receipt
    NO_MATCH = "no_match"


class MatchStatus(str, Enum):
    FULL_MATCH = "full_match"
    PARTIAL_MATCH = "partial_match"
    NO_MATCH = "no_match"


@dataclass
class VarianceItem:
    field: str
    invoice_value: Any
    po_value: Optional[Any] = None
    receipt_value: Optional[Any] = None
    variance_amount: Optional[Decimal] = None
    variance_percent: Optional[float] = None
    within_tolerance: bool = True


@dataclass
class MatchResult:
    match_type: MatchType
    status: MatchStatus
    confidence: float
    variances: List[VarianceItem] = dc_field(default_factory=list)
    po: Optional[PurchaseOrder] = None
    receipt: Optional[Receipt] = None
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_type": self.match_type.value,
            "status": self.status.value,
            "confidence": self.confidence,
            "variances": [
                {
                    "field": v.field,
                    "invoice_value": str(v.invoice_value) if v.invoice_value else None,
                    "po_value": str(v.po_value) if v.po_value else None,
                    "receipt_value": str(v.receipt_value) if v.receipt_value else None,
                    "variance_percent": v.variance_percent,
                    "within_tolerance": v.within_tolerance,
                }
                for v in self.variances
            ],
            "summary": self.summary,
        }


class MatchingEngine:
    """Engine for 2-way and 3-way invoice matching."""
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
        self.amount_tolerance = settings.amount_tolerance_percent
        self.qty_tolerance = settings.quantity_tolerance_percent
    
    async def match(self, invoice: Invoice, po: Optional[PurchaseOrder] = None) -> MatchResult:
        """Perform matching for an invoice."""
        if not po and invoice.po_number:
            po = await self._lookup_po(invoice.po_number)
        
        if not po:
            return MatchResult(
                match_type=MatchType.NO_MATCH,
                status=MatchStatus.NO_MATCH,
                confidence=0.0,
                summary="No PO found for matching",
            )
        
        receipts = await self._lookup_receipts(po.po_number)
        
        if receipts:
            return await self._three_way_match(invoice, po, _combined(receipts))
        return await self._two_way_match(invoice, po)
    
    async def _two_way_match(self, invoice: Invoice, po: PurchaseOrder) -> MatchResult:
        """2-way match: Invoice vs PO."""
        variances = []
        
        # Amount comparison
        if invoice.total_amount and po.total_amount:
            amt_var = self._compare_amounts(
                "total_amount", invoice.total_amount, po.total_amount, None
            )
            if amt_var:
                variances.append(amt_var)
        
        # Vendor comparison
        if invoice.vendor_id != po.vendor_id:
            variances.append(VarianceItem(
                field="vendor_id",
                invoice_value=invoice.vendor_id,
                po_value=po.vendor_id,
                within_tolerance=False,
            ))
        
        # Currency comparison
        if invoice.currency != po.currency:
            variances.append(VarianceItem(
                field="currency",
                invoice_value=invoice.currency,
                po_value=po.currency,
                within_tolerance=False,
            ))
        
        # Determine status
        out_of_tolerance = [v for v in variances if not v.within_tolerance]
        if not out_of_tolerance:
            status = MatchStatus.FULL_MATCH
            confidence = 0.95
        elif len(out_of_tolerance) <= 2:
            status = MatchStatus.PARTIAL_MATCH
            confidence = 0.7
        else:
            status = MatchStatus.NO_MATCH
            confidence = 0.3
        
        return MatchResult(
            match_type=MatchType.TWO_WAY,
            status=status,
            confidence=confidence,
            variances=variances,
            po=po,
            summary=f"2-way match: {status.value} with {len(out_of_tolerance)} variance(s)",
        )
    
    async def _three_way_match(
        self, invoice: Invoice, po: PurchaseOrder, receipt: Receipt
    ) -> MatchResult:
        """3-way match: Invoice vs PO vs Receipt."""
        variances = []
        
        # Amount comparisons
        if invoice.total_amount:
            amt_var = self._compare_amounts(
                "total_amount",
                invoice.total_amount,
                po.total_amount,
                receipt.total_amount,
            )
            if amt_var:
                variances.append(amt_var)
        
        # Vendor check
        if invoice.vendor_id != po.vendor_id:
            variances.append(VarianceItem(
                field="vendor_id",
                invoice_value=invoice.vendor_id,
                po_value=po.vendor_id,
                within_tolerance=False,
            ))
        
        # Line item quantity matching
        if invoice.line_items and receipt.line_items:
            qty_variances = self._compare_line_quantities(
                invoice.line_items, po.line_items, receipt.line_items
            )
            variances.extend(qty_variances)
        
        out_of_tolerance = [v for v in variances if not v.within_tolerance]
        if not out_of_tolerance:
            status = MatchStatus.FULL_MATCH
            confidence = 0.98
        elif len(out_of_tolerance) <= 2:
            status = MatchStatus.PARTIAL_MATCH
            confidence = 0.75
        else:
            status = MatchStatus.NO_MATCH
            confidence = 0.4
        
        return MatchResult(
            match_type=MatchType.THREE_WAY,
            status=status,
            confidence=confidence,
            variances=variances,
            po=po,
            receipt=receipt,
            summary=f"3-way match: {status.value} with {len(out_of_tolerance)} variance(s)",
        )
    
    def _compare_amounts(
        self, field: str, inv_amt: Decimal, po_amt: Optional[Decimal], rcpt_amt: Optional[Decimal]
    ) -> Optional[VarianceItem]:
        if not po_amt:
            return None
        
        variance = abs(inv_amt - po_amt)
        variance_pct = float(variance / po_amt) if po_amt else 0
        within_tol = Decimal(str(variance_pct)) <= self.amount_tolerance
        
        if variance_pct > 0:
            return VarianceItem(
                field=field,
                invoice_value=inv_amt,
                po_value=po_amt,
                receipt_value=rcpt_amt,
                variance_amount=variance,
                variance_percent=variance_pct * 100,
                within_tolerance=within_tol,
            )
        return None
    
    def _compare_line_quantities(
        self, inv_lines: list, po_lines: list, rcpt_lines: list
    ) -> List[VarianceItem]:
        variances = []
        inv_by_line = {l.get("line_number"): l for l in inv_lines} if inv_lines else {}
        rcpt_by_line = {l.get("line_number"): l for l in rcpt_lines} if rcpt_lines else {}
        
        for line_num, inv_item in inv_by_line.items():
            rcpt_item = rcpt_by_line.get(line_num, {})
            inv_qty = Decimal(str(inv_item.get("quantity", 0)))
            rcpt_qty = Decimal(str(rcpt_item.get("quantity", inv_qty)))
            
            if rcpt_qty > 0:
                qty_var = abs(inv_qty - rcpt_qty) / rcpt_qty
                if qty_var > self.qty_tolerance:
                    variances.append(VarianceItem(
                        field=f"line_{line_num}_quantity",
                        invoice_value=inv_qty,
                        receipt_value=rcpt_qty,
                        variance_percent=float(qty_var * 100),
                        within_tolerance=False,
                    ))
        return variances
    
    async def _lookup_po(self, po_number: str) -> Optional[PurchaseOrder]:
        query = select(PurchaseOrder).where(
            and_(
                PurchaseOrder.tenant_id == self.tenant_id,
                PurchaseOrder.po_number == po_number,
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _lookup_receipts(self, po_number: str) -> List[Receipt]:
        """Every receipt on the PO: one delivered in several shipments has several."""
        query = select(Receipt).where(
            and_(
                Receipt.tenant_id == self.tenant_id,
                Receipt.po_number == po_number,
            )
        ).order_by(Receipt.receipt_date)
        result = await self.db.execute(query)
        return list(result.scalars().all())


def _combined(receipts: List[Receipt]) -> Receipt:
    """Everything received on a PO, as one receipt to match against. Built in
    memory only; it is never added to the session."""
    if len(receipts) == 1:
        return receipts[0]
    quantities: Dict[Any, Decimal] = {}
    descriptions: Dict[Any, str] = {}
    for receipt in receipts:
        for line in receipt.line_items or []:
            number = line.get("line_number")
            quantities[number] = quantities.get(number, Decimal(0)) + Decimal(str(line.get("quantity", 0)))
            descriptions[number] = line.get("description")
    return Receipt(
        tenant_id=receipts[0].tenant_id,
        receipt_number=", ".join(r.receipt_number for r in receipts),
        receipt_date=receipts[-1].receipt_date,
        po_number=receipts[0].po_number,
        vendor_id=receipts[0].vendor_id,
        total_amount=sum((r.total_amount for r in receipts), Decimal(0)),
        line_items=[{"line_number": n, "description": descriptions[n], "quantity": q} for n, q in quantities.items()],
    )
