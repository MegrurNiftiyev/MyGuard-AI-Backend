# Part 3/3 — Node.js Integration with the FastAPI ML Service

## Context

Builds on Parts 1-2 (FastAPI service is running with `/classify`, `/model/active`, `/train`, `/train/status/{jobId}`). This part wires the existing Node.js backend (see its Swagger doc: MyGuard AI Document Security Gateway API) to call this service at the right points, without changing its public API contract.

## Where FastAPI gets called from Node — mapping to existing endpoints

Do not create new public endpoints for this — plug into the ones that already exist.

### 1. `POST /api/documents/upload` (and its alias `POST /api/analyze`)

Current flow (per the existing pipeline): Node extracts PDF text + runs OCR (Layer 1, already implemented per the earlier real-Layer-1 prompt) → now add: Node calls FastAPI's `POST /classify` with the extracted text → stores the result as Layer 2 of the document's pipeline record → if `label == "suspicious"` (i.e. classifier isn't confident either way), Node proceeds to call the external LLM (Layer 3, already planned separately) for a final read; if `label` is a confident `"safe"` or `"injection"`, Layer 3 is skipped.

```ts
// services/mlService.ts
import fetch from 'node-fetch';

const ML_SERVICE_URL = process.env.ML_SERVICE_URL; // e.g. http://ml-service:8000
const INTERNAL_TOKEN = process.env.ML_SERVICE_INTERNAL_TOKEN;

interface ClassifyResult {
  label: 'safe' | 'suspicious' | 'injection';
  confidence: number;
  categories: string[];
}

export async function classifyDocument(documentId: string, text: string): Promise<ClassifyResult> {
  const res = await fetch(`${ML_SERVICE_URL}/classify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-internal-token': INTERNAL_TOKEN!,
    },
    body: JSON.stringify({ documentId, text }),
  });
  if (!res.ok) {
    throw new Error(`ML service classify failed: ${res.status}`);
  }
  return res.json();
}
```

Call this from the existing document upload handler, right after the Layer 1 (OCR/text) step completes, before deciding whether Layer 3 runs.

### 2. `GET /api/documents/{id}/pipeline`

This endpoint already returns Layer 1/2/3 inspection data per its description. Layer 2's portion of the response should now be the real result stored during upload (from step 1 above) — not mock data. No new call to FastAPI is needed here at read time; this just reads what was already stored in Node's own DB when the document was analyzed.

### 3. `GET /api/admin/models` and `POST /api/admin/models`

These are Node's own model **registry** (separate purpose from FastAPI's `/model/active` — see the earlier scope discussion: this is the record of "which model versions exist and their status", FastAPI's `/model/active` is "what's currently loaded at runtime"). Keep both. Wire them together as follows:

- After a training job completes in FastAPI (`GET /train/status/{jobId}` returns `status: "completed"`), Node should read that job's `resultVersion` and `metrics`, then call its own existing `POST /api/admin/models` to register the new candidate version in its registry (so admins can see it in the existing admin UI without needing to look at FastAPI directly).
- Add a new admin action (small addition, not a new public endpoint category) that lets an admin explicitly promote a candidate to active — this should call the `PATCH /model/{version}/promote` route on FastAPI (from Part 2) and then update the record's status in Node's own registry to match.

```ts
// services/mlService.ts (continued)
export async function getTrainingStatus(jobId: string) {
  const res = await fetch(`${ML_SERVICE_URL}/train/status/${jobId}`, {
    headers: { 'x-internal-token': INTERNAL_TOKEN! },
  });
  return res.json();
}

export async function startTraining(): Promise<{ jobId: string }> {
  const res = await fetch(`${ML_SERVICE_URL}/train`, {
    method: 'POST',
    headers: { 'x-internal-token': INTERNAL_TOKEN! },
  });
  return res.json();
}

export async function promoteModel(version: string) {
  const res = await fetch(`${ML_SERVICE_URL}/model/${version}/promote`, {
    method: 'PATCH',
    headers: { 'x-internal-token': INTERNAL_TOKEN! },
  });
  return res.json();
}
```

### 4. Where the "start training" trigger lives

Per the earlier decision, training is **manually triggered**, not automatic. Add this as an admin-only action — either a small addition under the existing Admin & Registry section (e.g. an internal button in the admin panel that calls `startTraining()` above) or, if the Swagger doc should reflect it explicitly, add one new documented endpoint:

```
POST /api/admin/models/train   → calls startTraining(), returns { jobId }
GET  /api/admin/models/train/{jobId}  → calls getTrainingStatus(jobId)
```

Do not wire this to run automatically on any schedule or on every new label — it stays a deliberate admin action, exactly as agreed.

## Error handling and resilience

- If the FastAPI service is unreachable during `POST /api/documents/upload`, the document upload should **not** silently mark the document as "safe" — return a clear `status: "analysis_pending"` or similar and either retry or surface the failure, since silently skipping Layer 2 defeats the purpose of the pipeline.
- Wrap the `classifyDocument` call with a reasonable timeout (a few seconds — this model is lightweight, if it's taking long something is wrong) and a single retry before treating it as a failure.

## Environment variables to add (Node side)

```
ML_SERVICE_URL=http://localhost:8000
ML_SERVICE_INTERNAL_TOKEN=<shared secret, matches FastAPI's INTERNAL_SERVICE_TOKEN>
```

## What NOT to build in this part

- No changes to the public API contract documented in the existing Swagger — only internal service-to-service calls and one small addition (the admin train-trigger endpoints) if the team wants them documented.
- No automatic retraining scheduling.
