"""FastAPI Core Entry Point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .api.endpoints import router as api_router
from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting Personal Meeting Intelligence Agent API")
    logger.info("Initializing database")
    await init_db()

    # Pre-warm search index
    from .search.index import get_search_index

    get_search_index()

    yield

    # Shutdown actions
    logger.info("Stopping Personal Meeting Intelligence Agent API")


_is_production = settings.app_env.lower() == "production"

app = FastAPI(
    title="Personal Meeting Intelligence Agent API",
    description="Speech-to-text, LangGraph agents, Qdrant hybrid search, and MCP action tools.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# CORS configurations
_cors_origins = settings.cors_origins
if settings.app_env.lower() != "production" and not _cors_origins:
    _cors_origins = ["http://localhost:5173", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Route registration
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "pmia-backend"}
