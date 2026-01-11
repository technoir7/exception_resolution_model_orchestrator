"""
AP Reconciliation Orchestrator API

A production-minded MVP for accounts payable reconciliation with:
- Deterministic rules engine
- Cost-aware LLM routing
- Verification layer with JSON schema validation
- Audit ledger with replay capability
- Exception queue with SLA tracking
- Cost dashboard
"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from apps.api.config import settings
from apps.api.routes import ingest, invoices, pipeline, exceptions, audit, metrics, auth
from apps.api.models.base import init_db

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if settings.environment == "production" 
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("Starting AP Reconciliation Orchestrator", environment=settings.environment)
    await init_db()
    yield
    logger.info("Shutting down AP Reconciliation Orchestrator")


app = FastAPI(
    title="AP Reconciliation Orchestrator",
    description=__doc__,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics/prometheus", metrics_app)

# Register routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])
app.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(exceptions.router, prefix="/exceptions", tags=["Exceptions"])
app.include_router(audit.router, prefix="/audit", tags=["Audit"])
app.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "AP Reconciliation Orchestrator",
        "version": "0.1.0",
        "description": "Cost per verified invoice + audit replay",
        "docs": "/docs",
    }
