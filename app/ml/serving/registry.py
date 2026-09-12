"""
Model registry — load/save model versions against Firebase (Firestore & Storage).

Keeps an in-process cache so ``/classify`` doesn't hit Firebase on every request.
Only reloads when the active model version actually changes.

Model serialization uses TensorFlow SavedModel format packed into a zip archive
uploaded to Firebase Storage (directory: ``models/model_<version>.zip``).
Model metadata is stored in Firebase Firestore (collection: ``models``).
"""

import io
import os
import pickle
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

import numpy as np

from firebase_admin import firestore
from app.core.firebase import get_firestore_db, get_storage_bucket
from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------
_cached_model = None
_cached_version: str | None = None


# ---------------------------------------------------------------------------
# Dummy model for testing
# ---------------------------------------------------------------------------
class DummyModel:
    """A stub model that returns a fixed prediction.

    Used when no real trained model is stored in Firebase Storage.
    """

    def predict(self, text):
        return ("safe", 0.95)


# ---------------------------------------------------------------------------
# TensorFlow serialization helpers
# ---------------------------------------------------------------------------
def serialize_model(model) -> bytes:
    """Serialize a model to zip bytes for storage in Firebase Storage."""
    if isinstance(model, DummyModel):
        return pickle.dumps(model)

    import tensorflow as tf  # noqa: delayed import

    tmp_dir = tempfile.mkdtemp(prefix="ml_model_")
    try:
        save_path = os.path.join(tmp_dir, "model.keras")
        model.save(save_path)

        with open(save_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def deserialize_model(blob: bytes):
    """Deserialize model zip bytes back to a Keras model object."""
    if blob[:4] == b"PK\x03\x04":  # zip magic bytes
        import tensorflow as tf  # noqa: delayed import

        tmp_dir = tempfile.mkdtemp(prefix="ml_model_load_")
        try:
            save_path = os.path.join(tmp_dir, "model.keras")
            with open(save_path, "wb") as f:
                f.write(blob)

            from app.ml.cnn.architecture import RETVecTokenizer
            model = tf.keras.models.load_model(
                save_path,
                custom_objects={'RETVecTokenizer': RETVecTokenizer}
            )
            return model
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        return pickle.loads(blob)


# ---------------------------------------------------------------------------
# Public API backed by Firebase (Firestore & Storage)
# ---------------------------------------------------------------------------
def get_local_cache_path(version: str) -> str:
    """Return local disk cache file path for model version archive."""
    cache_dir = os.path.join(".", "data", "cache", "models")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"model_{version}.keras")


