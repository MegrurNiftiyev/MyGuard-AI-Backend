"""
Script to upload trained local Keras model to Firebase Storage and promote it.

Usage:
    python push_to_firebase.py
    python -m app.scripts.push_to_firebase
"""

import os
import sys
import asyncio
from datetime import datetime, timezone

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

sys.stdout.reconfigure(encoding='utf-8')

from app.core.firebase import init_firebase, get_storage_bucket, get_firestore_db
from app.ml.serving.registry import promote_model_version


async def push_to_firebase():
    print("Initializing Firebase...")
    init_firebase()
    
    version = "real-dataset-v10"
    keras_model_path = os.path.join(BASE_DIR, "data", "models", "retvec_cnn_model.keras")
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
        "accuracy": 0.9874,
        "note": "Run #10 model trained on 510 real admin docs (AZ + ENG). 98.74% Val Acc, 0% FP rate on safe docs."
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


def main():
    asyncio.run(push_to_firebase())


if __name__ == "__main__":
    main()
