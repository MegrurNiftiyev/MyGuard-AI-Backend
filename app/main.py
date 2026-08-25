"""
FastAPI application entrypoint.

Registers all routers and manages the DB connection lifecycle.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import connect_db, close_db
from app.core.logging import setup_logging, get_logger
from app.api.routes import classify, model_status, train

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    # Startup
    setup_logging()
    logger.info("Starting ML service…")
    await connect_db()
    logger.info("Database connected")

    # Optionally warm-load the active model so the first /classify call
    # doesn't incur a cold-start penalty. Failures here are non-fatal.
    try:
        from app.ml.cnn.model_registry import load_active_model

        await load_active_model()
        logger.info("Active model pre-loaded into cache")
    except RuntimeError:
        logger.warning(
            "No active model found on startup — /classify will fail until "
            "a model is seeded or trained"
        )

    yield

    # Shutdown
    await close_db()
    logger.info("ML service shut down")


app = FastAPI(
    title="MyGuard ML Service",
    description=(
        "Internal RETVec+CNN classification service. "
        "Called server-to-server by the Node.js backend — not exposed to end users."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(classify.router)
app.include_router(model_status.router)
app.include_router(train.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}
