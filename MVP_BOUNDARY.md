# MVP Boundary Document

## What This MVP Delivers

### Core Processing Pipeline
- **Ingestion**: Accept invoices as JSON with canonical fields
- **Validation**: Required fields, duplicate detection, PO lookup
- **Matching**: 2-way (Invoice↔PO) and 3-way (Invoice↔PO↔Receipt)
- **LLM Analysis**: Mock LLM with deterministic outputs for demo
- **Verification**: JSON schema validation, invariant checks
- **Decision**: Approve, Reject, or Route to Exception Queue

### LLM Router
- **Tier A (GPT-3.5 equivalent)**: High confidence (>90%), low risk
- **Tier B (GPT-4-mini equivalent)**: Medium confidence (70-90%)
- **Tier C (GPT-4 equivalent)**: Low confidence (<70%), high risk
- **Escalation**: Auto-escalate on high amount, complex exception, or retry
- **Budget Caps**: Tenant-level daily spend limits

### Exception Management
- **Taxonomy**: 8 exception categories with severity levels
- **SLA Tracking**: Deadline per category, breach detection
- **Resolution Workflow**: Approve, Reject, Escalate, Reprocess
- **Owner Routing**: Route to correct role (Controller, AP Manager, BPO)

### Audit & Replay
- **Append-Only Ledger**: Every step logged with input/output hashes
- **Replay Endpoint**: Re-run pipeline with same inputs
- **Drift Detection**: Compare original vs replay outputs
- **Policy Versioning**: Track policy and prompt versions

### Cost Accounting
- **Per-Event Tracking**: Token counts, model tier, cost USD
- **Cost per Invoice**: Total cost to process each invoice
- **Cost per Verified Invoice**: Key efficiency metric
- **Cache Hit Tracking**: Semantic cache savings

### Frontend Dashboard
- **Dashboard**: Summary stats, system health
- **Invoice List**: Paginated, filterable by status
- **Invoice Detail**: Line items, audit timeline
- **Exception Queue**: SLA status, resolution form
- **Cost Dashboard**: Tier breakdown, efficiency metrics

## What This MVP Does NOT Deliver

### Document Processing
- ❌ PDF/image OCR and extraction
- ❌ Document classification
- ❌ Multi-format ingestion (XML, EDI)
- ✅ **Workaround**: Accept pre-canonicalized JSON

### Real LLM Integration
- ❌ OpenAI/Anthropic API calls
- ❌ Real token counting
- ✅ **Workaround**: MockLLM with deterministic outputs

### Authentication & Multi-Tenancy
- ❌ Full user management
- ❌ SSO/SAML integration
- ✅ **Workaround**: Demo users with hardcoded JWT

### Notifications
- ❌ Email alerts
- ❌ Slack/Teams integration
- ❌ SLA breach notifications

### Analytics
- ❌ Historical trend analysis
- ❌ Predictive exception routing
- ❌ Vendor performance scoring

### Production Operations
- ❌ Kubernetes deployment
- ❌ CI/CD pipelines
- ❌ Monitoring/alerting (Prometheus metrics endpoint exists)

## Key Metrics This MVP Tracks

1. **Touchless Rate**: % of invoices approved without human intervention
2. **Cost per Verified Invoice**: Average LLM cost for approved invoices
3. **Exception Rate**: % of invoices routed to exception queue
4. **Cache Hit Rate**: % of LLM calls served from cache
5. **SLA Breach Rate**: % of exceptions exceeding SLA deadlines

## Demo Scenario

The MVP includes 10 invoice fixtures:
- 5 clean invoices (expected: approved)
- 5 exception invoices (missing PO, duplicate, variances, vendor mismatch)

Running `make demo` will:
1. Seed POs and receipts
2. Ingest all 10 invoices
3. Process each through the pipeline
4. Print summary metrics

Expected output:
- Touchless Rate: ~50-60%
- Cost per Invoice: ~$0.02
- Exception breakdown by category

## Future Roadmap

### Phase 2: Real LLM Integration
- OpenAI/Anthropic provider implementations
- Prompt engineering and optimization
- A/B testing framework for prompts

### Phase 3: Document Processing
- Integration with AWS Textract or Google Document AI
- Multi-format document handling
- Confidence-based extraction

### Phase 4: Production Hardening
- Kubernetes Helm charts
- GitHub Actions CI/CD
- Grafana dashboards

### Phase 5: Advanced Features
- ML-based exception prediction
- Vendor risk scoring
- Natural language audit queries
