"""
Model status and promotion endpoints.

GET   /model/active            — active model metadata
PATCH /model/{version}/promote — promote a candidate model to active
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import verify_internal_service
from app.models.schemas import ModelMetadataResponse, ErrorResponse
from app.ml.serving.registry import get_active_model_metadata, promote_model_version

router = APIRouter(prefix="/model", tags=["Model"])


@router.get(
    "/active",
    response_model=ModelMetadataResponse,
    dependencies=[Depends(verify_internal_service)],
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


@router.patch(
    "/{version}/promote",
    dependencies=[Depends(verify_internal_service)],
    summary="Promote a candidate model to active",
    description=(
        "Promotes a candidate model version to active, demoting the current "
        "active model. This keeps a human in the loop — new models are never "
        "auto-promoted, even if their metrics are better."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request — Invalid or nonexistent candidate model version"},
        401: {"model": ErrorResponse, "description": "Unauthorized — Missing or invalid X-Internal-Token header"},
        403: {"model": ErrorResponse, "description": "Forbidden — Client IP banned due to 3 failed token attempts"},
    },
)
async def promote_model(version: str):
    """Promote a candidate model to active."""
    try:
        result = await promote_model_version(version)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
