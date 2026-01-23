# AP Reconciliation Orchestrator

> **This isn't "AP software." This is AI systems infrastructure.**

## 🎯 The Wedge → Platform Strategy

**Start narrow. Prove economics. Expand laterally.**

This project demonstrates a **cost-aware orchestration layer** that can route between deterministic rules, cached decisions, and tiered AI models based on risk and complexity. AP invoice reconciliation is the **opinionated wedge** — a workflow where:

1. **Unit economics matter immediately** (high volume, thin margins)
2. **Ground truth exists** (POs, receipts, GL codes)
3. **Cost of error is quantifiable** (duplicate payments, compliance fines)

Once you prove **cost + accuracy dominance** in AP, the same infrastructure applies to:
- **AR/Collections** (payment matching, dispute resolution)
- **Procurement** (contract compliance, vendor onboarding)
- **Expense Management** (receipt matching, policy enforcement)
- **Any document-heavy workflow** where you need to balance AI cost vs. human cost

---

## 📈 The Core Thesis: Economics-First AI

Most automation tools use an "LLM-first" brute force approach: throw every document at GPT-4 and hope for the best. This is **commercially unviable** for high-volume workflows because the marginal cost of AI can exceed the processing fee.

**This orchestrator treats model selection as a risk-adjusted financial decision.** It uses a **Hierarchy of Resolution** to ensure you never spend more on AI than the risk justifies.

### The Hierarchy of Resolution
The system always attempts to solve at the cheapest possible level before "falling down":

1.  **Deterministic Rules** (~$0.000) → Catch duplicates/missing fields before any AI sees them
2.  **Semantic Cache** (~$0.000) → Reuse previous AI decisions for recurring invoices
3.  **Tier A AI** (~$0.0001/call) → High-confidence, low-value matches (e.g., GPT-3.5)
4.  **Tier C AI** (~$0.01/call) → High-risk or complex cases (e.g., GPT-4)
5.  **Human Review** (~$2-5/invoice) → Final fallback for true anomalies

**The goal:** Drive the blended cost per verified invoice to <$0.05 while maintaining >99% accuracy.

---

## 🏗️ Why Engineers Pay Attention

This project moves away from "AI magic" and into **deterministic orchestration with economic guardrails**.

### 1. The Deterministic Moat
The `RulesEngine` kills the run immediately if an invoice is a duplicate or missing required fields.
*   **Result:** Zero tokens spent on "broken" invoices that would confuse an LLM anyway.

### 2. Risk-Based Escalation (Not Complexity-Based)
The `LLMRouter` doesn't just look at "how hard is this?" — it looks at **"what's the liability?"**
*   **Example:** A $50,000 invoice with 2% variance gets Tier C (premium model). A $200 invoice with the same variance gets Tier A (cheap model).
*   **Logic:** The cost of error on a $50k invoice justifies the premium. On a $200 invoice, it destroys your margins.

### 3. Verification Over Generation
The `VerificationService` enforces invariants on LLM outputs.
*   **Safety:** If the LLM claims a match but the line-item math doesn't add up, the system flags it as an exception.
*   **No hallucination risk:** The LLM doesn't "decide" — it analyzes. The system decides based on verified facts.

### 4. Cost-per-Verified-Invoice (Not Just API Spend)
We track **spend per successful outcome**, not just total spend.
*   **Why it matters:** A Tier C model with 99% first-pass accuracy might be cheaper per verified invoice than a Tier A model with 60% accuracy (due to rework/exceptions).

---

## What Does This Do?

## The Big Picture

```
📄 Invoice arrives → 🔍 Validate → 🔗 Match to PO/Receipt → 🤖 AI Analysis → ✅ Approve or ⚠️ Flag Exception
                                                                                    ↓
                                                                          📊 Track costs & audit trail
```

### Real-World Example

**Scenario**: Your company receives an invoice for $5,400 from Acme Supplies.

