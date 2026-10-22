"""
Exception Handler for creating and managing exception cases.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.exception import (
    ExceptionCase,
    ExceptionCategory,
    ExceptionSeverity,
    ExceptionStatus,
    OwnerRole,
    EXCEPTION_SLA_HOURS,
    EXCEPTION_OWNER_ROLE,
)
from apps.api.models.audit import AuditStep
from apps.api.models.invoice import Invoice, InvoiceStatus
from apps.api.services.audit_service import AuditService
from apps.api.services.rules_engine import RuleViolation, RuleViolationType

logger = structlog.get_logger()

# What a person's decision does to the exception and to its invoice. Escalating
# leaves the invoice held, for someone more senior to decide.
RESOLUTIONS = {
    "approve": (ExceptionStatus.RESOLVED, InvoiceStatus.APPROVED),
    "reject": (ExceptionStatus.RESOLVED, InvoiceStatus.REJECTED),
    "reprocess": (ExceptionStatus.RESOLVED, InvoiceStatus.PENDING),
    "escalate": (ExceptionStatus.ESCALATED, None),
}


# Mapping from rule violation types to exception categories
VIOLATION_TO_CATEGORY = {
    RuleViolationType.MISSING_REQUIRED_FIELD: ExceptionCategory.MISSING_FIELDS,
    RuleViolationType.EXACT_DUPLICATE: ExceptionCategory.DUPLICATE,
    RuleViolationType.FUZZY_DUPLICATE: ExceptionCategory.DUPLICATE,
    RuleViolationType.PO_NOT_FOUND: ExceptionCategory.MISSING_PO,
    RuleViolationType.PO_CLOSED: ExceptionCategory.MISSING_PO,
    RuleViolationType.AMOUNT_EXCEEDS_TOLERANCE: ExceptionCategory.AMOUNT_VARIANCE,
    RuleViolationType.QUANTITY_EXCEEDS_TOLERANCE: ExceptionCategory.QUANTITY_VARIANCE,
    RuleViolationType.VENDOR_MISMATCH: ExceptionCategory.VENDOR_MISMATCH,
}

SEVERITY_BY_VIOLATION = {
    RuleViolationType.EXACT_DUPLICATE: ExceptionSeverity.HIGH,
    RuleViolationType.MISSING_REQUIRED_FIELD: ExceptionSeverity.HIGH,
    RuleViolationType.PO_NOT_FOUND: ExceptionSeverity.HIGH,
    RuleViolationType.AMOUNT_EXCEEDS_TOLERANCE: ExceptionSeverity.HIGH,
    RuleViolationType.FUZZY_DUPLICATE: ExceptionSeverity.MEDIUM,
    RuleViolationType.QUANTITY_EXCEEDS_TOLERANCE: ExceptionSeverity.MEDIUM,
    RuleViolationType.PO_CLOSED: ExceptionSeverity.MEDIUM,
    RuleViolationType.VENDOR_MISMATCH: ExceptionSeverity.LOW,
    RuleViolationType.INVALID_DATE: ExceptionSeverity.LOW,
}


class ExceptionHandler:
    """Handler for creating and managing exception cases."""
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
    
    async def create_from_violation(
        self,
        invoice: Invoice,
        violation: RuleViolation,
        pipeline_run_id: Optional[UUID] = None,
    ) -> ExceptionCase:
        """Create an exception case from a rule violation."""
        category = VIOLATION_TO_CATEGORY.get(violation.rule_type, ExceptionCategory.OTHER)
        severity = SEVERITY_BY_VIOLATION.get(violation.rule_type, ExceptionSeverity.MEDIUM)
        owner_role = EXCEPTION_OWNER_ROLE.get(category, OwnerRole.AP_MANAGER)
        sla_hours = EXCEPTION_SLA_HOURS.get(category, 24)
        
        exception = ExceptionCase(
            tenant_id=self.tenant_id,
            invoice_id=invoice.id,
            pipeline_run_id=pipeline_run_id,
            category=category,
            severity=severity,
            status=ExceptionStatus.OPEN,
            owner_role=owner_role,
            title=f"{category.value}: {violation.message[:100]}",
            description=violation.message,
            details=violation.details,
            sla_deadline=datetime.utcnow() + timedelta(hours=sla_hours),
        )
        
        self.db.add(exception)
        invoice.status = InvoiceStatus.EXCEPTION
        
        self.logger.info(
            "Created exception",
            invoice_id=str(invoice.id),
            category=category.value,
            severity=severity.value,
        )
        
        return exception
    
    async def create_exception(
        self,
        invoice: Invoice,
        category: ExceptionCategory,
        title: str,
        description: Optional[str] = None,
        details: Optional[dict] = None,
        severity: Optional[ExceptionSeverity] = None,
        pipeline_run_id: Optional[UUID] = None,
    ) -> ExceptionCase:
        """Create an exception case directly."""
        if severity is None:
            severity = ExceptionSeverity.MEDIUM
        
        owner_role = EXCEPTION_OWNER_ROLE.get(category, OwnerRole.AP_MANAGER)
        sla_hours = EXCEPTION_SLA_HOURS.get(category, 24)
        
        exception = ExceptionCase(
            tenant_id=self.tenant_id,
            invoice_id=invoice.id,
            pipeline_run_id=pipeline_run_id,
            category=category,
            severity=severity,
            status=ExceptionStatus.OPEN,
            owner_role=owner_role,
            title=title,
            description=description,
            details=details,
            sla_deadline=datetime.utcnow() + timedelta(hours=sla_hours),
        )
        
        self.db.add(exception)
        invoice.status = InvoiceStatus.EXCEPTION
        
        return exception
    
    async def resolve_exception(
        self,
        exception: ExceptionCase,
        resolution: str,
        resolution_action: str,
        resolved_by: UUID,
    ) -> ExceptionCase:
        """A person's decision on a held invoice, recorded in its audit trail."""
        exception_status, invoice_status = RESOLUTIONS[resolution_action]
        exception.status = exception_status
        exception.resolution = resolution
        exception.resolution_action = resolution_action
        exception.resolved_by = resolved_by
        exception.resolved_at = datetime.utcnow()
        if invoice_status is not None:
            invoice = await self.db.get(Invoice, exception.invoice_id)
            invoice.status = invoice_status
        await AuditService(self.db, self.tenant_id).emit(
            invoice_id=exception.invoice_id, pipeline_run_id=exception.pipeline_run_id,
            step=AuditStep.EXCEPTION_RESOLVED, raw_input={"exception_id": str(exception.id)},
            raw_output={"action": resolution_action, "resolution": resolution}, started_at=exception.resolved_at,
            actor_id=resolved_by, actor_type="user",
        )
        
        self.logger.info(
            "Resolved exception",
            exception_id=str(exception.id),
            action=resolution_action,
        )
        
        return exception
    
    async def check_sla_breaches(self) -> list[ExceptionCase]:
        """Check and mark SLA breaches."""
        from sqlalchemy import select, and_
        
        query = select(ExceptionCase).where(
            and_(
                ExceptionCase.tenant_id == self.tenant_id,
                ExceptionCase.status == ExceptionStatus.OPEN,
                ExceptionCase.sla_deadline < datetime.utcnow(),
                ExceptionCase.sla_breached == False,
            )
        )
        
        result = await self.db.execute(query)
        breached = result.scalars().all()
        
        for exc in breached:
            exc.sla_breached = True
            self.logger.warning("SLA breached", exception_id=str(exc.id))
        
        return list(breached)
