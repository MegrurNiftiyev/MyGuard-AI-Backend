# MyGuard AI ML Service — Node.js Integration Guide

This document provides complete technical specifications, schemas, authentication requirements, and code examples for the **Node.js Backend** to integrate with the **Python FastAPI ML Microservice** (`Ai-Models`).

---

## 🏛️ Architecture Overview

The ML Microservice serves as **Layer 2** in the MyGuard Document Security Gateway pipeline:
1. **Layer 1 (Node.js Backend):** Parses PDF/Word/Text files, extracts visible text, OCR text from images, and hidden/invisible text from file structures.
2. **Layer 2 (FastAPI ML Microservice — THIS SERVICE):** Fast, lightweight character-level **RETVec + CNN** deep learning classification predicting risk level (`safe`, `suspicious`, `injection`) and specific attack categories. **No LLM calls are made inside this service.**
3. **Layer 3 (External LLM — Handled by Node.js):** Invoked exclusively by the Node.js backend when Layer 2 returns `suspicious`.

---

## 🔒 Service-to-Service Authentication & Security Policy

All API endpoints (except `GET /health` and `GET /`) require internal service-to-service authentication.

### Required Header
```http
X-Internal-Token: <YOUR_INTERNAL_SERVICE_TOKEN>
```

> [!CAUTION]
> **IP Security Ban Policy:**
> If a client IP address submits an invalid or missing `X-Internal-Token` header **more than 3 times**, the client IP address will be **permanently banned** for that server session, returning `HTTP 403 Forbidden`. Ensure your Node.js backend always sends the correct token configured in `.env` (`INTERNAL_SERVICE_TOKEN`).

---

## 🚀 Key Integration Endpoints

**Vacib Qeyd:** Aşağıdakı endpointlərin hər biri (Health xaric) mütləq şəkildə Node.js tərəfindən **`X-Internal-Token`** header-i ilə çağırılmalıdır. Token göndərilmədikdə və ya səhv göndərildikdə, server avtomatik olaraq Node.js-i bloklayacaq. 

---

### 1. Document Text Classification — `POST /classify`

Sends extracted document text to the ML service for real-time risk assessment.

#### Endpoint Details
- **HTTP Method:** `POST`
- **Path:** `/classify`
- **Full URL (Production/Render):** `https://myguard-ai-backend.onrender.com/classify`
- **Headers Required:**
  - `Content-Type: application/json`
  - `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)

#### Request Payload Schema (`ClassifyRequest`)
```json
{
  "documentId": "doc-8f31b2e2",
  "text": "Standard document text extracted from the main body...",
  "ocrText": "Optional OCR text extracted from document images...",
  "hiddenText": "Optional hidden or white text extracted from document layers..."
}
```

#### Success Response Schema (200 OK)
```json
{
  "label": "injection",
  "confidence": 0.9854,
  "categories": [
    "Instruction Override",
    "Data Exfiltration"
  ]
}
```

#### Errors
- `422 Unprocessable Entity`: Body is missing required fields (`text`, `documentId`).
- `401 Unauthorized`: Missing or invalid `X-Internal-Token`.
- `403 Forbidden`: Node.js IP banned due to 3 failed token attempts.
- `503 Service Unavailable`: Model is not available (Firebase unreachable or no active model). Node.js backend should surface this as "analysis unavailable/pending".

---

### 2. Active Model Status — `GET /model/active`

Retrieves the currently active ML model's metadata (useful for Node.js Admin Panels).

#### Endpoint Details
- **HTTP Method:** `GET`
- **Path:** `/model/active`
- **Headers Required:**
  - `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)

#### Success Response (200 OK)
```json
{
  "version": "v12345678",
  "metrics": {
    "f1": 0.94,
    "precision": 0.96,
    "recall": 0.93
  },
  "createdAt": "2026-08-27T14:30:00+00:00",
  "status": "active"
}
```
#### Errors
- `401 Unauthorized`: Missing or invalid `X-Internal-Token`.
- `403 Forbidden`: IP banned.