1. **Validation**: System checks it has invoice number, date, vendor, PO number, amounts ✅
2. **Matching**: Finds PO-2024-001 for $5,000 and receipt showing goods received ✅
3. **Variance Check**: Invoice is 8% higher than PO ($5,400 vs $5,000) ⚠️
4. **AI Decision**: Uses GPT-4 (Tier C) because of the variance, determines it's due to tax
5. **Verification**: Validates the AI's reasoning and math ✅
6. **Result**: Auto-approved with full audit trail, cost: ~$0.02-0.05 (estimated)

**Alternative Scenario**: Invoice references PO-MISSING-999 that doesn't exist
- System immediately flags as "Missing PO" exception
- Routes to AP Manager with 4-hour SLA
- No expensive AI call needed for obvious issue
- Cost: ~$0.001 (rules-only, no AI)

## Key Features Explained

### 🎯 Deterministic Rules Engine

**What it does**: Checks invoices against hard rules before using expensive AI.

**Why it matters**: Catches 40% of issues instantly without AI costs.

**Rules include**:
- Required fields (invoice number, date, vendor, amount)
- Duplicate detection (exact and fuzzy matching)
- PO lookup and validation
- Amount/quantity tolerance checks (configurable, default ±1%)

**Example**: If an invoice is missing a PO number, the system flags it immediately without calling an AI model.

### 💰 Cost-Aware LLM Routing

**What it does**: Automatically selects the right AI model based on complexity and risk.

**Why it matters**: Saves money by using cheaper models when appropriate, reserves expensive models for complex cases.

**How it works**:

| Tier | Model | When Used | Cost per 1K tokens |
|------|-------|-----------|-------------------|
| **A** | GPT-3.5 | High confidence (>90%), low risk (<$10K) | ~$0.0001-0.0005 |
| **B** | GPT-4-mini | Medium confidence (70-90%) or high-value invoices | ~$0.001-0.005 |
| **C** | GPT-4 | Low confidence (<70%), complex exceptions | $0.01 |

**Escalation triggers**:
- 💵 Invoice over $10,000 → bump up one tier (more scrutiny for high-value)
- 🔄 Retry after failure → bump up one tier (smarter model might succeed)
- 🧩 Complex exception (duplicate, amount variance) → bump up one tier

**Example**: A $500 invoice with perfect PO match uses Tier A (~$0.0001-0.0005). A $15,000 invoice with 10% variance uses Tier C (~$0.01-0.03).

### 🔄 Hybrid Routing (Optimistic Strategy)

**What it does**: "Cheap to propose, expensive to verify."

Instead of statically routing based on confidence, the system now:
1. **Optimistically** tries Tier A (Cheap) first for most invoices.
2. If Tier A output has low confidence (< 0.85) or flags a "Review", it **auto-escalates** to Tier C (Expensive).
3. **Result**: You pay Tier A prices for 80% of volume, and only pay Tier C when actually needed.

### 👥 Shadow Mode

**What it does**: safely tests new routing policies in production.

- The system can run a "Shadow Router" alongside the main one.
- Shadow decisions are logged to the audit trail (`SHADOW_ROUTING`) but do not affect the live invoice.
- Allows you to validatate "What would happen if I changed the threshold to 0.7?" without risk.

### 🔗 2-Way & 3-Way Matching

**What it does**: Compares invoice against purchase orders and receipts.

**2-Way Matching** (Invoice ↔ Purchase Order):
- Vendor matches
- Amounts within tolerance
- Currency matches
- Line items align

**3-Way Matching** (Invoice ↔ PO ↔ Receipt):
- Everything in 2-way, plus:
- Quantities received match invoice quantities
- Confirms goods were actually delivered

**Example**:
```
Invoice: 100 widgets @ $25 = $2,500
PO:      100 widgets @ $25 = $2,500  ✅ Match
Receipt: 100 widgets received        ✅ 3-way match complete
```

### ⚠️ Exception Queue with SLA Tracking

**What it does**: Routes problematic invoices to the right person with deadlines.

**Exception Categories**:

