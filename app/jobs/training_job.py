"""
Background training job runner.

Training is triggered by ``POST /train`` and runs asynchronously via
FastAPI's ``BackgroundTasks``. Job status is tracked in ``db.training_jobs``
(not in memory) so it survives service restarts.

Status transitions: ``queued → running → completed / failed``.
"""

import uuid
from datetime import datetime, timezone

import numpy as np

from app.core.db import get_db
from app.core.logging import get_logger
from app.ml.cnn.architecture import build_model
from app.ml.training.dataset import load_labeled_dataset
from app.ml.training.train import get_class_weights
from app.ml.training.evaluate import evaluate
from app.ml.cnn.model_registry import save_model_version

logger = get_logger(__name__)


async def run_training_job(job_id: str) -> None:
    """Execute a full training run: load data → build model → train → evaluate → save.

    Updates the job record in ``db.training_jobs`` at each stage.
    On failure, the job is marked ``"failed"`` with the error message.

    Args:
        job_id: The unique job ID (matches ``_id`` in ``db.training_jobs``).
    """
    db = get_db()

    # Mark as running
    await db.training_jobs.update_one(
        {"_id": job_id},
        {"$set": {"status": "running", "startedAt": datetime.now(timezone.utc)}},
    )
    logger.info("Training job %s started", job_id)

    try:
        # 1. Load dataset
        logger.info("Loading labeled dataset…")
        (
            train_texts,
            train_labels,
            train_categories,
            test_texts,
            test_labels,
            test_categories,
        ) = await load_labeled_dataset()

        logger.info(
            "Dataset loaded: %d train, %d test",
            len(train_texts),
            len(test_texts),
        )

        # 2. Compute class weights
        class_weights = get_class_weights(train_labels)

        # 3. Build model
        logger.info("Building RETVec+CNN model…")
        num_categories = train_categories.shape[1]
        model = build_model(num_categories=num_categories)

        # 4. Train
        logger.info("Starting training (10 epochs)…")
        model.fit(
            train_texts,
            {"label": train_labels, "categories": train_categories},
            class_weight={"label": class_weights},
            epochs=10,
            validation_split=0.1,
            verbose=1,
        )

        # 5. Evaluate on held-out test set
        logger.info("Evaluating on test set…")
        metrics = evaluate(model, test_texts, test_labels)

        # 6. Save model version as "candidate"
        version = f"v{uuid.uuid4().hex[:8]}"
        await save_model_version(model, metrics, version)

        # 7. Mark job as completed
        await db.training_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "completed",
                    "finishedAt": datetime.now(timezone.utc),
                    "resultVersion": version,
                    "metrics": metrics,
                }
            },
        )
        logger.info(
            "Training job %s completed — model %s (F1: %.4f)",
            job_id,
            version,
            metrics.get("f1", 0.0),
        )

    except Exception as e:
        logger.exception("Training job %s failed: %s", job_id, e)
        await db.training_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "finishedAt": datetime.now(timezone.utc),
                    "error": str(e),
                }
            },
        )
