"""
KillMatch Backend - FastAPI Application

Main entry point for the KillMatch API with LangGraph multi-agent system.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    analytics,
    cover_letter,
    debate,
    headhunter,
    health,
    match,
    profile,
    resume_generator,
)
from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    setup_logging()
    yield
    # Shutdown (cleanup if needed)


# Create FastAPI application
app = FastAPI(
    title="KillMatch API",
    description="AI-powered job matching with multi-agent debates",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(profile.router, prefix="/api/v1", tags=["Profile"])
app.include_router(match.router, prefix="/api/v1", tags=["Match"])
app.include_router(cover_letter.router, prefix="/api/v1", tags=["Cover Letter"])
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
app.include_router(headhunter.router, prefix="/api/v1", tags=["Headhunter"])
app.include_router(debate.router, prefix="/api/v1/debate", tags=["Agent Debate"])
app.include_router(resume_generator.router, prefix="/api/v1", tags=["Resume Generator"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "KillMatch API",
        "version": "0.1.0",
        "docs": "/docs",
    }
