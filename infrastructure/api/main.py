#!/usr/bin/env python3
"""
FastAPI Orchestrator for Bell Schedule Acquisition

Coordinates:
- Crawlee service for website mapping and PDF capture
- Ollama for URL ranking and PDF triage
- File management for PDF storage
- Learning loop pattern updates
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.api.routes import acquire, triage, patterns

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting Bell Schedule Acquisition API")
    yield
    logger.info("Shutting down Bell Schedule Acquisition API")


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


@app.get("/")
async def root():
    """API documentation."""
    return {
        "name": "Bell Schedule Acquisition API",
        "version": "1.0.0",
        "endpoints": {
            "POST /acquire/district/{district_id}": "Start acquisition for a district",
            "GET /acquire/status/{district_id}": "Check acquisition status",
            "POST /triage/pdf": "Score a PDF for bell schedule content",
            "POST /patterns/learn": "Update learning patterns from feedback",
            "GET /patterns": "Get current learning patterns",
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
