"""
Seed script — inserts a base initial model into Firebase Firestore and Storage.

Usage:
    python seed_model.py
    python -m app.scripts.seed_model
"""

import asyncio
import os
import sys

# Ensure the project root is on sys.path so app.* imports work
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.firebase import init_firebase, get_firestore_db
from app.ml.cnn.model_registry import DummyModel, save_model_version


async def seed():
    """Insert an initial base model record into Firebase."""
    init_firebase()
    db = get_firestore_db()

    if db is None:
        print("Firebase Firestore not initialized. Ensure FIREBASE_CREDENTIALS_PATH or JSON is set.")
        return

    # Check if an active model already exists
    active_docs = db.collection("models").where("status", "==", "active").limit(1).get()
    if active_docs:
        doc = active_docs[0].to_dict()
        print(f"Active model already exists in Firebase: version={doc.get('version', active_docs[0].id)}")
        return

    model_obj = DummyModel()
    metrics = {
        "accuracy": 0.85,
        "f1": 0.88,
        "note": "Initial base model.",
    }

    await save_model_version(model_obj, metrics, version="v1.0.0")

    # Set status to active directly
    db.collection("models").document("v1.0.0").update({"status": "active"})
    print("✓ Initial base model seeded as active in Firebase (version=v1.0.0)")


def main():
    asyncio.run(seed())


if __name__ == "__main__":
    main()
