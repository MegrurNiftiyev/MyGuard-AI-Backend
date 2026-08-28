import asyncio
import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"
from app.services.supabase_dataset import dataset_service
from app.jobs.training_job import run_training_job
from app.ml.cnn.model_registry import promote_model_version
from app.core.firebase import init_firebase, get_firestore_db

async def main():
    print("Initializing Firebase...")
    init_firebase()
    
    print("Skipping direct dataset sync, will rely on load_labeled_dataset's internal sync and bootstrap samples...")

    print("Running training job...")
    job_id = "local-training-job-1"
    
    # Create an initial training job document so it doesn't fail on update
    db = get_firestore_db()
    if db:
        db.collection("training_jobs").document(job_id).set({
            "status": "queued"
        })
        
    await run_training_job(job_id)
    print("Training job complete.")
    
    # Retrieve the version that was generated
    if db:
        doc = db.collection("training_jobs").document(job_id).get()
        if doc.exists:
            version = doc.to_dict().get("resultVersion")
            if version:
                print(f"Promoting model version {version}...")
                await promote_model_version(version)
                print("Model promoted successfully. It is now active in Firebase.")

if __name__ == "__main__":
    # Force TensorFlow to only use CPU to avoid CUDA errors if not setup
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    asyncio.run(main())
