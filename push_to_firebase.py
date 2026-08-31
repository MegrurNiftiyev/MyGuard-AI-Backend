import os
import sys
import asyncio
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

from app.core.firebase import init_firebase, get_storage_bucket, get_firestore_db
from app.ml.cnn.model_registry import promote_model_version

async def main():
    print("Initializing Firebase...")
    init_firebase()
    
    version = "real-dataset-v1"
    keras_model_path = r"c:\Users\megru\Desktop\Programlar\Github\MyGurad-IDDA-Final_project\Ai-Models\data\models\retvec_cnn_model.keras"
    storage_path = f"models/model_{version}.keras"
    
    print(f"Reading {keras_model_path}...")
    with open(keras_model_path, "rb") as f:
        blob_bytes = f.read()
    
    print("Uploading to Firebase Storage...")
    bucket = get_storage_bucket()
    blob = bucket.blob(storage_path)
    blob.upload_from_string(blob_bytes, content_type="application/octet-stream")
    print("Upload complete!")
    
    print("Creating Firestore document...")
    db = get_firestore_db()
    metrics = {
        "accuracy": 0.6667,
        "note": "Trained on real docx/pdf dataset. 100% Injection Recall."
    }
    db.collection("models").document(version).set({
        "version": version,
        "storagePath": storage_path,
        "metrics": metrics,
        "status": "candidate",
        "createdAt": datetime.now(timezone.utc),
    })
    
    print(f"Promoting model {version} to ACTIVE...")
    await promote_model_version(version)
    print("Model successfully pushed to Firebase and activated!")

if __name__ == "__main__":
    asyncio.run(main())
