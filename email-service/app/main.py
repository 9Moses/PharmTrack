"""
app/main.py — Email Service (FastAPI)
Exposes:
  GET  /health     — health check
  POST /send       — manual trigger (internal use / testing)
  GET  /           — service info

On startup, launches the RabbitMQ consumer in a background thread.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from core.config import settings
from app.consumers.email_consumer import start_consumer_thread
from app.services.email_sender import send_email

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Lifespan ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start RabbitMQ consumer thread on startup."""
    logger.info("[Email Service] Starting up — launching RabbitMQ consumer thread...")
    thread = start_consumer_thread()
    app.state.consumer_thread = thread
    yield
    logger.info("[Email Service] Shutting down.")


# ─── App ──────────────────────────────────────────────────────

app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    description="Async email service for PharmTrack microservices. Consumes RabbitMQ events and dispatches templated emails.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── Schemas ──────────────────────────────────────────────────

class SendEmailRequest(BaseModel):
    to: EmailStr
    subject: str
    text_body: str
    html_body: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


# ─── Routes ──────────────────────────────────────────────────

@app.get("/", tags=["Info"])
async def root():
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    consumer_alive = (
        hasattr(app.state, "consumer_thread") and app.state.consumer_thread.is_alive()
    )
    return HealthResponse(
        status="healthy" if consumer_alive else "degraded",
        service=settings.service_name,
        version=settings.service_version,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post("/send", tags=["Email"], status_code=status.HTTP_202_ACCEPTED)
async def send_manual_email(request: SendEmailRequest):
    """
    Manual email trigger — useful for testing and internal tooling.
    Protected in production by API Gateway or service mesh (no auth here by design).
    """
    success = await send_email(
        to=request.to,
        subject=request.subject,
        text_body=request.text_body,
        html_body=request.html_body,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email. Check SMTP configuration.",
        )
    return {"message": f"Email queued for delivery to {request.to}"}
