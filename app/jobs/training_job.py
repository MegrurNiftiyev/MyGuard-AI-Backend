"""
Background training job runner.

Training is triggered by ``POST /train`` and runs asynchronously via
FastAPI's ``BackgroundTasks``. Job status is tracked in Firestore ``training_jobs``
collection so it survives service restarts.

Status transitions: ``queued → running → completed / failed``.
"""

import uuid
from datetime import datetime, timezone

import numpy as np

from app.core.firebase import get_firestore_db
from app.core.logging import get_logger
from app.ml.cnn.architecture import build_model
from app.ml.training.data.loader import load_labeled_dataset
from app.ml.training.train import get_class_weights
from app.ml.training.evaluate import evaluate
from app.ml.serving.registry import save_model_version

logger = get_logger(__name__)


async def run_training_job(job_id: str) -> None:
    """Execute a full training run: load data → build model → train → evaluate → save to Firebase.

    Updates the job record in Firestore ``training_jobs`` collection at each stage.
    """
    db = get_firestore_db()

    # Mark as running
    if db is not None:
        try:
            db.collection("training_jobs").document(job_id).update(
                {"status": "running", "startedAt": datetime.now(timezone.utc)}
            )
        except Exception as e:
            logger.warning("Failed to update job %s running status in Firestore: %s", job_id, str(e))

    logger.info("Training job %s started", job_id)

    try:
        # 1. Load dataset from Supabase / raw storage
        logger.info("Loading labeled dataset from Supabase…")
        (
            train_texts,
            train_labels,
            test_texts,
            test_labels,
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
        model = build_model()

        # 4. Train
        logger.info("Starting training (10 epochs)…")
        model.fit(
            train_texts,
            train_labels,
            epochs=10,
            validation_split=0.1,
            verbose=1,
        )

        # 5. Evaluate on held-out test set
        logger.info("Evaluating on test set…")
        metrics = evaluate(model, test_texts, test_labels)

        # 6. Save model version to Firebase Storage & Firestore
        version = f"v{uuid.uuid4().hex[:8]}"
        await save_model_version(model, metrics, version)

        # 7. Mark job as completed in Firestore
        if db is not None:
            try:
                db.collection("training_jobs").document(job_id).update(
                    {
                        "status": "completed",
                        "finishedAt": datetime.now(timezone.utc),
                        "resultVersion": version,
                        "metrics": metrics,
                    }
                )
            except Exception as e:
                logger.warning("Failed to update job %s completion in Firestore: %s", job_id, str(e))

        logger.info(
            "Training job %s completed — model %s (F1: %.4f)",
            job_id,
            version,
            metrics.get("f1", 0.0),
        )

    except Exception as e:
        logger.exception("Training job %s failed: %s", job_id, e)
        if db is not None:
            try:
                db.collection("training_jobs").document(job_id).update(
                    {
                        "status": "failed",
                        "finishedAt": datetime.now(timezone.utc),
                        "error": str(e),
                    }
                )
            except Exception as err:
                logger.error("Failed to update job %s error status in Firestore: %s", job_id, str(err))
