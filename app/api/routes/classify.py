"""
POST /classify — document text classification endpoint.
"""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies import verify_internal_service
from app.models.schemas import ClassifyRequest, ClassifyResponse
from app.ml.cnn.model_registry import load_active_model, run_prediction
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/classify", tags=["Classification"])


@router.post(
    "",
    response_model=ClassifyResponse,
    dependencies=[Depends(verify_internal_service)],
    summary="Classify extracted document text",
    description=(
        "Accepts already-extracted text (from the Node.js PDF/OCR layer) "
        "and returns a risk label, confidence score, and detected attack categories."
    ),
)
async def classify(
    req: ClassifyRequest,
):
    """Run the active RETVec+CNN model on fullText."""
    words = req.fullText.strip().split() if req.fullText else []
    if len(words) < 5:
        raise HTTPException(
            status_code=503,
            detail="insufficient_text"
        )

    try:
        model = await load_active_model()
    except Exception as e:
        logger.error("Classification model unavailable: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail={"error": "Classification model unavailable", "detail": str(e)}
        )

    label, confidence = run_prediction(model, req.fullText)

    logger.info(
        "Classified document %s (length: %d chars, words: %d) → %s (confidence: %.2f)",
        req.documentId,
        len(req.fullText),
        len(words),
        label,
        confidence,
    )

    return ClassifyResponse(
        label=label, confidence=confidence
    )
