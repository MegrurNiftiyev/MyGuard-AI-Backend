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
from app.api.routes import classify, model_status, train

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
        from app.ml.serving.registry import load_active_model

        model = await load_active_model()
        logger.info("Active model initialized successfully (cached)")
    except Exception as e:
        logger.warning("Active model initialization warning: %s", str(e))

    logger.info("==================================================================")
    logger.info("🚀 Swagger UI (Interactive API Docs): http://localhost:8000/api-docs")
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
    docs_url="/api-docs",
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


from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Format Pydantic validation errors into clean {code, message} JSON."""
    msg_parts = []
    for err in exc.errors():
        loc = ".".join(str(l) for l in err.get("loc", []) if str(l) != "body")
        msg = err.get("msg", "Invalid field")
        msg_parts.append(f"Field '{loc}' {msg.lower()}" if loc else msg)
    message = "; ".join(msg_parts) if msg_parts else "Unprocessable Entity validation error"

    return JSONResponse(
        status_code=422,
        content={
            "code": "UNPROCESSABLE_ENTITY",
            "message": message,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    """Format HTTP exceptions into clean {code, message} JSON."""
    detail = exc.detail
    if isinstance(detail, dict):
        message = detail.get("error") or detail.get("message") or detail.get("detail") or str(detail)
    else:
        message = str(detail)

    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        422: "UNPROCESSABLE_ENTITY",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "ERROR")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": message,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Catch unhandled internal server exceptions to prevent raw 500 server crashes."""
    logger.error("Unhandled server error on %s: %s", request.url.path, str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred while processing the request.",
        },
    )



@app.get("/", include_in_schema=False)
async def root():
    """Redirect root path to interactive Swagger UI documentation."""
    return RedirectResponse(url="/api-docs")


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}
