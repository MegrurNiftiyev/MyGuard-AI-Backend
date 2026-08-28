# Python FastAPI ML Service — Full Current-State Audit (No Code Changes)

## Purpose

Report the exact current state of the FastAPI ML microservice (MyGuard `Ai-Models` / `ml-service`). **Do not write, edit, or refactor any code.** Only read and report, based strictly on what's actually in the code — not on what any doc claims.

## Report format — answer every section

### 1. Project structure
Folder tree with a one-line note per top-level folder/file. Confirm whether it roughly matches this planned structure (note deviations, don't force it to match):
```
app/main.py, app/core/(config,db,logging), app/models/schemas,
app/ml/(retvec, cnn, preprocessing, training), app/api/routes/*, app/jobs/*
```

### 2. Every implemented endpoint
For each route: method + path, handler file, request schema (actual Pydantic model, not assumed), response schema, what internal function it calls. Explicitly check for:
- `POST /classify` — does it exist? What request body does it actually expect (`documentId`, `text`, `ocrText`, `hiddenText`, `language` — confirm exact field names used in code)? What does it actually return (`label`, `confidence`, `categories` — confirm exact shape)?
- `GET /model/active` — exists?
- `POST /train`, `GET /train/status/{jobId}` — exist, or is training still entirely unbuilt?
- `PATCH /model/{version}/promote` — exists?
- Any other route not in this list — report it.

### 3. What actually powers `/classify` right now
This is the most important section. Determine precisely:
- Is there a real trained model being loaded, or is the response currently hardcoded/rule-based/random?
- If a model exists: what architecture (confirm RETVec+CNN as planned, or something else — check `app/ml/cnn/architecture.py` or wherever the model is actually defined)?
- Where are the model weights actually stored and loaded from — local disk file, DB, object storage, or baked into the Docker image? (Prior plan was DB-backed, stateless — confirm whether that was actually implemented or if it's still loading from a local file, which would violate the stateless requirement.)
- Is there a fallback if no model/weights are found (crashes, returns an error, or silently returns a fixed dummy response)?

### 4. Training pipeline — built or not
- Is there any labeled dataset loader reading from a DB? Which collection/table does it read from, and does that collection actually have any data in it yet?
- Is class weighting / imbalance handling actually implemented, or just planned?
- Is the held-out test set logic (with a different, more realistic positive ratio than the training set) actually implemented?
- Is training synchronous or does it run as a background job (`BackgroundTasks`, Celery, or something else)? If background, how is job status tracked (DB record, in-memory dict, something else — flag if in-memory, since that breaks on restart)?
- Does a completed training run actually produce a new stored model version, or does it just log metrics without persisting anything usable?

### 5. Auth / service-to-service security
- Is there an internal-token check on any endpoint? Show the actual dependency/middleware code.
- What is the exact env var name used for this token in code (confirm it matches what Node expects)?
- Is any endpoint currently reachable without this check (an oversight, or intentionally public like a health check)?
- Is the service bound in a way that would work with a private-network-only deployment (i.e. does it just listen on a port with no public-specific config), or does anything in the code assume a public URL?

### 6. Database
- What DB client/driver does this service actually use to talk to the same database as the Node backend (confirm it's the same Firestore instance, or a different one)?
- How is the connection configured (service account, connection string, env vars — list them)?
- Confirm whether this service can currently read the `documents`/`labeled_documents`-equivalent collections at all, or if that integration doesn't exist yet.

### 7. Dependencies
From `requirements.txt` (or `pyproject.toml`): confirm presence of `fastapi`, `retvec`, `tensorflow` (or alternative ML framework actually used), `scikit-learn`, DB client library, any HTTP client. Flag anything unexpected or missing relative to the plan.

### 8. Error handling & resilience
- What happens if `/classify` is called with empty/malformed text?
- What happens if the DB is unreachable when loading the active model?
- Are there any try/except blocks that silently swallow errors (log-and-continue) versus ones that properly surface failures?

### 9. Deployment
- Is there a `Dockerfile`? Does it match how the service is actually meant to run (correct entrypoint, port exposed)?
- Any Render-specific config file (`render.yaml` or dashboard-only config — note if you can't determine this from code alone)?
- Confirm current deployment target from any config/env references (local only, or an actual deployed URL referenced somewhere).

### 10. Your own assessment — gaps, bugs, inconsistencies
Plain bullet list. In particular: is this service currently capable of returning a real (non-mock) classification at all, end to end? If not, what's the single biggest missing piece blocking that?

## What NOT to do
Do not modify files. Do not fix anything. Do not guess — say "not implemented" or "could not confirm" rather than assuming.
