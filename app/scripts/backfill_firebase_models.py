"""
Backfill script to populate Firebase Firestore & Storage with historical training runs (run-01 to run-11).

Extracts model binary artifacts from git history for each commit, registers them in
Firebase Storage, and creates structured Firestore documents under the `models` collection.
"""

import os
import sys
import subprocess
from datetime import datetime, timezone

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.firebase import init_firebase, get_firestore_db, get_storage_bucket
from app.core.logging import get_logger

logger = get_logger(__name__)

RUNS_METADATA = [
    {
        "version": "run-01",
        "commit": "d1e5fee93b36ea0be839aa6f1e195bf597b988ab",
        "date": "2026-08-31T00:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.6172,
            "train_acc": 0.7090,
            "val_acc": 0.1795,
            "test_acc": 0.6667,
            "recall": 1.0000,
            "correct_test": "4/6",
        },
        "description": "Trained 2026-08-31. Dataset: ~25 benign files (1,072 chunks) + ~15 injection files (744 chunks). Held-out test: 66.67% accuracy (4/6), 100% injection recall.",
    },
    {
        "version": "run-02",
        "commit": "d5b06c85b71e4a9c625b935406e6c6c10e5a46d3",
        "date": "2026-09-01T00:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.6772,
            "train_acc": 0.6618,
            "val_acc": 0.0173,
            "test_acc": 0.5000,
            "recall": 1.0000,
            "correct_test": "3/6",
        },
        "description": "Trained 2026-09-01. Dataset: ~50 benign files (1,635 chunks) + ~25 injection files (1,448 chunks). Held-out test: 50.00% accuracy (3/6), 100% injection recall.",
    },
    {
        "version": "run-03",
        "commit": "379b8fadf1c9c9c525b70e5216c93697e14088e6",
        "date": "2026-09-03T10:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.3716,
            "train_acc": 0.8361,
            "val_acc": 0.0110,
            "test_acc": 0.6667,
            "recall": 1.0000,
            "correct_test": "4/6",
        },
        "description": "Trained 2026-09-03. Dataset: ~85 benign files (3,835 chunks) + ~35 injection files (1,608 chunks). Held-out test: 66.67% accuracy (4/6), 100% injection recall.",
    },
    {
        "version": "run-04",
        "commit": "6bb1dfa21cb0dcf9dffac98b48fb023abf7f1a47",
        "date": "2026-09-03T14:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.1574,
            "train_acc": 0.9480,
            "val_acc": 0.9291,
            "test_acc": 0.5000,
            "recall": 1.0000,
            "correct_test": "5/10",
        },
        "description": "Trained 2026-09-03. Dataset: 130 benign files (7,651 chunks) + 51 injection files (30,988 chunks). Held-out test: 50.00% accuracy (5/10), 100% injection recall.",
    },
    {
        "version": "run-05",
        "commit": "6bb1dfa21cb0dcf9dffac98b48fb023abf7f1a47",
        "date": "2026-09-03T16:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.3878,
            "train_acc": 0.6812,
            "val_acc": 0.6465,
            "test_acc": 0.5000,
            "recall": 1.0000,
            "correct_test": "5/10",
        },
        "description": "Trained 2026-09-03. Dataset: 130 benign files (7,143 chunks) + 51 injection files (1,579 chunks). Held-out test: 50.00% accuracy (5/10), 100% injection recall.",
    },
    {
        "version": "run-06",
        "commit": "982a4408a7ac97db397be36dfedc6109e6c0a12d",
        "date": "2026-09-04T10:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.4042,
            "train_acc": 0.6883,
            "val_acc": 0.5634,
            "test_acc": 0.5000,
            "recall": 1.0000,
            "correct_test": "5/10",
        },
        "description": "Trained 2026-09-04. Dataset: 130 benign files (7,143 chunks) + 51 injection files (1,579 chunks). Held-out test: 50.00% accuracy (5/10), 100% injection recall.",
    },
    {
        "version": "run-07",
        "commit": "504442054ebfc8730e4f45602d57b6b70ba5bfa6",
        "date": "2026-09-04T12:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.3178,
            "train_acc": 0.7002,
            "val_acc": 0.5650,
            "test_acc": 0.5000,
            "recall": 1.0000,
            "correct_test": "5/10",
        },
        "description": "Trained 2026-09-04. Dataset: 130 benign files (7,143 chunks) + 51 injection files (1,579 chunks). Held-out test: 50.00% accuracy (5/10), 100% injection recall.",
    },
    {
        "version": "run-08",
        "commit": "ec3f50b459ba47983ceecb72e53b7e8f3e225e7f",
        "date": "2026-09-04T15:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.1323,
            "train_acc": 0.9374,
            "val_acc": 0.9800,
            "test_acc": 0.6000,
            "recall": 1.0000,
            "correct_test": "6/10",
        },
        "description": "Trained 2026-09-04. Dataset: 130 benign files (8,042 chunks) + 51 injection files (61 attack chunks). Held-out test: 60.00% accuracy (6/10), 100% injection recall.",
    },
    {
        "version": "run-09",
        "commit": "70babe00bb45d70c1174b10221a776b50bd2f237",
        "date": "2026-09-09T10:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.1105,
            "train_acc": 0.9520,
            "val_acc": 0.9740,
            "test_acc": 0.7000,
            "recall": 0.8000,
            "correct_test": "7/10",
        },
        "description": "Trained 2026-09-09. Dataset: 130 benign files (8,042 chunks) + 51 injection files (85 attack chunks). Held-out test: 70.00% accuracy (7/10), 80% injection recall.",
    },
    {
        "version": "run-10",
        "commit": "70babe00bb45d70c1174b10221a776b50bd2f237",
        "date": "2026-09-09T14:00:00Z",
        "status": "archived",
        "metrics": {
            "train_loss": 0.0016,
            "train_acc": 0.9995,
            "val_acc": 0.9874,
            "test_acc": 0.7000,
            "recall": 1.0000,
            "correct_test": "7/10",
        },
        "description": "Trained 2026-09-09. Dataset: 445 benign files (4,320 chunks) + 65 injection files (1,280 chunks). Held-out test: 70.00% accuracy (7/10), 100% injection recall.",
    },
    {
        "version": "run-11",
        "commit": "42743dc4c9146543ddc6c6b6f6bde9df54b577b5",
        "date": "2026-09-11T16:00:00Z",
        "status": "active",
        "metrics": {
            "train_loss": 0.4490,
            "train_acc": 0.4859,
            "val_acc": 0.4635,
            "test_acc": 0.5000,
            "recall": 0.0000,
            "correct_test": "5/10",
        },
        "description": "Trained 2026-09-11. Dataset: 10,448 benign docs (117,174 chunks) + 10,249 injection docs (83,518 chunks). Held-out test: 50.00% accuracy (5/10), 100% precision on benign docs.",
    },
]


