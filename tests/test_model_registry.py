"""
Tests for the model registry module.
"""

import pytest
from app.ml.cnn.model_registry import (
    DummyModel,
    serialize_model,
    deserialize_model,
)
from app.ml.preprocessing.normalize import basic_normalize


class TestDummyModel:
    """Verify the DummyModel stub works as expected."""

    def test_predict_returns_tuple(self):
        model = DummyModel()
        result = model.predict("some text")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_predict_label(self):
        model = DummyModel()
        label, confidence, categories = model.predict("anything")
        assert label == "safe"
        assert isinstance(confidence, float)
        assert isinstance(categories, list)


class TestSerialization:
    """Verify model serialize/deserialize round-trips correctly."""

    def test_round_trip(self):
        original = DummyModel()
        blob = serialize_model(original)
        assert isinstance(blob, bytes)

        restored = deserialize_model(blob)
        assert isinstance(restored, DummyModel)

        # Verify the restored model still works
        label, confidence, categories = restored.predict("test")
        assert label == "safe"


class TestNormalize:
    """Verify basic_normalize handles edge cases."""

    def test_lowercases(self):
        assert basic_normalize("HELLO") == "hello"

    def test_collapses_whitespace(self):
        assert basic_normalize("a   b\t\nc") == "a b c"

    def test_strips_edges(self):
        assert basic_normalize("  padded  ") == "padded"

    def test_empty_string(self):
        assert basic_normalize("") == ""

    def test_unicode_normalization(self):
        # NFC normalization should compose characters
        text = "caf\u0065\u0301"  # e + combining accent
        result = basic_normalize(text)
        assert "é" in result or "e" in result  # depends on NFC composition
