"""
Verification Layer for LLM output validation.
"""

import json
from dataclasses import dataclass, field as dc_field
from decimal import Decimal
from typing import Optional, List, Dict, Any, Type
from uuid import UUID

import structlog
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger()


@dataclass
class VerificationError:
    error_type: str
    message: str
    field: Optional[str] = None
    details: Dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class VerificationResult:
    valid: bool
    errors: List[VerificationError] = dc_field(default_factory=list)
    warnings: List[str] = dc_field(default_factory=list)
    sanitized_output: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [
                {"type": e.error_type, "message": e.message, "field": e.field}
                for e in self.errors
            ],
            "warnings": self.warnings,
        }


class VerificationService:
    """Service for validating and verifying LLM outputs."""
    
    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=str(tenant_id))
    
    def verify_llm_response(
        self,
        response: Dict[str, Any],
        schema: Optional[Type[BaseModel]] = None,
        invoice_data: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify an LLM response against schema and invariants."""
        errors = []
        warnings = []
        
        # Schema validation
        if schema:
            schema_errors = self._validate_schema(response, schema)
            errors.extend(schema_errors)
        
        # Required fields check
        required_errors = self._check_required_fields(response)
        errors.extend(required_errors)
        
        # Invariant checks
        if invoice_data:
            invariant_errors = self._check_invariants(response, invoice_data)
            errors.extend(invariant_errors)
        
        # Business logic checks
        logic_errors, logic_warnings = self._check_business_logic(response)
        errors.extend(logic_errors)
        warnings.extend(logic_warnings)
        
        valid = len(errors) == 0
        
        return VerificationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            sanitized_output=response if valid else None,
        )
    
    def _validate_schema(
        self, response: Dict[str, Any], schema: Type[BaseModel]
    ) -> List[VerificationError]:
        errors = []
        try:
            schema.model_validate(response)
        except ValidationError as e:
            for err in e.errors():
                errors.append(VerificationError(
                    error_type="schema_validation",
                    message=err.get("msg", "Validation error"),
                    field=".".join(str(x) for x in err.get("loc", [])),
                    details={"type": err.get("type")},
                ))
        return errors
    
    def _check_required_fields(self, response: Dict[str, Any]) -> List[VerificationError]:
        errors = []
        required = ["decision", "confidence"]
        for field in required:
            if field not in response or response[field] is None:
                errors.append(VerificationError(
                    error_type="missing_required_field",
                    message=f"Required field '{field}' is missing",
                    field=field,
                ))
        
        # Confidence bounds check
        confidence = response.get("confidence")
        if confidence is not None:
            if not (0 <= confidence <= 1):
                errors.append(VerificationError(
                    error_type="invalid_value",
                    message="Confidence must be between 0 and 1",
                    field="confidence",
                ))
        
        return errors
    
    def _check_invariants(
        self, response: Dict[str, Any], invoice_data: Dict[str, Any]
    ) -> List[VerificationError]:
        errors = []
        
        # Amount sum invariant
        line_items = invoice_data.get("line_items", [])
        if line_items and invoice_data.get("subtotal"):
            line_sum = sum(
                Decimal(str(item.get("amount", 0))) 
                for item in line_items
            )
            subtotal = Decimal(str(invoice_data["subtotal"]))
            if abs(line_sum - subtotal) > Decimal("0.01"):
                errors.append(VerificationError(
                    error_type="invariant_violation",
                    message=f"Line items sum ({line_sum}) doesn't match subtotal ({subtotal})",
                    field="line_items",
                    details={"line_sum": str(line_sum), "subtotal": str(subtotal)},
                ))
        
        # Currency consistency
        if "currency" in invoice_data:
            inv_currency = invoice_data["currency"]
            resp_variances = response.get("variances", [])
            for var in resp_variances:
                if var.get("type") == "currency" and var.get("invoice_currency") != inv_currency:
                    errors.append(VerificationError(
                        error_type="invariant_violation",
                        message="Currency mismatch in response",
                        field="currency",
                    ))
        
        return errors
    
    def _check_business_logic(
        self, response: Dict[str, Any]
    ) -> tuple[List[VerificationError], List[str]]:
        errors = []
        warnings = []
        
        decision = response.get("decision")
        confidence = response.get("confidence", 0)
        requires_review = response.get("requires_review", False)
        
        # High confidence reject should require review
        if decision == "reject" and confidence > 0.9 and not requires_review:
            warnings.append("High-confidence rejection without review flag")
        
        # Low confidence approve should require review
        if decision == "approve" and confidence < 0.7 and not requires_review:
            errors.append(VerificationError(
                error_type="logic_error",
                message="Low-confidence approval must require review",
                field="decision",
            ))
        
        # Variances require explanation
        variances = response.get("variances", [])
        if variances and not response.get("reasoning"):
            warnings.append("Variances detected but no reasoning provided")
        
        return errors, warnings
    
    def verify_json_structure(self, content: str) -> tuple[bool, Optional[Dict[str, Any]], str]:
        """Verify that content is valid JSON and return parsed result."""
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                return False, None, "Response must be a JSON object"
            return True, parsed, ""
        except json.JSONDecodeError as e:
            return False, None, f"Invalid JSON: {str(e)}"