async def load_active_model():
    """Load the active model from local disk cache, Firebase Storage, or fallback."""
    global _cached_model, _cached_version

    if _cached_model is not None:
        return _cached_model

    db = get_firestore_db()
    bucket = get_storage_bucket()

    if db is not None:
        try:
            # Query active model record from Firestore without requiring a composite index
            docs = (
                db.collection("models")
                .where(filter=firestore.FieldFilter("status", "==", "active"))
                .get()
            )

            if docs:
                # Sort in memory by createdAt descending
                sorted_docs = sorted(
                    docs,
                    key=lambda d: d.to_dict().get("createdAt") or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
                active_doc = sorted_docs[0].to_dict()
                version = active_doc.get("version", sorted_docs[0].id)
                storage_path = active_doc.get("storagePath", f"models/model_{version}.keras")
                local_cache_file = get_local_cache_path(version)

                # 1. Check local disk cache first (fast start on Render / local)
                if os.path.exists(local_cache_file):
                    logger.info("Loaded active model %s from local disk cache (%s)", version, local_cache_file)
                    with open(local_cache_file, "rb") as f:
                        model_bytes = f.read()
                # 2. Download from Firebase Storage if not cached locally
                elif bucket is not None:
                    logger.info("Downloading active model %s from Firebase Storage (%s)", version, storage_path)
                    blob = bucket.blob(storage_path)
                    model_bytes = blob.download_as_bytes()

                    # Cache to disk for subsequent restarts
                    try:
                        with open(local_cache_file, "wb") as f:
                            f.write(model_bytes)
                        logger.info("Cached active model %s to local disk (%s)", version, local_cache_file)
                    except Exception as err:
                        logger.warning("Could not write to model disk cache: %s", str(err))
                else:
                    raise RuntimeError("Firebase Storage bucket unavailable and local cache missing.")

                _cached_model = deserialize_model(model_bytes)
                _cached_version = version
                logger.info("Active model version %s loaded into memory", version)
                return _cached_model
            else:
                logger.warning("No active model record found in Firestore. Fallback to local trained disk model.")
        except Exception as e:
            logger.warning("Failed to load active model from Firebase (%s). Fallback to local trained disk model.", str(e))

    # Check if a real trained model exists on local disk
    local_paths = [
        os.path.join(".", "data", "models", "retvec_cnn_model.keras"),
        os.path.join(".", "data", "cache", "active_model.keras"),
    ]
    for lp in local_paths:
        if os.path.exists(lp):
            try:
                import tf_keras as keras
                from app.ml.cnn.architecture import RETVecTokenizer
                model = keras.models.load_model(
                    lp, custom_objects={"RETVecTokenizer": RETVecTokenizer}
                )
                _cached_model = model
                _cached_version = "real-local-v1"
                logger.info("Loaded active trained model from local disk (%s)", lp)
                return _cached_model
            except Exception as e:
                logger.warning("Could not load local model from %s: %s", lp, str(e))

    if settings.ALLOW_DUMMY_MODEL_FALLBACK:
        # In-memory fallback
        logger.info("Using in-memory DummyModel fallback (version: dummy-v0)")
        _cached_model = DummyModel()
        _cached_version = "dummy-v0"
        return _cached_model

    raise RuntimeError("Classification model unavailable: No active model in Firebase or local disk.")


async def save_model_version(
    model,
    metrics: dict,
    version: str,
    status: str = "candidate",
    source_commit: str | None = None,
    description: str | None = None,
) -> None:
    """Persist a new model version to Firebase Storage and Firestore."""
    blob_bytes = serialize_model(model)
    storage_path = f"models/model_{version}.zip"

    # 1. Save locally to cache so it can be pushed and used locally
    local_path = get_local_cache_path(version)
    with open(local_path, "wb") as f:
        f.write(blob_bytes)
    logger.info("Saved model to local cache at %s", local_path)

    # 2. Upload model zip archive to Firebase Storage
    bucket = get_storage_bucket()
    if bucket is not None:
        try:
            blob = bucket.blob(storage_path)
            blob.upload_from_string(blob_bytes, content_type="application/zip")
            logger.info("Uploaded model binary to Firebase Storage at %s", storage_path)
        except Exception as e:
            logger.error("Failed to upload model zip to Firebase Storage: %s", str(e))
            # Continue anyway since it's saved locally

    # 3. Save metadata document to Firebase Firestore
    db = get_firestore_db()
    if db is not None:
        try:
            doc_data = {
                "version": version,
                "storagePath": storage_path,
                "metrics": metrics,
                "status": status,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
            if source_commit:
                doc_data["sourceCommit"] = source_commit
            if description:
                doc_data["description"] = description

            db.collection("models").document(version).set(doc_data)
            logger.info("Saved model version %s record as %s in Firestore", version, status)
        except Exception as e:
            logger.error("Failed to save model metadata in Firestore: %s", str(e))
            raise


async def promote_model_version(version: str) -> dict:
    """Promote a candidate model version to active in Firestore."""
    db = get_firestore_db()
    if db is None:
        raise RuntimeError("Firebase Firestore is not initialized")

    doc_ref = db.collection("models").document(version)
    doc = doc_ref.get()

    if not doc.exists:
        raise ValueError(f"Model version '{version}' not found in Firestore")

    data = doc.to_dict()
    if data.get("status") == "active":
        raise ValueError(f"Model version '{version}' is already active")

    # Demote existing active models
    active_docs = db.collection("models").where(filter=firestore.FieldFilter("status", "==", "active")).get()
    for active_doc in active_docs:
        active_doc.reference.update({"status": "archived"})

    # Promote target version
    doc_ref.update({"status": "active"})

    # Invalidate in-memory cache
    global _cached_model, _cached_version
    _cached_model = None
    _cached_version = None

    logger.info("Promoted model version %s to active in Firestore", version)

    return {
        "version": version,
        "metrics": data.get("metrics", {}),
        "status": "active",
    }


async def get_active_model_metadata() -> dict:
    """Return metadata for the active model from Firestore."""
    db = get_firestore_db()
    if db is not None:
        try:
            docs = (
                db.collection("models")
                .where(filter=firestore.FieldFilter("status", "==", "active"))
                .get()
            )
            if docs:
                sorted_docs = sorted(
                    docs,
                    key=lambda d: d.to_dict().get("createdAt") or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
                data = sorted_docs[0].to_dict()
                created_at = data.get("createdAt")
                return {
                    "version": data.get("version", sorted_docs[0].id),
                    "metrics": data.get("metrics", {}),
                    "description": data.get("description", ""),
                    "sourceCommit": data.get("sourceCommit", ""),
                    "storagePath": data.get("storagePath", ""),
                    "createdAt": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
                    "status": data.get("status", "active"),
                    "isCurrentVersion": True,
                }
        except Exception as e:
            logger.warning("Failed to fetch active model metadata from Firestore: %s", str(e))

    return {
        "version": _cached_version or "dummy-v0",
        "metrics": {"note": "In-memory standalone fallback (Firebase model not uploaded yet)"},
        "description": "Standalone fallback model",
        "sourceCommit": "",
        "storagePath": "",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "isCurrentVersion": True,
    }


def extract_run_number(v: str) -> int | None:
    """Extract integer run number from version string (e.g. 'run-05' -> 5)."""
    if v and v.startswith("run-"):
        try:
            return int(v.split("-")[1])
        except (IndexError, ValueError):
            pass
    return None


async def get_all_models_metadata(
    version: str | None = None,
    version_min: str | None = None,
    version_max: str | None = None,
    min_accuracy: float | None = None,
    max_accuracy: float | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Fetch all model metadata records from Firestore with optional filtering parameters."""
    db = get_firestore_db()
    if db is None:
        return []

    try:
        docs = db.collection("models").get()
    except Exception as e:
        logger.error("Failed to fetch models from Firestore: %s", str(e))
        return []

    all_models = []

    for doc in docs:
        d = doc.to_dict()
        ver = d.get("version") or doc.id
        m_status = d.get("status", "archived")
        is_current = (m_status == "active")
        created_at = d.get("createdAt")
        created_at_str = (
            created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        ) if created_at else None

        item = {
            "version": ver,
            "status": m_status,
            "isCurrentVersion": is_current,
            "metrics": d.get("metrics", {}),
            "description": d.get("description", ""),
            "sourceCommit": d.get("sourceCommit", ""),
            "storagePath": d.get("storagePath", ""),
            "createdAt": created_at_str,
        }
        all_models.append(item)

    # Sort all_models descending by run number / date
    def sort_key(m):
        r_num = extract_run_number(m["version"])
        if r_num is not None:
            return (1, r_num)
        return (0, m["createdAt"] or "")

    all_models.sort(key=sort_key, reverse=True)

    # Filtering logic
    filtered = []
    min_v_num = extract_run_number(version_min) if version_min else None
    max_v_num = extract_run_number(version_max) if version_max else None

    for m in all_models:
        v_str = m["version"]
        r_num = extract_run_number(v_str)
        metrics = m.get("metrics") or {}
        
        test_acc = metrics.get("test_acc")
        if test_acc is None:
            test_acc = metrics.get("accuracy")

        # 1. Exact version filter
        if version and v_str.lower() != version.lower():
            continue

        # 2. Min version filter
        if version_min:
            if min_v_num is not None and r_num is not None:
                if r_num < min_v_num:
                    continue
            elif v_str < version_min:
                continue

        # 3. Max version filter
        if version_max:
            if max_v_num is not None and r_num is not None:
                if r_num > max_v_num:
                    continue
            elif v_str > version_max:
                continue

        # 4. Min accuracy filter
        if min_accuracy is not None:
            if test_acc is None or float(test_acc) < min_accuracy:
                continue

        # 5. Max accuracy filter
        if max_accuracy is not None:
            if test_acc is None or float(test_acc) > max_accuracy:
                continue

        # 6. Status filter
        if status and m["status"].lower() != status.lower():
            continue

        # 7. Date filters
        if min_date and m["createdAt"]:
            if m["createdAt"] < min_date:
                continue
        if max_date and m["createdAt"]:
            if m["createdAt"] > max_date:
                continue

        filtered.append(m)

    return filtered
