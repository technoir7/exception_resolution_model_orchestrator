"""
Deterministic Rules Engine for invoice validation.

Implements validation rules that run before LLM processing:
- Required field validation
- Duplicate detection (exact hash + fuzzy matching)
- PO lookup
- Tolerance checks (amount/quantity)
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.invoice import Invoice
from apps.api.models.purchase_order import PurchaseOrder
from apps.api.schemas.invoice import InvoiceCanonical

logger = structlog.get_logger()


class RuleViolationType(str, Enum):
    """Types of rule violations."""
    MISSING_REQUIRED_FIELD = "missing_required_field"
    EXACT_DUPLICATE = "exact_duplicate"
    FUZZY_DUPLICATE = "fuzzy_duplicate"
    PO_NOT_FOUND = "po_not_found"
    PO_CLOSED = "po_closed"
    AMOUNT_EXCEEDS_TOLERANCE = "amount_exceeds_tolerance"
    QUANTITY_EXCEEDS_TOLERANCE = "quantity_exceeds_tolerance"
    INVALID_DATE = "invalid_date"
    VENDOR_MISMATCH = "vendor_mismatch"


@dataclass
class RuleViolation:
    """A single rule violation."""
    rule_type: RuleViolationType
    field: Optional[str] = None
    message: str = ""
    severity: str = "medium"  # low, medium, high
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RulesResult:
    """Result of running all validation rules."""
    passed: bool
    violations: List[RuleViolation] = field(default_factory=list)
    po_match: Optional[PurchaseOrder] = None
    warnings: List[str] = field(default_factory=list)
    
    def has_blocking_violations(self) -> bool:
        """Check if there are any high-severity violations."""
        return any(v.severity == "high" for v in self.violations)


class RulesEngine:
    """
    Deterministic rules engine for invoice validation.
    
    Runs a series of validation rules on invoices before
    LLM processing to catch obvious issues early.
    """
    
    REQUIRED_FIELDS = [
        "invoice_number",
        "invoice_date",
        "vendor_id",
        "total_amount",
    ]
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
    
    async def validate(self, invoice: Invoice) -> RulesResult:
        """
        Run all validation rules on an invoice.
        
        Returns RulesResult with pass/fail status and any violations.
        """
        violations: List[RuleViolation] = []
        warnings: List[str] = []
        po_match: Optional[PurchaseOrder] = None
        
        self.logger.info("Running rules engine", invoice_id=str(invoice.id))
        
        # 1. Required fields validation
        field_violations = self._validate_required_fields(invoice)
        violations.extend(field_violations)
        
        # 2. Date validation
        date_violations = self._validate_dates(invoice)
        violations.extend(date_violations)
        
        # 3. Duplicate detection (exact hash)
        exact_dup = await self._check_exact_duplicate(invoice)
        if exact_dup:
            violations.append(exact_dup)
        
        # 4. Duplicate detection (fuzzy match)
        fuzzy_dup = await self._check_fuzzy_duplicate(invoice)
        if fuzzy_dup:
            violations.append(fuzzy_dup)
        
        # 5. PO lookup (if PO number provided)
        if invoice.po_number:
            po_result = await self._lookup_po(invoice)
            if isinstance(po_result, RuleViolation):
                violations.append(po_result)
            else:
                po_match = po_result
                
                # 6. Check PO tolerances
                if po_match:
                    tolerance_violations = self._check_tolerances(invoice, po_match)
                    violations.extend(tolerance_violations)
                    
                    # 7. Check vendor match
                    vendor_violation = self._check_vendor_match(invoice, po_match)
                    if vendor_violation:
                        violations.append(vendor_violation)
        
        # Determine overall pass/fail
        passed = len(violations) == 0
        
        self.logger.info(
            "Rules engine complete",
            invoice_id=str(invoice.id),
            passed=passed,
            violation_count=len(violations),
        )
        
        return RulesResult(
            passed=passed,
            violations=violations,
            po_match=po_match,
            warnings=warnings,
        )
    
    def _validate_required_fields(self, invoice: Invoice) -> List[RuleViolation]:
        """Check that all required fields are present and non-empty."""
        violations = []
        
        for field_name in self.REQUIRED_FIELDS:
            value = getattr(invoice, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                violations.append(RuleViolation(
                    rule_type=RuleViolationType.MISSING_REQUIRED_FIELD,
                    field=field_name,
                    message=f"Required field '{field_name}' is missing or empty",
                    severity="high",
                ))
        
        # Check total_amount is positive
        if invoice.total_amount is not None and invoice.total_amount <= 0:
            violations.append(RuleViolation(
                rule_type=RuleViolationType.MISSING_REQUIRED_FIELD,
                field="total_amount",
                message="Total amount must be positive",
                severity="high",
            ))
        
        return violations
    
    def _validate_dates(self, invoice: Invoice) -> List[RuleViolation]:
        """Validate invoice dates are reasonable."""
        violations = []
        today = date.today()
        
        if invoice.invoice_date:
            # Invoice date shouldn't be in the far future
            if invoice.invoice_date > today + timedelta(days=30):
                violations.append(RuleViolation(
                    rule_type=RuleViolationType.INVALID_DATE,
                    field="invoice_date",
                    message="Invoice date is more than 30 days in the future",
                    severity="medium",
                ))
            
            # Invoice date shouldn't be too old (over 1 year)
            if invoice.invoice_date < today - timedelta(days=365):
                violations.append(RuleViolation(
                    rule_type=RuleViolationType.INVALID_DATE,
                    field="invoice_date",
                    message="Invoice date is more than 1 year old",
                    severity="low",
                ))
        
        if invoice.due_date and invoice.invoice_date:
            # Due date should be after invoice date
            if invoice.due_date < invoice.invoice_date:
                violations.append(RuleViolation(
                    rule_type=RuleViolationType.INVALID_DATE,
                    field="due_date",
                    message="Due date is before invoice date",
                    severity="medium",
                ))
        
        return violations
    
    async def _check_exact_duplicate(self, invoice: Invoice) -> Optional[RuleViolation]:
        """Check for exact duplicate by document hash."""
        query = select(Invoice).where(
            and_(
                Invoice.tenant_id == self.tenant_id,
                Invoice.document_hash == invoice.document_hash,
                Invoice.id != invoice.id,
            )
        )
        
        result = await self.db.execute(query)
        duplicate = result.scalar_one_or_none()
        
        if duplicate:
            return RuleViolation(
                rule_type=RuleViolationType.EXACT_DUPLICATE,
                message=f"Exact duplicate of invoice {duplicate.invoice_number}",
                severity="high",
                details={
                    "duplicate_invoice_id": str(duplicate.id),
                    "duplicate_invoice_number": duplicate.invoice_number,
                },
            )
        
        return None
    
    async def _check_fuzzy_duplicate(self, invoice: Invoice) -> Optional[RuleViolation]:
        """
        Check for fuzzy duplicate based on vendor, date, and amount.
        
        Looks for invoices with:
        - Same vendor
        - Same or similar date (within 7 days)
        - Same or similar amount (within 1%)
        """
        if not invoice.vendor_id or not invoice.invoice_date or not invoice.total_amount:
            return None
        
        date_range_start = invoice.invoice_date - timedelta(days=7)
        date_range_end = invoice.invoice_date + timedelta(days=7)
        
        amount_lower = invoice.total_amount * Decimal("0.99")
        amount_upper = invoice.total_amount * Decimal("1.01")
        
        query = select(Invoice).where(
            and_(
                Invoice.tenant_id == self.tenant_id,
                Invoice.vendor_id == invoice.vendor_id,
                Invoice.invoice_date >= date_range_start,
                Invoice.invoice_date <= date_range_end,
                Invoice.total_amount >= amount_lower,
                Invoice.total_amount <= amount_upper,
                Invoice.id != invoice.id,
            )
        )
        
        result = await self.db.execute(query)
        candidates = result.scalars().all()
        
        for candidate in candidates:
            # Additional fuzzy matching on invoice number
            if invoice.invoice_number and candidate.invoice_number:
                similarity = SequenceMatcher(
                    None,
                    invoice.invoice_number.lower(),
                    candidate.invoice_number.lower(),
                ).ratio()
                
                if similarity >= settings.fuzzy_match_threshold:
                    return RuleViolation(
                        rule_type=RuleViolationType.FUZZY_DUPLICATE,
                        message=f"Possible duplicate of invoice {candidate.invoice_number}",
                        severity="medium",
                        details={
                            "candidate_invoice_id": str(candidate.id),
                            "candidate_invoice_number": candidate.invoice_number,
                            "similarity_score": similarity,
                        },
                    )
        
        return None
    
    async def _lookup_po(
        self, invoice: Invoice
    ) -> Optional[PurchaseOrder] | RuleViolation:
        """
        Look up the referenced PO and validate it exists and is open.
        """
        if not invoice.po_number:
            return None
        
        query = select(PurchaseOrder).where(
            and_(
                PurchaseOrder.tenant_id == self.tenant_id,
                PurchaseOrder.po_number == invoice.po_number,
            )
        )
        
        result = await self.db.execute(query)
        po = result.scalar_one_or_none()
        
        if not po:
            return RuleViolation(
                rule_type=RuleViolationType.PO_NOT_FOUND,
                field="po_number",
                message=f"PO {invoice.po_number} not found",
                severity="high",
            )
        
        if po.status.value in ("closed", "cancelled"):
            return RuleViolation(
                rule_type=RuleViolationType.PO_CLOSED,
                field="po_number",
                message=f"PO {invoice.po_number} is {po.status.value}",
                severity="high",
            )
        
        return po
    
    def _check_tolerances(
        self, invoice: Invoice, po: PurchaseOrder
    ) -> List[RuleViolation]:
        """
        Check if invoice amounts/quantities are within tolerance of PO.
        """
        violations = []
        
        if invoice.total_amount and po.total_amount:
            variance = abs(invoice.total_amount - po.total_amount) / po.total_amount
            
            if variance > settings.amount_tolerance_percent:
                violations.append(RuleViolation(
                    rule_type=RuleViolationType.AMOUNT_EXCEEDS_TOLERANCE,
                    field="total_amount",
                    message=f"Amount variance {variance:.2%} exceeds tolerance {settings.amount_tolerance_percent:.2%}",
                    severity="high" if variance > Decimal("0.10") else "medium",
                    details={
                        "invoice_amount": str(invoice.total_amount),
                        "po_amount": str(po.total_amount),
                        "variance_percent": float(variance * 100),
                    },
                ))
        
        # Line item quantity checks
        if invoice.line_items and po.line_items:
            invoice_items = {
                item.get("line_number"): item 
                for item in (invoice.line_items if isinstance(invoice.line_items, list) else [])
            }
            po_items = {
                item.get("line_number"): item 
                for item in po.line_items
            }
            
            for line_num, inv_item in invoice_items.items():
                if line_num in po_items:
                    po_item = po_items[line_num]
                    inv_qty = Decimal(str(inv_item.get("quantity", 0)))
                    po_qty = Decimal(str(po_item.get("quantity", 0)))
                    
                    if po_qty > 0:
                        qty_variance = abs(inv_qty - po_qty) / po_qty
                        if qty_variance > settings.quantity_tolerance_percent:
                            violations.append(RuleViolation(
                                rule_type=RuleViolationType.QUANTITY_EXCEEDS_TOLERANCE,
                                field=f"line_items[{line_num}].quantity",
                                message=f"Line {line_num} quantity variance {qty_variance:.2%} exceeds tolerance",
                                severity="medium",
                                details={
                                    "line_number": line_num,
                                    "invoice_quantity": str(inv_qty),
                                    "po_quantity": str(po_qty),
                                },
                            ))
        
        return violations
    
    def _check_vendor_match(
        self, invoice: Invoice, po: PurchaseOrder
    ) -> Optional[RuleViolation]:
        """Check if invoice vendor matches PO vendor."""
        if invoice.vendor_id and po.vendor_id:
            if invoice.vendor_id != po.vendor_id:
                return RuleViolation(
                    rule_type=RuleViolationType.VENDOR_MISMATCH,
                    field="vendor_id",
                    message=f"Invoice vendor {invoice.vendor_id} doesn't match PO vendor {po.vendor_id}",
                    severity="high",
                    details={
                        "invoice_vendor_id": invoice.vendor_id,
                        "po_vendor_id": po.vendor_id,
                    },
                )
        return None
    
    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA-256 hash of document content."""
        return hashlib.sha256(content.encode()).hexdigest()
