"""
Tests for the /classify endpoint.

Uses a monkeypatched model registry so no real database is needed.
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.ml.cnn.model_registry import DummyModel


@pytest.fixture
def auth_headers():
    """Valid internal service auth headers."""
    return {"X-Internal-Token": "test-secret"}



@pytest.mark.asyncio
async def test_classify_returns_prediction(auth_headers):
    """POST /classify should return a valid ClassifyResponse."""
    dummy = DummyModel()

    with patch(
        "app.api.routes.classify.load_active_model",
        new_callable=AsyncMock,
        return_value=dummy,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/classify",
                json={
                    "documentId": "doc-123",
                    "text": "This is a normal document with standard content.",
                },
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["label"] in ("safe", "suspicious", "injection")
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["categories"], list)


@pytest.mark.asyncio
async def test_classify_rejects_missing_auth():
    """POST /classify without X-Internal-Token should return 401 or 422."""
    dummy = DummyModel()

    with patch(
        "app.api.routes.classify.load_active_model",
        new_callable=AsyncMock,
        return_value=dummy,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/classify",
                json={"documentId": "doc-123", "text": "test"},
            )

    # FastAPI returns 422 for missing required header
    assert response.status_code in (401, 422)


@pytest.mark.asyncio
async def test_classify_rejects_wrong_token():
    """POST /classify with wrong token should return 401."""
    dummy = DummyModel()

    with patch(
        "app.api.routes.classify.load_active_model",
        new_callable=AsyncMock,
        return_value=dummy,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/classify",
                json={"documentId": "doc-123", "text": "test"},
                headers={"X-Internal-Token": "wrong-secret"},
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_classify_normalizes_text(auth_headers):
    """Verify that text normalization is applied before prediction."""
    dummy = DummyModel()
    captured_texts = []

    def capturing_run_prediction(model, text):
        captured_texts.append(text)
        return ("safe", 0.99, [])

    with patch(
        "app.api.routes.classify.load_active_model",
        new_callable=AsyncMock,
        return_value=dummy,
    ), patch(
        "app.api.routes.classify.run_prediction",
        side_effect=capturing_run_prediction,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/classify",
                json={
                    "documentId": "doc-456",
                    "text": "  Hello   WORLD\n\ttest  ",
                },
                headers=auth_headers,
            )

    # basic_normalize: lowercase + collapse whitespace + strip
    assert captured_texts[0] == "hello world test"

