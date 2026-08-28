"""
Training endpoints.

POST /train             — trigger a background training job
GET  /train/status/{job_id} — check training job status
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import verify_internal_service
from app.core.firebase import get_firestore_db
from app.jobs.training_job import run_training_job

router = APIRouter(prefix="/train", tags=["Training"])


@router.post(
    "",
    dependencies=[Depends(verify_internal_service)],
    summary="Trigger a model training job",
    description=(
        "Creates a background training job that loads labeled documents from Supabase, "
        "trains a new RETVec+CNN model, evaluates it, and stores the resulting model "
        "to Firebase Storage and Firestore. Returns the job ID immediately."
    ),
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


@router.get(
    "/status/{job_id}",
    dependencies=[Depends(verify_internal_service)],
    summary="Get training job status",
    description=(
        "Returns the current status of a training job from Firestore, including metrics "
        "and the resulting model version if completed."
    ),
)
async def training_status(job_id: str):
    """Check the status of a training job."""
    db = get_firestore_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    doc = db.collection("training_jobs").document(job_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Job not found")

    job = doc.to_dict()
    result = {
        "jobId": job.get("jobId", job_id),
        "status": job.get("status", "unknown"),
        "createdAt": job.get("createdAt", "").isoformat()
        if hasattr(job.get("createdAt", ""), "isoformat")
        else str(job.get("createdAt", "")),
    }

    if "startedAt" in job:
        result["startedAt"] = (
            job["startedAt"].isoformat()
            if hasattr(job["startedAt"], "isoformat")
            else str(job["startedAt"])
        )
    if "finishedAt" in job:
        result["finishedAt"] = (
            job["finishedAt"].isoformat()
            if hasattr(job["finishedAt"], "isoformat")
            else str(job["finishedAt"])
        )
    if "resultVersion" in job:
        result["resultVersion"] = job["resultVersion"]
    if "metrics" in job:
        result["metrics"] = job["metrics"]
    if "error" in job:
        result["error"] = job["error"]

    return result
