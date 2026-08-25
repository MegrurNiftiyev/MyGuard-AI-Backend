# Part 2/3 — FastAPI ML Service: Training Pipeline & Background Jobs

## Context

Builds on Part 1's folder structure and model registry. This part implements: the RETVec+CNN model architecture, the dataset loader (reads labeled documents from DB), the training loop, evaluation, and the `/train` + `/train/status/{jobId}` endpoints. Training must run as a **background job**, never synchronously inside an HTTP request — it can take minutes and would otherwise block/timeout the caller.

**Important — do not add automatic/scheduled retraining in this part.** Training is triggered manually (an explicit `POST /train` call from an admin action in Node). No cron job, no "retrain every N new labels" auto-trigger — that decision is made later by a human, not by this code.

## 1. RETVec + CNN architecture

```python
# app/ml/cnn/architecture.py
import tensorflow as tf
from tensorflow.keras import layers, Model
from retvec.tf import RETVecTokenizer

def build_model(sequence_length: int = 128, num_categories: int = 6):
    inputs = layers.Input(shape=(1,), dtype=tf.string, name="text_input")
    x = RETVecTokenizer(sequence_length=sequence_length)(inputs)
    x = layers.Conv1D(128, 5, activation="relu")(x)
    x = layers.GlobalMaxPooling1D()(x)
    x = layers.Dense(64, activation="relu")(x)
    x = layers.Dropout(0.3)(x)

    label_output = layers.Dense(3, activation="softmax", name="label")(x)          # safe / suspicious / injection
    category_output = layers.Dense(num_categories, activation="sigmoid", name="categories")(x)  # multi-label

    model = Model(inputs=inputs, outputs=[label_output, category_output])
    model.compile(
        optimizer="adam",
        loss={"label": "categorical_crossentropy", "categories": "binary_crossentropy"},
        metrics={"label": ["accuracy"], "categories": ["binary_accuracy"]},
    )
    return model
```

Note: `label` is a 3-way classification (safe/suspicious/injection), `categories` is separate multi-label output (a document can match more than one category, e.g. both Instruction Override and Ranking Manipulation) — keep these as two output heads, don't collapse into one.

## 2. Dataset loader — respects the agreed class balance

Per the earlier data plan: ~1000 documents total, ~20-25% injection (with even split across categories and AZ/EN language), plus deliberate hard negatives among the "safe" set. This loader does not generate that data — it assumes the labeled documents already exist in DB (uploaded + labeled via the review flow, or bulk-imported) and just needs to split/load them correctly.

```python
# app/ml/training/dataset.py
from app.core.db import get_db
import numpy as np

async def load_labeled_dataset(test_split: float = 0.15):
    db = get_db()
    docs = await db.labeled_documents.find({}).to_list(length=None)

    texts = [d["text"] for d in docs]
    labels = [d["label"] for d in docs]           # "safe" | "suspicious" | "injection"
    categories = [d["categories"] for d in docs]   # list[str], multi-label

    # Held-out test set: keep it closer to real-world ratio (~5-8% injection),
    # not the training set's boosted ~20-25% — see earlier data-plan discussion.
    train_idx, test_idx = stratified_split_with_test_ratio_override(
        labels, test_split=test_split, test_positive_ratio=0.06
    )

    return (
        [texts[i] for i in train_idx], [labels[i] for i in train_idx], [categories[i] for i in train_idx],
        [texts[i] for i in test_idx], [labels[i] for i in test_idx], [categories[i] for i in test_idx],
    )
```

`stratified_split_with_test_ratio_override` is a helper you write: it must guarantee the test set's positive ratio is close to real-world (~5-8%) even though the full dataset's ratio is ~20-25% — this means the split is not a simple random shuffle; oversample "safe" documents into the test set relative to their training-set proportion. Implement this explicitly, don't skip it — a test set with the same inflated ratio as training will give a misleadingly optimistic picture of real-world performance.

## 3. Class weighting (required, per earlier discussion)

```python
# app/ml/training/train.py
from sklearn.utils.class_weight import compute_class_weight

def get_class_weights(labels: list[str]) -> dict:
    classes = np.unique(labels)
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=labels)
    return dict(zip(classes, weights))
```

