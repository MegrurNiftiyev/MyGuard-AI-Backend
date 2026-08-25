# Part 1/3 — FastAPI ML Service: Setup, Folder Structure, Core Endpoints

## Context

This is a new, separate Python/FastAPI service that sits alongside an existing Node.js backend (MyGuard AI Document Security Gateway). The Node.js API already exposes the full public-facing REST surface (auth, documents, security actions, chat, admin/models registry — see Swagger doc). This FastAPI service is **internal only** — not exposed to end users directly, only called server-to-server by the Node.js backend.

Responsibility split (do not implement anything outside this scope):
- **This service owns**: the RETVec-based classification model (Layer 2 of the pipeline), training/retraining, and model versioning storage.
- **This service does NOT own**: OCR, PDF text extraction, document storage, auth, chat sessions, or the external LLM call (Layer 3) — those stay in Node.js.

## Critical architectural constraint: stateless service

The FastAPI service must **not** rely on local disk or in-memory state surviving a restart. Model weights are not baked into the container or saved to a local file as the source of truth. On cold start (or whenever the active model changes), the service loads the current model weights from the database. Keep this in mind throughout: any "save model" step writes to DB (or DB-referenced object storage), and any "load model" step reads from DB.

## Folder structure

```
ml-service/
  app/
    main.py                      # FastAPI app entrypoint, router registration
    core/
      config.py                  # env vars, settings (DB connection string, service auth token)
      db.py                      # DB client/connection setup
      logging.py
    models/
      schemas.py                 # Pydantic request/response models
    ml/
      retvec/
        tokenizer.py             # RETVec tokenizer wrapper (loads retvec package)
      cnn/
        architecture.py          # CNN classification head on top of RETVec embeddings
        model_registry.py        # load_active_model(), save_model_version(), in-memory cache with DB-backed source of truth
      preprocessing/
        normalize.py             # text normalization before tokenization (whitespace, case — NOT a substitute for RETVec, just basic cleanup)
      training/
        dataset.py                # loads labeled documents from DB into train/val/test splits
        train.py                  # training loop (see Part 2)
        evaluate.py               # precision/recall/F1 computation on held-out test set
    api/
      routes/
        classify.py               # POST /classify
        model_status.py           # GET /model/active
        train.py                  # POST /train, GET /train/status/{jobId}  (see Part 2)
      dependencies.py             # shared auth dependency for service-to-service calls
    jobs/
      training_job.py             # background job runner (see Part 2)
  tests/
    test_classify.py
    test_model_registry.py
  requirements.txt
  Dockerfile
```

## 1. Service-to-service auth

This API is never called by end users, only by the Node.js backend. Do not build user-facing JWT auth here — implement a simple shared-secret header check instead:

```python
# app/api/dependencies.py
from fastapi import Header, HTTPException
from app.core.config import settings

async def verify_internal_service(x_internal_token: str = Header(...)):
    if x_internal_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized service call")
```

Apply this as a dependency on every route in this service.

## 2. Model registry (stateless load/save)

```python
# app/ml/cnn/model_registry.py
from app.core.db import get_db

_cached_model = None
_cached_version = None

async def load_active_model():
    global _cached_model, _cached_version
    db = get_db()
    active = await db.models.find_one({"status": "active"}, sort=[("createdAt", -1)])
    if active is None:
        raise RuntimeError("No active model found in database")
    if _cached_version == active["version"]:
        return _cached_model  # avoid re-deserializing on every request
    _cached_model = deserialize_model(active["weightsBlob"])
    _cached_version = active["version"]
    return _cached_model

async def save_model_version(model, metrics: dict, version: str):
    db = get_db()
    blob = serialize_model(model)
    await db.models.insert_one({
        "version": version,
        "weightsBlob": blob,
        "metrics": metrics,
        "status": "candidate",   # promoted to "active" explicitly, not automatically — see Part 2
        "createdAt": datetime.utcnow(),
    })
```

Notes:
- `deserialize_model` / `serialize_model` — use whatever the training framework supports (e.g. TensorFlow `SavedModel` bytes, or `.h5` bytes) stored as a binary field or as a reference to object storage if the weights are too large for the DB's document size limit — check the DB's max document/blob size before deciding; if too large, store the blob in object storage and keep only the storage key in the DB record.
- Keep an in-process cache (`_cached_model`) so every `/classify` call doesn't hit the DB — only reload when the active version actually changes.

## 3. `GET /model/active`

```python
# app/api/routes/model_status.py
from fastapi import APIRouter, Depends
from app.api.dependencies import verify_internal_service
from app.ml.cnn.model_registry import get_active_model_metadata

router = APIRouter(prefix="/model", tags=["Model"])

@router.get("/active", dependencies=[Depends(verify_internal_service)])
async def model_active():
    meta = await get_active_model_metadata()  # version, metrics, createdAt — NOT the raw weights
    return meta
```

This is for visibility/debugging (Node's admin panel can show "currently active model: v3, F1: 0.91") — it does not return the weights themselves.

## 4. `POST /classify`

```python
# app/models/schemas.py
from pydantic import BaseModel
from typing import Literal

class ClassifyRequest(BaseModel):
    documentId: str
    text: str            # already-extracted text (from Node's PDF/OCR layer), not a file
    language: str | None = None  # optional hint, RETVec doesn't require it

class ClassifyResponse(BaseModel):
    label: Literal["safe", "suspicious", "injection"]
    confidence: float
    categories: list[str]   # e.g. ["Instruction Override", "Ranking Manipulation"]
```

```python
# app/api/routes/classify.py
from fastapi import APIRouter, Depends
from app.api.dependencies import verify_internal_service
from app.models.schemas import ClassifyRequest, ClassifyResponse
from app.ml.cnn.model_registry import load_active_model
from app.ml.preprocessing.normalize import basic_normalize

router = APIRouter(prefix="/classify", tags=["Classification"])

@router.post("", response_model=ClassifyResponse, dependencies=[Depends(verify_internal_service)])
async def classify(req: ClassifyRequest):
    model = await load_active_model()
    cleaned = basic_normalize(req.text)
    label, confidence, categories = model.predict(cleaned)
    return ClassifyResponse(label=label, confidence=confidence, categories=categories)
```

This must be synchronous and fast (RETVec+CNN is lightweight, no GPU needed) — Node calls this inline during the document upload flow and waits for the response.

## What NOT to build in this part

- No training logic yet (Part 2).
- No Node.js integration code yet (Part 3).
- No `/train` route yet — only the folder placeholder exists.

Confirm this part is working (service boots, `/model/active` and `/classify` respond, even against a manually-seeded dummy model) before moving to Part 2.