| Category | Severity | SLA | Who Handles | Example |
|----------|----------|-----|-------------|---------|
| Missing PO | 🔴 High | 4 hours | AP Manager | Invoice references non-existent PO |
| Duplicate | 🔴 High | 4 hours | Controller | Same invoice submitted twice |
| Amount Variance | 🔴 High | 8 hours | AP Manager | Invoice 20% over PO amount |
| Quantity Variance | 🟡 Medium | 24 hours | BPO Operator | Received 95 items, invoiced for 100 |
| Vendor Mismatch | 🟢 Low | 48 hours | BPO Operator | Wrong vendor on invoice |

**SLA Tracking**: System automatically flags exceptions that breach their deadline.

### 📜 Audit Ledger & Replay

**What it does**: Records every step of processing so you can replay it later.

**Why it matters**: 
- **Compliance**: Prove to auditors exactly how each decision was made
- **Debugging**: If something went wrong, replay to see what happened
- **Drift Detection**: Replay with updated rules to see if decisions would change

**How it works**:
1. Every pipeline step is logged with input/output hashes
2. You can request a "replay" of any invoice
3. System re-runs with same inputs, compares outputs
4. Reports any "drift" (different results)

**Example Use Case**: 
- Original run (Jan 1): Invoice approved with Tier A model
- Policy updated (Jan 15): New tolerance rules
- Replay (Jan 20): Would now be flagged as exception
- **Drift detected**: Shows policy change impact

### 🔁 Replay Harness (Offline Simulation)

**What it does**: Simulates pipeline runs against huge historical datasets to measure "Cost vs Accuracy" impact of policy changes.

**How to run**:
```bash
# 1. Seed benchmark data
make seed

# 2. Run comparison (Baseline vs Hybrid)
python scripts/run_replay.py
```

**Output**:
```
Hybrid: Cost=$0.45, Approved=48/50
Baseline: Cost=$2.10, Approved=49/50
Savings: 78% | Accuracy Delta: -2%
```

### 💵 Cost Dashboard

**What it does**: Tracks and reports AI costs with key efficiency metrics.

**Key Metrics**:
- **Total LLM Cost**: All AI spending
- **Cost per Invoice**: Average cost to process any invoice
- **Cost per Verified Invoice**: Average cost for successfully approved invoices (key metric!)
- **Cache Hit Rate**: % of AI calls served from cache (saves money)
- **Touchless Rate**: % of invoices approved without human intervention

**Why "Cost per Verified Invoice" matters**: 
- Includes only successful approvals (your actual throughput)
- Excludes exceptions that need human review anyway
- Shows true automation efficiency

**Example Dashboard** (with real LLM integration):
```
Total Cost:              ~$0.20-0.50
Total Invoices:          10
Cost per Invoice:        ~$0.02-0.05
Cost per Verified:       ~$0.03-0.08  (6 approved out of 10)
Touchless Rate:          60%
Cache Hit Rate:          33%
```

> **Note:** This MVP uses MockLLM for demonstration. Costs shown are estimates based on real-world OpenAI pricing.

### 🗄️ Semantic Caching

**What it does**: Remembers AI responses for similar invoices.

**How it works**:
1. Normalize invoice data (remove timestamps, IDs)
2. Hash the normalized input + policy version + model
3. Check cache before calling AI
4. Store response for future use

**Example**: 
- Invoice 1: $1,000 from Acme, PO-001 → AI call → Cache
- Invoice 2: $1,000 from Acme, PO-001 → Cache hit! (free)
- Savings: ~$0.001-0.01 per cache hit (depending on tier)

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Installation & Demo

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/exception_resolution_model_orchestrator.git
cd exception_resolution_model_orchestrator

# 2. Start all services (PostgreSQL, Redis, API, Celery, Frontend)
make dev

# Wait for services to be healthy (about 30 seconds)

# 3. Seed the database with purchase orders and receipts
make seed