Pass this into `model.fit(..., class_weight=...)` for the `label` output. Do not train without this — with ~20-25% positives the model will otherwise bias toward predicting "safe".

## 4. Evaluation — precision/recall/F1, not accuracy

```python
# app/ml/training/evaluate.py
from sklearn.metrics import precision_recall_fscore_support, classification_report

def evaluate(model, test_texts, test_labels):
    preds = model.predict(test_texts)
    pred_labels = decode_predictions(preds)  # softmax -> label string
    precision, recall, f1, _ = precision_recall_fscore_support(
        test_labels, pred_labels, average="macro"
    )
    report = classification_report(test_labels, pred_labels, output_dict=True)
    return {"precision": precision, "recall": recall, "f1": f1, "report": report}
```

The training job must record this in the model's metadata (see `save_model_version` in Part 1) — every model version stored in DB carries its own metrics, so later versions can be compared before promoting one to "active".

## 5. Background job — training runner + status tracking

Use FastAPI's `BackgroundTasks` for simplicity (no need for Celery/Redis unless the team already has that infra — check first before adding a new dependency). Track job status in DB, not in memory, since the service may restart mid-job (in which case the job should be marked failed/stale, not silently lost).

```python
# app/jobs/training_job.py
from app.core.db import get_db
from app.ml.cnn.architecture import build_model
from app.ml.training.dataset import load_labeled_dataset
from app.ml.training.evaluate import evaluate
from app.ml.cnn.model_registry import save_model_version
from datetime import datetime
import uuid

async def run_training_job(job_id: str):
    db = get_db()
    await db.training_jobs.update_one({"_id": job_id}, {"$set": {"status": "running", "startedAt": datetime.utcnow()}})

    try:
        train_x, train_y, train_cat, test_x, test_y, test_cat = await load_labeled_dataset()
        class_weights = get_class_weights(train_y)

        model = build_model()
        model.fit(train_x, {"label": encode(train_y), "categories": encode_multi(train_cat)},
                  class_weight={"label": class_weights}, epochs=10, validation_split=0.1)

        metrics = evaluate(model, test_x, test_y)
        version = f"v{uuid.uuid4().hex[:8]}"
        await save_model_version(model, metrics, version)

        await db.training_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "completed", "finishedAt": datetime.utcnow(), "resultVersion": version, "metrics": metrics}},
        )
    except Exception as e:
        await db.training_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "finishedAt": datetime.utcnow(), "error": str(e)}},
        )
```

## 6. `POST /train` and `GET /train/status/{jobId}`

```python
# app/api/routes/train.py
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from app.api.dependencies import verify_internal_service
from app.core.db import get_db
from app.jobs.training_job import run_training_job
from datetime import datetime
import uuid

router = APIRouter(prefix="/train", tags=["Training"])

@router.post("", dependencies=[Depends(verify_internal_service)])
async def start_training(background_tasks: BackgroundTasks):
    db = get_db()
    job_id = str(uuid.uuid4())
    await db.training_jobs.insert_one({"_id": job_id, "status": "queued", "createdAt": datetime.utcnow()})
    background_tasks.add_task(run_training_job, job_id)
    return {"jobId": job_id, "status": "queued"}

@router.get("/status/{job_id}", dependencies=[Depends(verify_internal_service)])
async def training_status(job_id: str):
    db = get_db()
    job = await db.training_jobs.find_one({"_id": job_id})
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
```

## Important: no automatic promotion to "active"

`save_model_version` in Part 1 stores new models with `status: "candidate"`, never `"active"`. This part does **not** implement auto-promotion — a newly trained model, even with better metrics, does not automatically replace the currently active one. Promotion is a separate explicit action (add a small `PATCH /model/{version}/promote` endpoint if you want it in this part, gated behind the same internal-service auth) — this keeps a human in the loop before a new model goes live, since metrics on a small held-out set can be misleading.

## What NOT to build in this part

- No scheduled/automatic retraining trigger.
- No Node.js-side code yet (Part 3).
