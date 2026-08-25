"""
Training utilities — class weighting and label encoding helpers.

Class weighting is critical: with ~20-25% positives in the training set,
the model will bias toward predicting ``"safe"`` without it.
"""

import numpy as np
from sklearn.utils.class_weight import compute_class_weight

from app.ml.cnn.architecture import LABEL_NAMES
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_class_weights(labels_onehot: np.ndarray) -> dict[int, float]:
    """Compute balanced class weights from one-hot encoded labels.

    Uses ``sklearn.utils.class_weight.compute_class_weight`` with
    ``class_weight="balanced"`` to inversely weight classes by frequency.

    Args:
        labels_onehot: One-hot encoded labels, shape ``(N, 3)``.

    Returns:
        Dict mapping class index → weight, suitable for
        ``model.fit(..., class_weight={"label": weights})``.
    """
    # Convert one-hot back to integer labels for sklearn
    y_int = np.argmax(labels_onehot, axis=1)
    classes = np.arange(len(LABEL_NAMES))

    weights = compute_class_weight(
        class_weight="balanced", classes=classes, y=y_int
    )
    weight_dict = {int(cls): float(w) for cls, w in zip(classes, weights)}

    logger.info(
        "Class weights: %s",
        {LABEL_NAMES[k]: f"{v:.3f}" for k, v in weight_dict.items()},
    )
    return weight_dict