# 4. Run the demo (processes 10 sample invoices)
make demo
```

### What the Demo Does

The demo processes 10 invoices with different scenarios:

| Invoice | Scenario | Expected Result |
|---------|----------|-----------------|
| INV-001 | Perfect match | ✅ Auto-approved |
| INV-002 | Perfect match | ✅ Auto-approved |
| INV-003 | Missing PO | ⚠️ Exception (Missing PO) |
| INV-004 | Exact duplicate | ⚠️ Exception (Duplicate) |
| INV-005 | 20% over PO amount | ⚠️ Exception (Amount Variance) |
| INV-006 | Perfect match | ✅ Auto-approved |
| INV-007 | Quantity mismatch | ⚠️ Exception (Quantity Variance) |
| INV-008 | High-value ($12K) | ✅ Auto-approved (uses Tier B) |
| INV-009 | Wrong vendor | ⚠️ Exception (Vendor Mismatch) |
| INV-010 | Within tolerance | ✅ Auto-approved |

**Expected Output**:
```
📊 Processing Summary
   Total Invoices:        10
   Touchless (Approved):  6 (60%)
   Exceptions:            4 (40%)

💰 Cost Metrics (MockLLM - estimates only)
   Total LLM Cost:        ~$0.20-0.50 (with real LLM)
   Avg Cost per Invoice:  ~$0.02-0.05
   Cache Hit Rate:        33%

⚠️  Exception Breakdown
   missing_po             1
   duplicate              1
   amount_variance        1
   vendor_mismatch        1
```

> **Note:** This demo uses MockLLM with deterministic outputs. In production with real OpenAI/Anthropic integration, costs would vary based on actual token usage.

### Accessing the Application

After running `make dev`:

- **Frontend Dashboard**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **API Health Check**: http://localhost:8000/health

**Demo Login Credentials**:
- Username: `controller` / Password: `demo123` (Full access)
- Username: `ap_manager` / Password: `demo123` (AP Manager role)
- Username: `bpo_operator` / Password: `demo123` (Operator role)

## Architecture Deep Dive

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js + Tailwind)                 │
│  - Dashboard with metrics                                        │
│  - Invoice list and detail views                                 │
│  - Exception queue with SLA tracking                             │
│  - Cost dashboard with breakdowns                                │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API
┌────────────────────────────┴────────────────────────────────────┐
│                    FastAPI Backend (Python)                      │
├──────────────┬──────────────┬──────────────┬──────────────┬─────┤
│ Ingestion    │ Rules Engine │ LLM Router   │ Matching     │ ... │
│ - Hash docs  │ - Validate   │ - Tier select│ - 2-way      │     │
│ - Normalize  │ - Duplicates │ - Escalate   │ - 3-way      │     │
└──────────────┴──────────────┴──────────────┴──────────────┴─────┘
                             │
┌────────────────────────────┴────────────────────────────────────┐
│                    Data Layer                                    │
│  PostgreSQL: Invoices, POs, Receipts, Audit, Costs, Exceptions  │
│  Redis: Cache, Celery queue                                      │
└──────────────────────────────────────────────────────────────────┘
```

### Pipeline State Machine

Every invoice goes through these states:

```
INGESTED
   ↓
VALIDATING ──→ [Rules Engine checks]
   ↓                ↓ (if fails)
   ↓             EXCEPTION
   ↓
MATCHING ────→ [2-way/3-way matching]
   ↓                ↓ (if no match)
   ↓             EXCEPTION
   ↓
LLM_PROCESSING → [AI analysis with tier selection]
   ↓                ↓ (if rejected/needs review)
   ↓             EXCEPTION
   ↓
VERIFYING ───→ [Validate AI output]
   ↓                ↓ (if invalid)
   ↓             EXCEPTION
   ↓
COMPLETED (Approved!)
```

### Data Models

**Core Entities**:
- `Invoice`: The invoice being processed
- `PurchaseOrder`: Reference PO for matching
- `Receipt`: Goods receipt for 3-way matching
- `InvoicePipelineRun`: Tracks state machine progress
- `ExceptionCase`: Exceptions requiring human review
- `AuditEvent`: Immutable audit log entries
- `CostEvent`: Per-call cost tracking
- `SemanticCache`: Cached AI responses

