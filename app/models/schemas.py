"""
Pydantic request/response models for the ML service API.
"""

from pydantic import BaseModel, Field
from typing import Literal


class ClassifyRequest(BaseModel):
    """Payload sent by the Node.js backend for document classification."""

    model_config = {"extra": "forbid"}

    documentId: str | None = Field(default="N/A", description="Optional ID of the document being classified")
    fullText: str = Field(
        ...,
        description="Full extracted document text matching training input shape",
    )


class ClassifyResponse(BaseModel):
    """Classification result returned to the Node.js backend."""

    label: Literal["safe", "suspicious", "injection"] = Field(
        ..., description="Predicted risk label"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model confidence score"
    )


class ModelMetadataResponse(BaseModel):
    """Active model metadata (no raw weights)."""

    version: str
    metrics: dict
    createdAt: str
    status: str
    description: str | None = None
    sourceCommit: str | None = None
    storagePath: str | None = None
    isCurrentVersion: bool = True


class ModelDetailItem(BaseModel):
    """Detailed model metadata with isCurrentVersion flag."""

    version: str
    status: str
    isCurrentVersion: bool = False
    metrics: dict = {}
    description: str | None = None
    sourceCommit: str | None = None
    storagePath: str | None = None
    createdAt: str | None = None


class AllModelsResponse(BaseModel):
    """List of all models returned by GET /model/all-models."""

    total: int
    models: list[ModelDetailItem]


class TrainingJobResponse(BaseModel):
    """Training job status response."""

    jobId: str = Field(..., description="Unique job identifier")
    status: Literal["queued", "running", "completed", "failed"] = Field(
        ..., description="Current job status"
    )
    createdAt: str | None = None
    startedAt: str | None = None
    finishedAt: str | None = None
    resultVersion: str | None = Field(
        default=None, description="Model version produced (if completed)"
    )
    metrics: dict | None = Field(
        default=None, description="Evaluation metrics (if completed)"
    )
    error: str | None = Field(
        default=None, description="Error message (if failed)"
    )


class ErrorResponse(BaseModel):
    """Standardized error response payload."""

    code: str = Field(
        ...,
        description="Error classification code (e.g. UNPROCESSABLE_ENTITY, UNAUTHORIZED, FORBIDDEN, SERVICE_UNAVAILABLE)",
        json_schema_extra={"example": "UNPROCESSABLE_ENTITY"},
    )
    message: str = Field(
        ...,
        description="Human-readable error explanation",
        json_schema_extra={"example": "Field 'fullText' is required"},
    )
