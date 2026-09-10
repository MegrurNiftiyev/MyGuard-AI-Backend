"""
Tests for Part 2 — training pipeline, endpoints, and utilities.

Uses mocked DB and model so no real database or TensorFlow training is needed.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.ml.cnn.model_registry import DummyModel
from app.ml.training.dataset import (
    encode_labels,
    stratified_split_with_test_ratio_override,
)
from app.ml.training.evaluate import decode_predictions


# ───────────────────────── Fixtures ─────────────────────────


@pytest.fixture
def auth_headers():
    """Valid internal service auth headers."""
    return {"X-Internal-Token": "test-secret"}


# ───────────────────── Encoding helpers ─────────────────────


class TestEncodeLabels:
    """Test one-hot label encoding."""

    def test_basic_encoding(self):
        labels = ["safe", "suspicious", "injection"]
        encoded = encode_labels(labels)
        assert encoded.shape == (3, 3)
        # safe=[1,0,0], suspicious=[0,1,0], injection=[0,0,1]
        np.testing.assert_array_equal(encoded[0], [1, 0, 0])
        np.testing.assert_array_equal(encoded[1], [0, 1, 0])
        np.testing.assert_array_equal(encoded[2], [0, 0, 1])

    def test_all_same_label(self):
        labels = ["safe", "safe", "safe"]
        encoded = encode_labels(labels)
        assert encoded.shape == (3, 3)
        for row in encoded:
            np.testing.assert_array_equal(row, [1, 0, 0])

    def test_unknown_label_defaults_safe(self):
        labels = ["unknown"]
        encoded = encode_labels(labels)
        np.testing.assert_array_equal(encoded[0], [1, 0, 0])


# ───────────────── Stratified split ─────────────────


class TestStratifiedSplit:
    """Test stratified_split_with_test_ratio_override."""

    def test_produces_disjoint_sets(self):
        labels = ["safe"] * 80 + ["injection"] * 20
        train_idx, test_idx = stratified_split_with_test_ratio_override(labels)
        assert set(train_idx).isdisjoint(set(test_idx))
        assert len(train_idx) + len(test_idx) == len(labels)

    def test_test_set_has_lower_positive_ratio(self):
        """Test set should have ~6% positives, not the training set's ~20%."""
        labels = ["safe"] * 800 + ["injection"] * 200
        train_idx, test_idx = stratified_split_with_test_ratio_override(
            labels, test_split=0.15, test_positive_ratio=0.06
        )

        test_labels = [labels[i] for i in test_idx]
        test_positive_count = sum(1 for l in test_labels if l == "injection")
        test_ratio = test_positive_count / len(test_labels) if test_labels else 0

        # Test ratio should be much lower than 20%
        assert test_ratio < 0.15, (
            f"Test positive ratio {test_ratio:.2%} is too high — "
            f"should be closer to 6%, not the training set's ~20%"
        )

    def test_handles_small_dataset(self):
        labels = ["safe"] * 5 + ["injection"] * 2
        train_idx, test_idx = stratified_split_with_test_ratio_override(labels)
        assert len(train_idx) + len(test_idx) == len(labels)

    def test_deterministic_with_seed(self):
        labels = ["safe"] * 80 + ["injection"] * 20
        split1 = stratified_split_with_test_ratio_override(labels, seed=42)
        split2 = stratified_split_with_test_ratio_override(labels, seed=42)
        assert split1[0] == split2[0]
        assert split1[1] == split2[1]


# ───────────────── Decode predictions ─────────────────


class TestDecodePredictions:
    """Test softmax → label string decoding."""

    def test_argmax_decoding(self):
        probs = np.array([
            [0.9, 0.05, 0.05],  # safe
            [0.1, 0.8, 0.1],    # suspicious
            [0.05, 0.1, 0.85],  # injection
        ])
        labels = decode_predictions(probs)
        assert labels == ["safe", "suspicious", "injection"]

    def test_tie_breaks_to_first(self):
        probs = np.array([[0.5, 0.5, 0.0]])
        labels = decode_predictions(probs)
        assert labels == ["safe"]  # argmax returns first occurrence


# ───────────────── Training endpoints ─────────────────


@pytest.mark.asyncio
async def test_start_training_returns_job_id(auth_headers):
    """POST /train should return a job ID and queued status."""
    mock_db = MagicMock()

    async def noop_training_job(job_id):
        pass  # don't actually run training in tests

    with patch("app.api.routes.train.get_firestore_db", return_value=mock_db), \
         patch("app.api.routes.train.run_training_job", side_effect=noop_training_job):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/train", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "jobId" in data
    assert data["status"] == "queued"


# ───────────────── Model promotion endpoint ─────────────────


@pytest.mark.asyncio
async def test_promote_model_success(auth_headers):
    """PATCH /model/{version}/promote should promote a candidate."""
    mock_result = {"version": "v123", "metrics": {"f1": 0.9}, "status": "active"}

    with patch(
        "app.api.routes.model_status.promote_model_version",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/model/v123/promote", headers=auth_headers
            )

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v123"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_promote_model_not_found(auth_headers):
    """PATCH /model/{version}/promote with unknown version should return 400."""
    with patch(
        "app.api.routes.model_status.promote_model_version",
        new_callable=AsyncMock,
        side_effect=ValueError("Model version 'vXXX' not found"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                "/model/vXXX/promote", headers=auth_headers
            )

    assert response.status_code == 400


# ───────────────── Classify still works with DummyModel ─────────────────


@pytest.mark.asyncio
async def test_classify_still_works_with_dummy(auth_headers):
    """POST /analyze-injection should still work with DummyModel via run_prediction."""
    dummy = DummyModel()

    with patch(
        "app.api.routes.classify.load_active_model",
        new_callable=AsyncMock,
        return_value=dummy,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/analyze-injection",
                json={"documentId": "doc-123", "fullText": "normal document containing enough words for test"},
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "safe"
    assert data["confidence"] == 0.95