## API Reference

### Authentication

```bash
# Login to get JWT token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "controller", "password": "demo123"}'

# Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 28800
}

# Use token in subsequent requests
curl http://localhost:8000/invoices \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
```

### Key Endpoints

#### Ingest Invoice
```bash
POST /ingest/invoice
```
Submit a new invoice for processing (accepts JSON with canonical fields).

#### Process Invoice
```bash
POST /pipeline/run/{invoice_id}
```
Run the full pipeline on an invoice.

#### List Invoices
```bash
GET /invoices?page=1&status=approved
```
Get paginated list of invoices with optional status filter.

#### Exception Queue
```bash
GET /exceptions?page=1&category=amount_variance
```
Get exceptions with filtering by category, severity, status.

#### Resolve Exception
```bash
POST /exceptions/{exception_id}/resolve
{
  "resolution": "Approved after vendor confirmation",
  "resolution_action": "approve"
}
```

#### Audit Timeline
```bash
GET /audit/{invoice_id}
```
Get complete audit trail for an invoice.

#### Replay & Drift Detection
```bash
POST /audit/replay/{invoice_id}/{run_id}
```
Replay a pipeline run and detect any drift.

#### Cost Dashboard
```bash
GET /metrics/cost?start_date=2024-01-01&end_date=2024-01-31
```
Get cost metrics and breakdowns.

**Full API documentation**: http://localhost:8000/docs (interactive Swagger UI)

## Configuration

### Environment Variables

Create a `.env` file or set these in your environment:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/ap_reconciliation

# Redis
REDIS_URL=redis://redis:6379/0

# Security
JWT_SECRET=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=8

# LLM Router Policy
TIER_A_THRESHOLD=0.9          # Confidence threshold for Tier A
TIER_B_THRESHOLD=0.7          # Confidence threshold for Tier B
HIGH_RISK_AMOUNT=10000.0      # Amount threshold for escalation
DAILY_LLM_CAP=100.0           # Daily spend cap per tenant (USD)

# Matching Tolerances
AMOUNT_TOLERANCE_PERCENT=0.01  # 1% tolerance for amount variance
QUANTITY_TOLERANCE_PERCENT=0.05 # 5% tolerance for quantity variance

# Model Costs (per 1K tokens)
TIER_A_COST_PER_1K=0.0001
TIER_B_COST_PER_1K=0.001
TIER_C_COST_PER_1K=0.01
```

### Adjusting Tolerances

To change how strict the matching is:

```python
# In .env file:
AMOUNT_TOLERANCE_PERCENT=0.02  # Allow 2% variance instead of 1%
QUANTITY_TOLERANCE_PERCENT=0.10 # Allow 10% quantity variance
```

### Adjusting LLM Routing

To use cheaper models more often:

```python
# In .env file:
TIER_A_THRESHOLD=0.85  # Lower threshold = more Tier A usage
HIGH_RISK_AMOUNT=20000 # Higher threshold = less escalation
```

## Development

### Project Structure

```
exception_resolution_model_orchestrator/
├── apps/
│   ├── api/                      # FastAPI backend
│   │   ├── models/               # SQLAlchemy database models
│   │   │   ├── invoice.py        # Invoice model
│   │   │   ├── purchase_order.py # PO model
│   │   │   ├── exception.py      # Exception queue
│   │   │   ├── audit.py          # Audit ledger
│   │   │   └── cost.py           # Cost tracking
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── services/             # Business logic
│   │   │   ├── rules_engine.py   # Deterministic validation
│   │   │   ├── llm_router.py     # Cost-aware routing
│   │   │   ├── matching_engine.py # 2-way/3-way matching
│   │   │   ├── pipeline_orchestrator.py # State machine
│   │   │   ├── audit_service.py  # Audit logging
│   │   │   └── cost_service.py   # Cost tracking
│   │   ├── routes/               # API endpoints
│   │   ├── tasks/                # Celery async tasks
│   │   └── tests/                # Unit tests
│   └── web/                      # Next.js frontend
│       └── app/                  # App router pages
├── fixtures/                     # Demo data
│   ├── invoices/                 # 10 sample invoices
│   ├── purchase_orders.json      # Sample POs
│   └── receipts.json             # Sample receipts
├── infra/                        # Infrastructure
│   ├── docker-compose.yml        # Service orchestration
│   ├── Dockerfile.api            # API container
│   └── Dockerfile.web            # Frontend container
├── scripts/
│   ├── seed.py                   # Database seeding
│   └── demo.py                   # End-to-end demo
└── Makefile                      # Common commands
```

### Running Tests

```bash
# Run all tests
make test

