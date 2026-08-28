"""
Seed script — inserts a dummy active model into Firebase Firestore and Storage.

Usage:
    python seed_dummy_model.py
"""

import asyncio
import os
import sys

# Ensure the project root is on sys.path so app.* imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.firebase import init_firebase, get_firestore_db
from app.ml.cnn.model_registry import DummyModel, save_model_version


async def seed():
    """Insert a dummy active model record into Firebase."""
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

    dummy = DummyModel()
    metrics = {
        "accuracy": 0.0,
        "f1": 0.0,
        "note": "Dummy model — always predicts 'safe'. Replace with a real trained model.",
    }

    await save_model_version(dummy, metrics, version="dummy-v0")

    # Set status to active directly
    db.collection("models").document("dummy-v0").update({"status": "active"})
    print("✓ Dummy model seeded as active in Firebase (version=dummy-v0)")


if __name__ == "__main__":
    asyncio.run(seed())
