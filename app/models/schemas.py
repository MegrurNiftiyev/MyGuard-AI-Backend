"""
Pydantic request/response models for the ML service API.
"""

from pydantic import BaseModel, Field
from typing import Literal


class ClassifyRequest(BaseModel):
    """Payload sent by the Node.js backend for document classification."""

    documentId: str = Field(..., description="ID of the document being classified")
    text: str = Field(
        ...,
        description="Already-extracted text (from Node's PDF/OCR layer), not a file",
    )
    language: str | None = Field(
        default=None,
        description="Optional language hint — RETVec doesn't require it",
    )


class ClassifyResponse(BaseModel):
    """Classification result returned to the Node.js backend."""

    label: Literal["safe", "suspicious", "injection"] = Field(
        ..., description="Predicted risk label"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model confidence score"
    )
    categories: list[str] = Field(
        default_factory=list,
        description='Detected attack categories, e.g. ["Instruction Override", "Ranking Manipulation"]',
    )


class ModelMetadataResponse(BaseModel):
    """Active model metadata (no raw weights)."""

    version: str
    metrics: dict
    createdAt: str
    status: str


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
