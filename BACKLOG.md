# Technical Debt & Backlog

Technical items that need attention but are deferred from MVP scope.

## 🔴 High Priority (Should Fix Soon)

### Database-Dependent Test Fixtures
**Current state**: Tests for RulesEngine, AuditService, and duplicate detection require actual async PostgreSQL sessions.
**Impact**: These tests can't run in CI without database infrastructure.
**Solution**: Either:
1. Create proper async SQLite fixtures for testing, or
2. Mock the database layer in tests

**Affected files**:
- `test_rules_engine.py` - All tests ERROR
- `test_recurring_invoices.py` - All tests ERROR  
- `test_replay.py` - Some tests ERROR (audit event emission, drift detection)
- `test_tolerance_stacking.py` - All tests ERROR
- `test_split_po.py` - Most tests ERROR

### Tolerance Stacking at Document Level
**Current state**: MatchingEngine checks line-item tolerances but may not aggregate for document-level check.
**Impact**: Invoices could pass line-by-line checks but exceed total tolerance.
**Solution**: Add explicit document total variance check in `matching_engine.py`.

### Recurring Invoice False Positives
**Current state**: Fuzzy duplicate detection may flag monthly recurring invoices.
**Impact**: High false-positive rate for recurring vendors.
**Solution**: Add time-window filter to `RulesEngine._check_fuzzy_duplicate()`.

---

## 🟡 Medium Priority (Nice to Have)

### Split/Consolidated PO Support
**Current state**: MatchingEngine assumes 1:1 invoice-to-PO relationship.
**Impact**: Common scenarios (partial delivery, consolidated invoices) become exceptions.
**Solution**: Add `match_multi_po()` and `match_partial()` methods to MatchingEngine.

### Rate Limiting
**Current state**: No rate limiting on API endpoints.
**Impact**: Potential for budget exhaustion attacks.
**Solution**: Add FastAPI middleware with Redis-based rate limiting.

### PostgreSQL Row-Level Security
**Current state**: Tenant isolation is application-level only.
**Impact**: If any service skips tenant filter, data could leak.
**Solution**: Add RLS policies to PostgreSQL tables.

---

## 🟢 Lower Priority (Future Enhancement)

### Real LLM Provider Integration
**Current state**: MockLLM only.
**Impact**: Can't test actual LLM behavior.
**Solution**: Implement OpenAI and Anthropic providers in `llm_provider.py`.

### Document OCR/Parsing
**Current state**: Accepts pre-parsed JSON only.
**Impact**: Can't process actual invoice PDFs/images.
**Solution**: Integrate Azure Document Intelligence or similar.

### Email/Webhook Notifications
**Current state**: No notifications for SLA breaches.
**Impact**: Exceptions may be missed.
**Solution**: Add notification service with configurable channels.

### Production Deployment
- Kubernetes manifests
- Helm charts
- CI/CD pipeline configuration
- Secrets management (HashiCorp Vault or similar)

---

## 📊 Test Coverage Summary

| Test File | Status | Notes |
|-----------|--------|-------|
| `test_verification.py` | ✅ 11 passed | All working |
| `test_circuit_breaker.py` | ✅ 9 passed | All working |
| `test_recovery.py` | ✅ 7 passed | All working |
| `test_security.py` | ✅ 9 passed | All working |
| `test_llm_router.py` | ✅ Fixed | Uses mocked DB |
| `test_rules_engine.py` | ⚠️ Needs DB | Deferred |
| `test_recurring_invoices.py` | ⚠️ Needs DB | Deferred |
| `test_replay.py` | ⚠️ Partial | Hash tests pass, DB tests deferred |
| `test_tolerance_stacking.py` | ⚠️ Needs refactor | Test MatchingEngine directly |
| `test_split_po.py` | ⚠️ Needs implementation | Feature not built |

---

## Commands

```bash
# Run all passing tests
pytest apps/api/tests/ --ignore=apps/api/tests/conftest.py -v

# Run only unit tests (no DB required)
pytest apps/api/tests/test_verification.py apps/api/tests/test_circuit_breaker.py \
       apps/api/tests/test_recovery.py apps/api/tests/test_security.py \
       apps/api/tests/test_llm_router.py -v
```
