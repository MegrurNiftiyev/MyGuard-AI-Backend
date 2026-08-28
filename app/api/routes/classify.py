"""
POST /classify — document text classification endpoint.
"""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies import verify_internal_service
from app.models.schemas import ClassifyRequest, ClassifyResponse
from app.ml.cnn.model_registry import load_active_model, run_prediction
from app.ml.preprocessing.normalize import basic_normalize
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
    """Run the active RETVec+CNN model on the provided text, OCR text, and hidden text."""
    try:
        model = await load_active_model()
    except Exception as e:
        logger.error("Classification model unavailable: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail={"error": "Classification model unavailable", "detail": str(e)}
        )

    # Combine text, ocrText, and hiddenText into a single input stream
    raw_parts = [req.text]
    if req.ocrText:
        raw_parts.append(req.ocrText)
    if req.hiddenText:
        raw_parts.append(req.hiddenText)

    combined_text = "\n".join(part for part in raw_parts if part and part.strip())
    cleaned = basic_normalize(combined_text)

    # run_prediction handles both DummyModel (tuple) and TF model (numpy arrays)
    label, confidence, categories = run_prediction(model, cleaned)

    logger.info(
        "Classified document %s (length: %d chars) → %s (confidence: %.2f)",
        req.documentId,
        len(cleaned),
        label,
        confidence,
    )

    return ClassifyResponse(
        label=label, confidence=confidence, categories=categories
    )
