"""
Model prediction adapter — runs chunk-based inference on raw input text.
"""

import numpy as np

from app.ml.cnn.architecture import LABEL_NAMES
from app.ml.preprocessing.chunking import chunk_text
from app.ml.serving.registry import DummyModel


def run_prediction(model, text: str) -> tuple[str, float]:
    """Run chunk-based prediction on full text and return (label, confidence)."""
    if isinstance(model, DummyModel):
        return model.predict(text)

    chunks = chunk_text(text)
    if not chunks:
        return ("safe", 0.0)

    chunk_inputs = np.array([[c] for c in chunks])
    predictions = model.predict(chunk_inputs, verbose=0)

    # Predictions array has shape (N, 3): [safe, suspicious, injection]
    label_probs = predictions if isinstance(predictions, np.ndarray) and predictions.ndim == 2 else predictions[0]

    label_idx = label_probs.argmax(axis=1)  # argmax per chunk
    worst_chunk_idx = int(label_probs[:, 2].argmax())  # chunk with highest injection probability

    final_label_idx = 2 if 2 in label_idx else (1 if 1 in label_idx else 0)
    label = LABEL_NAMES[final_label_idx]

    confidence = float(label_probs[worst_chunk_idx, final_label_idx])

    return (label, confidence)
