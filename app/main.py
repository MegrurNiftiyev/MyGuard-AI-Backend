"""
FastAPI application entrypoint.

Registers all routers and manages the DB connection lifecycle.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.firebase import init_firebase
from app.api.routes import classify, model_status, train, dataset

from fastapi.responses import RedirectResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    # Startup
    setup_logging()
    logger.info("Starting ML service…")

    # Initialize Firebase Admin SDK
    init_firebase()

    # Warm-load model (fetches active model from Firebase Storage/Firestore or uses DummyModel fallback)
    try:
        from app.ml.cnn.model_registry import load_active_model

        model = await load_active_model()
        logger.info("Active model initialized successfully (cached)")
    except Exception as e:
        logger.warning("Active model initialization warning: %s", str(e))

    logger.info("==================================================================")
    logger.info("🚀 Swagger UI (Interactive API Docs): http://localhost:8000/docs")
    logger.info("==================================================================")

    yield

    # Shutdown
    logger.info("ML service shut down")


app = FastAPI(
    title="MyGuard ML Service",
    description=(
        "Internal RETVec+CNN classification service. "
        "Called server-to-server by the Node.js backend — not exposed to end users."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware (Restricts origins to Render backend + Swagger UI / Localhost testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(classify.router)
app.include_router(model_status.router)
app.include_router(train.router)
app.include_router(dataset.router)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root path to interactive Swagger UI documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}
