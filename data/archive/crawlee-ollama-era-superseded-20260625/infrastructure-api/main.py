#!/usr/bin/env python3
"""
FastAPI Orchestrator for Bell Schedule Acquisition

Coordinates:
- Crawlee service for website mapping and PDF capture
- Ollama for URL ranking and PDF triage
- File management for PDF storage
- Learning loop pattern updates
- Serial queue processing for acquisitions
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.api.routes import acquire, triage, patterns, enrich

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Set low priority for resource-friendly execution
    try:
        os.nice(10)
        logger.info("Starting Bell Schedule Acquisition API (nice +10)")
    except (OSError, AttributeError):
        logger.info("Starting Bell Schedule Acquisition API")
    yield
    # Graceful shutdown - cancel any running acquisition
    logger.info("Shutting down Bell Schedule Acquisition API")
    if acquire._current_task and not acquire._current_task.done():
        logger.info("Cancelling running acquisition...")
        acquire._current_task.cancel()
        try:
            await asyncio.wait_for(acquire._current_task, timeout=30)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        logger.info("Acquisition cancelled")


app = FastAPI(
    title="Bell Schedule Acquisition API",
    description="Orchestrates Crawlee and Ollama for automated bell schedule collection",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(acquire.router, prefix="/acquire", tags=["acquisition"])
app.include_router(triage.router, prefix="/triage", tags=["triage"])
app.include_router(patterns.router, prefix="/patterns", tags=["patterns"])
app.include_router(enrich.router, prefix="/enrich", tags=["enrichment"])


@app.get("/")
async def root():
    """API documentation."""
    return {
        "name": "Bell Schedule Acquisition API",
        "version": "1.1.0",
        "endpoints": {
            "acquisition": {
                "POST /acquire/district/{id}": "Start acquisition for a district",
                "GET /acquire/status/{id}": "Check acquisition status",
            },
            "queue": {
                "GET /acquire/queue": "Get queue status (pending, current, processing_active)",
                "POST /acquire/queue": "Add single district to queue",
                "POST /acquire/queue/batch": "Add multiple districts to queue",
                "DELETE /acquire/queue/{id}": "Remove district from pending queue",
                "POST /acquire/start": "Start serial queue processing",
                "POST /acquire/stop": "Stop after current completes",
                "POST /acquire/cancel/{id}": "Cancel running or pending acquisition",
                "GET /acquire/queue/history": "Get recent acquisition history",
            },
            "triage": {
                "POST /triage/pdf": "Score a PDF for bell schedule content",
            },
            "patterns": {
                "GET /patterns": "Get current learning patterns",
                "POST /patterns/learn": "Update patterns from feedback",
            },
            "enrichment": {
                "POST /enrich/extract": "Extract times from PDF text using Ollama",
                "GET /enrich/status/{id}": "Check enrichment status for a district",
                "GET /enrich/files/{id}": "List enrichment files for a district",
            },
        },
        "documentation": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