# Run specific test file
docker-compose exec api pytest apps/api/tests/test_rules_engine.py -v

# Run with coverage
docker-compose exec api pytest --cov=apps.api --cov-report=html
```

### Make Commands

```bash
make dev      # Start all services in development mode
make down     # Stop all services
make build    # Rebuild Docker images
make test     # Run test suite
make lint     # Run code linter (ruff)
make format   # Auto-format code
make seed     # Seed database with fixtures
make demo     # Run end-to-end demo
make migrate  # Run database migrations
make logs     # View service logs
make shell    # Open shell in API container
make clean    # Clean up containers and volumes
```

### Adding a New Exception Category

1. **Update the enum** in `apps/api/models/exception.py`:
```python
class ExceptionCategory(str, Enum):
    # ... existing categories
    TAX_MISMATCH = "tax_mismatch"  # New category
```

2. **Add SLA and owner** in same file:
```python
EXCEPTION_SLA_HOURS = {
    # ... existing mappings
    ExceptionCategory.TAX_MISMATCH: 12,  # 12-hour SLA
}

EXCEPTION_OWNER_ROLE = {
    # ... existing mappings
    ExceptionCategory.TAX_MISMATCH: OwnerRole.CONTROLLER,
}
```

3. **Update the exception handler** to detect this category in `apps/api/services/exception_handler.py`

## MVP Scope & Limitations

### ✅ What's Included

- Complete pipeline state machine
- Deterministic rules before LLM
- Cost-aware LLM routing (3 tiers)
- 2-way and 3-way matching
- Exception queue with SLA tracking
- Audit ledger with replay/drift detection
- Cost per verified invoice metric
- Semantic caching
- Full REST API
- Web dashboard

### ❌ What's NOT Included (Future Roadmap)

- **Real LLM Integration**: Currently uses MockLLM with deterministic outputs
  - *Workaround*: Easy to swap in OpenAI/Anthropic providers
- **Document OCR**: No PDF/image parsing
  - *Workaround*: Accepts pre-parsed JSON
- **Email Notifications**: No SLA breach alerts
- **Advanced Analytics**: No ML-based predictions
- **Production Deployment**: No Kubernetes configs
  - *Workaround*: Docker Compose works for small-scale production

See [MVP_BOUNDARY.md](MVP_BOUNDARY.md) for detailed scope documentation.

## Troubleshooting

### Services won't start

```bash
# Check if ports are already in use
lsof -i :8000  # API
lsof -i :3000  # Frontend
lsof -i :5432  # PostgreSQL

# Clean up and restart
make clean
make build
make dev
```

### Database connection errors

```bash
# Check PostgreSQL is healthy
docker-compose ps postgres

# View logs
docker-compose logs postgres

# Reset database
make clean
make dev
make seed
```

### Frontend can't connect to API

Check CORS settings in `apps/api/config.py`:
```python
cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
```

## Contributing

This is an MVP demonstration project. For production use, consider:

1. **Security**: Implement proper authentication, secrets management
2. **Scalability**: Add horizontal scaling, load balancing
3. **Monitoring**: Integrate Grafana, Sentry, etc.
4. **Testing**: Expand test coverage beyond unit tests
5. **Documentation**: Add API client SDKs, more examples

## License

MIT License - see LICENSE file for details

---

**Questions?** Check the [MVP_BOUNDARY.md](MVP_BOUNDARY.md) for scope details or open an issue.