---

### 3. Promote Candidate Model — `PATCH /model/{version}/promote`

Manually override the active model to a new specific candidate version.

#### Endpoint Details
- **HTTP Method:** `PATCH`
- **Path:** `/model/{version}/promote`
- **Headers Required:**
  - `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)

#### Success Response (200 OK)
```json
{
  "version": "v12345678",
  "metrics": { "f1": 0.94 },
  "status": "active"
}
```
#### Errors
- `400 Bad Request`: Model not found or already active.
- `401 / 403`: Auth errors.

---

### 4. Trigger Model Retraining — `POST /train`

Triggers an asynchronous background job to pull the latest labeled documents from **Supabase**, train a new model, and save it to **Firebase**. 
**Note:** Models are saved with `status: "candidate"` and are **NOT** automatically activated. You must explicitly call the Promote endpoint to make it active.

#### Endpoint Details
- **HTTP Method:** `POST`
- **Path:** `/train`
- **Headers Required:**
  - `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)

#### Success Response (200 OK)
```json
{
  "jobId": "7c9e3b1a-4d2f-4a8b-9e10-123456789abc",
  "status": "queued"
}
```
#### Errors
- `500 Internal Server Error`: Failed to create job in Firestore.
- `401 / 403`: Auth errors.

---

### 5. Check Training Job Status — `GET /train/status/{jobId}`

Polls the progress of a background training job.

#### Endpoint Details
- **HTTP Method:** `GET`
- **Path:** `/train/status/:jobId`
- **Headers Required:**
  - `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)

#### Success Response (Completed)
```json
{
  "jobId": "7c9e3b1a-4d2f-4a8b-9e10-123456789abc",
  "status": "completed",
  "createdAt": "2026-08-27T14:30:00.000Z",
  "startedAt": "2026-08-27T14:30:01.000Z",
  "finishedAt": "2026-08-27T14:32:15.000Z",
  "resultVersion": "v3b4a2f1",
  "metrics": {
    "f1": 0.945,
    "precision": 0.952,
    "recall": 0.938
  },
  "error": null
}
```
#### Errors
- `404 Not Found`: Job ID does not exist.
- `503 Service Unavailable`: Firestore is down.
- `401 / 403`: Auth errors.

---

### 6. Dataset Synchronization — `/api/v1/dataset/*`

Endpoints for inspecting and downloading dataset files from Supabase.

#### A. List Dataset Files
- **GET** `/api/v1/dataset/files?category=benign`
- **Headers Required:** `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)
- **Response:** Array of file metadata JSON objects.

#### B. Download File
- **GET** `/api/v1/dataset/file/{record_id}/download`
- **Headers Required:** `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)
- **Response:** Raw binary file.

#### C. Sync Dataset Locally
- **POST** `/api/v1/dataset/sync`
- **Headers Required:** `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (Mütləq göndərilməlidir)
- **Response:** JSON showing synced counts.
- **Errors for all:** `500` (Supabase unreachable), `401 / 403` (Auth errors).

---

### 7. Health Check Probe — `GET /health`

Public endpoint used by load balancers and Node.js for liveness probes.

#### Endpoint Details
- **HTTP Method:** `GET`
- **Path:** `/health`
- **Headers Required:** **NONE** (No token needed - heç bir header və token tələb olunmur, açıqdır).

#### Response (200 OK)
```json
{
  "status": "ok"
}
```

---

## ⚡ Render Cold-Start & Error Resilience

On Render (free tier), containers spin down after 15 minutes of inactivity. 
The ML service automatically caches downloaded Firebase models to local disk (`./data/cache/models/`). When the container wakes up:
1. It checks local disk cache first (0 ms load).
2. If absent, it fetches the active model from Firebase Storage & Firestore.
3. If Firebase is unreachable or no model is active, it will throw a `503 Service Unavailable` error instead of faking a response. Node.js should handle this `503` gracefully by showing an "analysis unavailable" or "pending" state on the frontend until the service is fully functional.