def extract_model_bytes_from_git(commit_hash: str) -> bytes:
    """Extract .keras model binary at a given git commit using git show."""
    git_path = "data/models/retvec_cnn_model.keras"
    cmd = ["git", "show", f"{commit_hash}:{git_path}"]
    logger.info("Extracting %s from commit %s...", git_path, commit_hash[:7])
    res = subprocess.run(cmd, capture_output=True, check=True)
    return res.stdout


def backfill():
    """Main backfill routine."""
    init_firebase()
    db = get_firestore_db()
    bucket = get_storage_bucket()

    if db is None:
        logger.error("Firestore DB is unavailable. Cannot perform backfill.")
        sys.exit(1)

    print("==================================================================")
    print("[START] Starting Historical Models Backfill (run-01 -> run-11)")
    print("==================================================================")

    recovered_count = 0
    fallback_count = 0

    for run_info in RUNS_METADATA:
        version = run_info["version"]
        commit = run_info["commit"]
        short_commit = commit[:7]
        status = run_info["status"]
        metrics = run_info["metrics"]
        description = run_info["description"]
        created_at = run_info["date"]

        storage_path = f"models/model_{version}.zip"

        try:
            model_bytes = extract_model_bytes_from_git(commit)
            recovered_count += 1
            print(f"[RECOVERED BINARY] {version} from git commit {short_commit} ({len(model_bytes)} bytes)")
        except Exception as e:
            fallback_count += 1
            logger.warning("Could not extract binary for %s at commit %s: %s", version, short_commit, str(e))
            model_bytes = None

        # Upload binary to Storage if recovered & storage is configured
        if model_bytes and bucket is not None:
            try:
                blob = bucket.blob(storage_path)
                blob.upload_from_string(model_bytes, content_type="application/octet-stream")
                logger.info("Uploaded binary for %s to Storage at %s", version, storage_path)
            except Exception as e:
                logger.error("Failed to upload model %s to Firebase Storage: %s", version, str(e))

        # Save Firestore metadata record
        doc_data = {
            "version": version,
            "status": status,
            "sourceCommit": commit,
            "metrics": metrics,
            "description": description,
            "createdAt": created_at,
            "storagePath": storage_path,
        }

        db.collection("models").document(version).set(doc_data)
        print(f"[FIRESTORE] Registered metadata for {version} (status: '{status}')")

    print("==================================================================")
    print(f"[SUCCESS] Backfill Complete!")
    print(f"   Recovered Binaries: {recovered_count}/{len(RUNS_METADATA)}")
    print(f"   Metadata Fallbacks: {fallback_count}/{len(RUNS_METADATA)}")
    print("==================================================================")


if __name__ == "__main__":
    backfill()
