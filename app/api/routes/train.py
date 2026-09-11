"""
Training endpoints.

POST /train             — trigger a background training job
GET  /train/status/{job_id} — check training job status
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import verify_internal_service
from app.models.schemas import TrainingJobResponse, ErrorResponse
from app.core.firebase import get_firestore_db
from app.jobs.training_job import run_training_job

router = APIRouter(prefix="/train", tags=["Training"])


@router.post(
    "",
    response_model=TrainingJobResponse,
    dependencies=[Depends(verify_internal_service)],
    summary="Trigger a model training job",
    description=(
        "Creates a background training job that loads labeled documents from Supabase, "
        "trains a new RETVec+CNN model, evaluates it, and stores the resulting model "
        "to Firebase Storage and Firestore. Returns the job ID immediately."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized — Missing or invalid X-Internal-Token header"},
        403: {"model": ErrorResponse, "description": "Forbidden — Client IP banned due to 3 failed token attempts"},
        500: {"model": ErrorResponse, "description": "Internal Server Error — Failed to initialize training record in Firestore"},
    },
)
async def start_training(background_tasks: BackgroundTasks):
    """Start a new training job in the background."""
    db = get_firestore_db()
    job_id = str(uuid.uuid4())

    # Create job record in Firestore (survives service restarts)
    if db is not None:
        try:
            db.collection("training_jobs").document(job_id).set(
                {
                    "jobId": job_id,
                    "status": "queued",
                    "createdAt": datetime.now(timezone.utc),
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create job in Firestore: {str(e)}")

    # Launch training as a background task
    background_tasks.add_task(run_training_job, job_id)

    return {"jobId": job_id, "status": "queued"}
