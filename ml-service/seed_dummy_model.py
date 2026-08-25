"""
Seed script — inserts a dummy model into MongoDB so the service can boot
and respond to /classify and /model/active without a real trained model.

Usage:
    python seed_dummy_model.py

Requires MONGO_URI and DB_NAME env vars (or a .env file in the working directory).
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Ensure the project root is on sys.path so app.* imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.db import connect_db, close_db, get_db
from app.ml.cnn.model_registry import DummyModel, serialize_model


async def seed():
    """Insert a dummy active model record."""
    await connect_db()
    db = get_db()

    # Check if an active model already exists
    existing = await db.models.find_one({"status": "active"})
    if existing is not None:
        print(f"Active model already exists: version={existing['version']}")
        print("Skipping seed. Delete it manually if you want to re-seed.")
        await close_db()
        return

    dummy = DummyModel()
    blob = serialize_model(dummy)

    record = {
        "version": "dummy-v0",
        "weightsBlob": blob,
        "metrics": {
            "accuracy": 0.0,
            "f1": 0.0,
            "note": "Dummy model — always predicts 'safe'. Replace with a real trained model.",
        },
        "status": "active",
        "createdAt": datetime.now(timezone.utc),
    }

    await db.models.insert_one(record)
    print("✓ Dummy model seeded as active (version=dummy-v0)")

    await close_db()


if __name__ == "__main__":
    asyncio.run(seed())
