"""
Model status and promotion endpoints.

GET  /model/active                      — active model metadata
GET  /model/all-models                  — list all models with rich query parameter filters
POST /model/change-version/{version_id} — promote a model version to active
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import verify_internal_service
from app.models.schemas import ModelMetadataResponse, AllModelsResponse, ErrorResponse
from app.ml.serving.registry import (
    get_active_model_metadata,
    get_all_models_metadata,
    promote_model_version,
)

router = APIRouter(prefix="/model", tags=["Model"])


@router.get(
    "/active",
    response_model=ModelMetadataResponse,
    summary="Get active model metadata",
    description=(
        "Returns the version, metrics, and creation timestamp of the currently "
        "active model. Does NOT return the raw weights — this is for visibility "
        "and debugging (e.g. the Node admin panel)."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized — Missing or invalid X-Internal-Token header"},
        403: {"model": ErrorResponse, "description": "Forbidden — Client IP banned due to 3 failed token attempts"},
    },
)
async def model_active():
    """Return metadata for the currently active model."""
    meta = await get_active_model_metadata()
    return meta


@router.get(
    "/all-models",
    response_model=AllModelsResponse,
    summary="List all models with optional query parameter filters",
    description=(
        "Retrieves all model metadata records from Firestore. Supports filtering by "
        "version, version range (version_min, version_max), test accuracy range (min_accuracy, max_accuracy), "
        "creation date range (min_date, max_date), and status. Each returned model item includes `isCurrentVersion: true/false`."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized — Missing or invalid X-Internal-Token header"},
        403: {"model": ErrorResponse, "description": "Forbidden — Client IP banned due to 3 failed token attempts"},
    },
)
async def get_all_models(
    version: str | None = Query(None, description="Exact version filter (e.g. run-10)"),
    version_min: str | None = Query(None, description="Minimum version string filter (e.g. run-05)"),
    version_max: str | None = Query(None, description="Maximum version string filter (e.g. run-11)"),
    min_accuracy: float | None = Query(None, description="Minimum test accuracy filter (0.0 - 1.0)"),
    max_accuracy: float | None = Query(None, description="Maximum test accuracy filter (0.0 - 1.0)"),
    min_date: str | None = Query(None, description="Minimum creation date filter (ISO date format)"),
    max_date: str | None = Query(None, description="Maximum creation date filter (ISO date format)"),
    status: str | None = Query(None, description="Filter by status ('active', 'archived', 'candidate')"),
):
    """Retrieve all models with query parameter filtering."""
    models_list = await get_all_models_metadata(
        version=version,
        version_min=version_min,
        version_max=version_max,
        min_accuracy=min_accuracy,
        max_accuracy=max_accuracy,
        min_date=min_date,
        max_date=max_date,
        status=status,
    )
    return AllModelsResponse(total=len(models_list), models=models_list)


@router.post(
    "/change-version/{version_id}",
    dependencies=[Depends(verify_internal_service)],
    summary="Change active model version",
    description=(
        "Promotes a model version to active, demoting the currently "
        "active model to archived. This keeps a human in the loop — new models are never "
        "auto-promoted, even if their metrics are better."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request — Invalid or nonexistent model version"},
        401: {"model": ErrorResponse, "description": "Unauthorized — Missing or invalid X-Internal-Token header"},
        403: {"model": ErrorResponse, "description": "Forbidden — Client IP banned due to 3 failed token attempts"},
    },
)
async def change_active_version(version_id: str):
    """Promote a model version to active."""
    try:
        result = await promote_model_version(version_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

