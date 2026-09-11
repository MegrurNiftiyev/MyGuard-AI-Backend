"""
Tests for the model registry module.
"""

import pytest
from app.ml.serving.registry import (
    DummyModel,
    serialize_model,
    deserialize_model,
)


class TestDummyModel:
    """Verify the DummyModel stub works as expected."""

    def test_predict_returns_tuple(self):
        model = DummyModel()
        result = model.predict("some text")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_predict_label(self):
        model = DummyModel()
        label, confidence = model.predict("anything")
        assert label == "safe"
        assert isinstance(confidence, float)


class TestSerialization:
    """Verify model serialize/deserialize round-trips correctly."""

    def test_round_trip(self):
        original = DummyModel()
        blob = serialize_model(original)
        assert isinstance(blob, bytes)

        restored = deserialize_model(blob)
        assert isinstance(restored, DummyModel)

        # Verify the restored model still works
        label, confidence = restored.predict("test")
        assert label == "safe"
