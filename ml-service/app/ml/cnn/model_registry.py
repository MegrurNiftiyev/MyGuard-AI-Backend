"""
Model registry — load/save model versions against MongoDB.

Keeps an in-process cache so ``/classify`` doesn't hit the DB on every request.
Only reloads when the active model version actually changes.

Serialization uses TensorFlow SavedModel format packed into a zip archive
stored as binary in MongoDB (or object storage for large models).
"""

import io
import os
import pickle
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

import numpy as np

from app.core.db import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------
_cached_model = None
_cached_version: str | None = None


# ---------------------------------------------------------------------------
# Dummy model for testing (kept from Part 1 for backward-compat)
# ---------------------------------------------------------------------------
class DummyModel:
    """A stub model that returns a fixed prediction.

    Used so ``/classify`` and ``/model/active`` work end-to-end
    without a real trained TensorFlow model.
    """

    def predict(self, text):
        """Return a static safe prediction.

        Accepts either a string or numpy array (to mimic TF model interface).
        Always returns the tuple format used by the classify route adapter.
        """
        return ("safe", 0.95, [])


# ---------------------------------------------------------------------------
# TensorFlow serialization helpers
# ---------------------------------------------------------------------------
def serialize_model(model) -> bytes:
    """Serialize a model to bytes for storage in the database.

    For TensorFlow/Keras models: saves as SavedModel to a temp directory,
    zips it, and returns the zip bytes.

    For DummyModel (testing): falls back to pickle.
    """
    if isinstance(model, DummyModel):
        return pickle.dumps(model)

    # TensorFlow model — save to temp dir, zip, return bytes
    import tensorflow as tf  # noqa: delayed import

    tmp_dir = tempfile.mkdtemp(prefix="ml_model_")
    try:
        save_path = os.path.join(tmp_dir, "saved_model")
        model.save(save_path)

        # Zip the SavedModel directory into memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(save_path):
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    arc_name = os.path.relpath(abs_path, save_path)
                    zf.write(abs_path, arc_name)

        return buf.getvalue()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def deserialize_model(blob: bytes):
    """Deserialize model bytes back to a model object.

    Tries TensorFlow SavedModel (zip) first; falls back to pickle
    for DummyModel blobs.
    """
    # Check if it's a zip file (TF SavedModel)
    if blob[:4] == b"PK\x03\x04":  # zip magic bytes
        import tensorflow as tf  # noqa: delayed import

        tmp_dir = tempfile.mkdtemp(prefix="ml_model_load_")
        try:
            save_path = os.path.join(tmp_dir, "saved_model")
            os.makedirs(save_path, exist_ok=True)

            buf = io.BytesIO(blob)
            with zipfile.ZipFile(buf, "r") as zf:
                zf.extractall(save_path)

            model = tf.keras.models.load_model(save_path)
            return model
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        # Fallback: pickle (DummyModel or legacy)
        return pickle.loads(blob)  # noqa: S301 — controlled internal data only


# ---------------------------------------------------------------------------
# Prediction adapter
# ---------------------------------------------------------------------------
def run_prediction(model, text: str) -> tuple[str, float, list[str]]:
    """Run prediction on a single text and return (label, confidence, categories).

    Handles both DummyModel (returns tuple directly) and TF Keras models
    (returns numpy arrays from dual-output heads).
    """
    from app.ml.cnn.architecture import LABEL_NAMES, CATEGORY_NAMES

    if isinstance(model, DummyModel):
        return model.predict(text)

    # TF model expects a batch — wrap single text in numpy array
    input_array = np.array([[text]])
    predictions = model.predict(input_array, verbose=0)

    # predictions is a list: [label_probs, category_probs]
    label_probs = predictions[0][0]  # shape (3,)
    category_probs = predictions[1][0]  # shape (num_categories,)

    # Decode label: argmax of softmax
    label_idx = int(np.argmax(label_probs))
    label = LABEL_NAMES[label_idx]
    confidence = float(label_probs[label_idx])

    # Decode categories: threshold at 0.5
    categories = [
        CATEGORY_NAMES[i]
        for i, p in enumerate(category_probs)
        if p >= 0.5 and i < len(CATEGORY_NAMES)
    ]

    return (label, confidence, categories)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def load_active_model():
    """Load the currently active model from DB (with in-memory caching).

    On first call (or after version change), fetches the active model record
    from MongoDB, deserializes the weights blob, and caches the result.
    Subsequent calls return the cached model if the version hasn't changed.
    """
    global _cached_model, _cached_version

    db = get_db()
    active = await db.models.find_one(
        {"status": "active"}, sort=[("createdAt", -1)]
    )

    if active is None:
        raise RuntimeError("No active model found in database")

    version = active["version"]

    # Return cached model if version hasn't changed
    if _cached_version == version and _cached_model is not None:
        return _cached_model

    logger.info("Loading model version %s from database", version)
    _cached_model = deserialize_model(active["weightsBlob"])
    _cached_version = version
    return _cached_model


async def save_model_version(model, metrics: dict, version: str) -> None:
    """Persist a new model version to the database.

    New models are saved with status ``"candidate"`` — promotion to
    ``"active"`` is an explicit admin action via PATCH /model/{version}/promote.
    """
    db = get_db()
    blob = serialize_model(model)
    await db.models.insert_one(
        {
            "version": version,
            "weightsBlob": blob,
            "metrics": metrics,
            "status": "candidate",
            "createdAt": datetime.now(timezone.utc),
        }
    )
    logger.info("Saved model version %s as candidate", version)


async def promote_model_version(version: str) -> dict:
    """Promote a candidate model to active, demoting the current active model.

    Returns the promoted model's metadata, or raises if the version is not found
    or is not a candidate.
    """
    db = get_db()

    # Find the candidate
    candidate = await db.models.find_one({"version": version})
    if candidate is None:
        raise ValueError(f"Model version '{version}' not found")
    if candidate["status"] == "active":
        raise ValueError(f"Model version '{version}' is already active")

    # Demote current active model(s) to "inactive"
    await db.models.update_many(
        {"status": "active"},
        {"$set": {"status": "inactive"}},
    )

    # Promote the candidate
    await db.models.update_one(
        {"version": version},
        {"$set": {"status": "active"}},
    )

    # Invalidate cache so next /classify call loads the new model
    global _cached_model, _cached_version
    _cached_model = None
    _cached_version = None

    logger.info("Promoted model version %s to active", version)

    return {
        "version": candidate["version"],
        "metrics": candidate.get("metrics", {}),
        "status": "active",
    }


async def get_active_model_metadata() -> dict:
    """Return metadata for the active model (version, metrics, createdAt).

    Does NOT return the raw weights blob — this is for the admin panel.
    """
    db = get_db()
    active = await db.models.find_one(
        {"status": "active"}, sort=[("createdAt", -1)]
    )
    if active is None:
        return {"error": "No active model found", "version": None}

    return {
        "version": active["version"],
        "metrics": active.get("metrics", {}),
        "createdAt": active["createdAt"].isoformat()
        if isinstance(active["createdAt"], datetime)
        else str(active["createdAt"]),
        "status": active["status"],
    }
