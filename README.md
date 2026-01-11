# AP Reconciliation Orchestrator

A production-minded MVP for automated accounts payable invoice reconciliation with deterministic rules, cost-aware LLM routing, verification layers, audit replay, and exception management.

## Features

- **Deterministic Rules Engine** - Required fields, duplicate detection, PO lookup, tolerance checks
- **Cost-Aware LLM Routing** - Tier A/B/C routing based on confidence, risk, and spend caps
- **2-Way & 3-Way Matching** - Invoice ↔ PO and Invoice ↔ PO ↔ Receipt matching
- **Exception Queue** - Category-based taxonomy, severity levels, SLA tracking
- **Audit Ledger & Replay** - Append-only audit events with drift detection
- **Cost Dashboard** - Track cost per verified invoice, cache hit rates
- **Semantic Caching** - Cache LLM responses to reduce costs

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                       │
│   Dashboard │ Invoices │ Exceptions │ Cost Dashboard │ Audit    │
└─────────────────────────────────────────────────────────────────┘
                              │ API
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                             │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│  Ingestion  │   Rules     │    LLM      │  Matching   │ Pipeline│
│   Layer     │   Engine    │   Router    │   Engine    │ Orchestr│
├─────────────┼─────────────┼─────────────┼─────────────┼─────────┤
│  Exception  │   Audit     │    Cost     │   Cache     │  Verify │
│   Handler   │   Service   │   Service   │   Service   │  Layer  │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────┘
                              │
┌─────────────┬───────────────────────────┬───────────────────────┐
│ PostgreSQL  │          Redis            │    Celery Workers     │
│  Database   │     Cache / Queue         │   Async Processing    │
└─────────────┴───────────────────────────┴───────────────────────┘
```

## Quick Start

```bash
# Clone and start all services
cd exception_resolution_model_orchestrator
make dev

# Seed the database with fixtures
make seed

# Run the demo (processes 10 invoices)
make demo
```

## Project Structure

```
.
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Business logic
│   │   ├── routes/             # API endpoints
│   │   ├── tasks/              # Celery tasks
│   │   └── tests/              # Unit tests
│   └── web/                    # Next.js frontend
│       └── app/                # App router pages
├── fixtures/                   # Seed data
│   └── invoices/               # 10 invoice fixtures
├── infra/                      # Docker configs
├── scripts/                    # seed.py, demo.py
├── Makefile
└── pyproject.toml
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/login` | POST | JWT authentication |
| `/ingest/invoice` | POST | Ingest new invoice |
| `/invoices` | GET | List invoices with pagination |
| `/invoices/{id}` | GET | Get invoice details |
| `/pipeline/run/{invoice_id}` | POST | Process invoice through pipeline |
| `/pipeline/run_batch` | POST | Batch process invoices |
| `/exceptions` | GET | List exceptions |
| `/exceptions/{id}` | GET | Get exception details |
| `/exceptions/{id}/resolve` | POST | Resolve exception |
| `/audit/{invoice_id}` | GET | Get audit timeline |
| `/audit/replay/{invoice_id}/{run_id}` | POST | Replay and detect drift |
| `/metrics/cost` | GET | Get cost dashboard |

## LLM Routing Policy

| Tier | Model | Confidence | Use Case |
|------|-------|------------|----------|
| A | GPT-3.5 | >90% | Simple, low-risk |
| B | GPT-4-mini | 70-90% | Medium complexity |
| C | GPT-4 | <70% | High-risk, complex |

**Escalation triggers:**
- Invoice amount > $10,000 → escalate one tier
- Complex exception (amount variance, duplicate) → escalate one tier
- Retry after failure → escalate one tier

## Pipeline State Machine

```
INGESTED → VALIDATING → MATCHING → LLM_PROCESSING → VERIFYING → COMPLETED
                ↓           ↓            ↓              ↓
            EXCEPTION   EXCEPTION    EXCEPTION      EXCEPTION
```

## Exception Categories

| Category | Severity | SLA | Owner |
|----------|----------|-----|-------|
| Missing PO | High | 4h | AP Manager |
| Duplicate | High | 4h | Controller |
| Amount Variance | High | 8h | AP Manager |
| Quantity Variance | Medium | 24h | BPO Operator |
| Vendor Mismatch | Low | 48h | BPO Operator |

## Demo Invoice Fixtures

| Invoice | Type | Expected Outcome |
|---------|------|------------------|
| INV-001 | Clean | ✅ Approved |
| INV-002 | Clean | ✅ Approved |
| INV-003 | Missing PO | ⚠️ Exception |
| INV-004 | Duplicate | ⚠️ Exception |
| INV-005 | Amount Variance (20%) | ⚠️ Exception |
| INV-006 | Clean | ✅ Approved |
| INV-007 | Quantity Variance | ⚠️ Exception |
| INV-008 | Clean (High Value) | ✅ Approved |
| INV-009 | Vendor Mismatch | ⚠️ Exception |
| INV-010 | Clean (Within Tolerance) | ✅ Approved |

## Make Commands

```bash
make dev      # Start all services
make down     # Stop services
make build    # Rebuild images
make test     # Run tests
make lint     # Run linter
make seed     # Seed database
make demo     # Run end-to-end demo
make logs     # View logs
make shell    # Shell into API container
make clean    # Clean up
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgres://... | PostgreSQL connection |
| `REDIS_URL` | redis://... | Redis connection |
| `JWT_SECRET` | dev-secret | JWT signing key |
| `TIER_A_THRESHOLD` | 0.9 | Confidence threshold for Tier A |
| `TIER_B_THRESHOLD` | 0.7 | Confidence threshold for Tier B |
| `HIGH_RISK_AMOUNT` | 10000 | Amount for high-risk escalation |
| `DAILY_LLM_CAP` | 100.0 | Daily LLM spend cap per tenant |

## Testing

```bash
# Run all tests
make test

# Run specific test file
docker-compose exec api pytest apps/api/tests/test_rules_engine.py -v
```

## Demo Credentials

| Username | Password | Role |
|----------|----------|------|
| controller | demo123 | Controller |
| ap_manager | demo123 | AP Manager |
| bpo_operator | demo123 | BPO Operator |

## MVP Boundary

This MVP includes:
- ✅ Complete pipeline state machine
- ✅ Deterministic rules before LLM
- ✅ Cost-aware LLM routing
- ✅ 2-way and 3-way matching
- ✅ Exception queue with SLA
- ✅ Audit ledger with replay/drift
- ✅ Cost per verified invoice metric
- ✅ Semantic caching

Not included in MVP:
- ❌ Real LLM integration (uses MockLLM)
- ❌ Document OCR/parsing (accepts JSON)
- ❌ Email notifications
- ❌ Advanced analytics
- ❌ Multi-language support

## License

MIT
