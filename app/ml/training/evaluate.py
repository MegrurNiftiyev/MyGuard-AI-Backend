"""
Model evaluation — precision, recall, F1 (macro), and classification report.

Uses the held-out test set with a realistic class distribution (~5-8%
injection) so metrics approximate real-world performance.
"""

import numpy as np
from sklearn.metrics import precision_recall_fscore_support, classification_report

from app.ml.cnn.architecture import LABEL_NAMES
from app.core.logging import get_logger

logger = get_logger(__name__)


def decode_predictions(label_probs: np.ndarray) -> list[str]:
    """Convert softmax probability arrays to label strings.

    Args:
        label_probs: Array of shape ``(N, 3)`` — softmax output from the
            ``label`` head of the model.

    Returns:
        List of label strings (``"safe"``, ``"suspicious"``, ``"injection"``).
    """
    indices = np.argmax(label_probs, axis=1)
    return [LABEL_NAMES[i] for i in indices]


def evaluate(model, test_texts: np.ndarray, test_labels_onehot: np.ndarray) -> dict:
    """Evaluate the model on the test set.

    Runs prediction, decodes labels, and computes macro-averaged
    precision, recall, and F1 plus a per-class classification report.

    Args:
        model: Trained Keras model with dual output heads.
        test_texts: Array of shape ``(N, 1)`` — raw text strings.
        test_labels_onehot: One-hot encoded true labels, shape ``(N, 3)``.

    Returns:
        Dict with ``precision``, ``recall``, ``f1``, and ``report`` keys.
    """
    # Run prediction — model returns [label_probs, category_probs]
    predictions = model.predict(test_texts, verbose=0)
    label_probs = predictions[0]  # shape (N, 3)

    # Decode predictions and true labels
    pred_labels = decode_predictions(label_probs)
    true_labels = decode_predictions(test_labels_onehot)

    # Macro-averaged metrics
    precision, recall, f1, _ = precision_recall_fscore_support(
        true_labels, pred_labels, average="macro", zero_division=0
    )

    # Per-class report
    # We dynamically determine labels to avoid ValueError if some classes are missing in test set
    unique_labels = sorted(list(set(true_labels + pred_labels)))
    report = classification_report(
        true_labels,
        pred_labels,
        labels=unique_labels,
        output_dict=True,
        zero_division=0,
    )

    metrics = {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "report": report,
    }

    logger.info(
        "Evaluation: precision=%.4f, recall=%.4f, F1=%.4f",
        precision,
        recall,
        f1,
    )

    return metrics
