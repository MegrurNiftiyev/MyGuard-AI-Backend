"""
Dataset loader — reads labeled documents from MongoDB and produces
train/test splits with a realistic test-set class distribution.

The training set uses the inflated ~20-25% injection ratio (per the data plan)
to give the model enough positive examples. The held-out test set is rebalanced
to approximate real-world traffic (~5-8% injection) so evaluation metrics
reflect actual deployment performance.
"""

import math
import random
from collections import defaultdict

import numpy as np

from app.core.db import get_db
from app.core.logging import get_logger
from app.ml.cnn.architecture import LABEL_NAMES, CATEGORY_NAMES

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------
def encode_labels(labels: list[str]) -> np.ndarray:
    """One-hot encode label strings into a (N, 3) numpy array.

    Label order follows ``LABEL_NAMES``: safe=0, suspicious=1, injection=2.
    """
    label_to_idx = {name: i for i, name in enumerate(LABEL_NAMES)}
    n = len(labels)
    encoded = np.zeros((n, len(LABEL_NAMES)), dtype=np.float32)
    for i, lab in enumerate(labels):
        idx = label_to_idx.get(lab)
        if idx is not None:
            encoded[i, idx] = 1.0
        else:
            logger.warning("Unknown label '%s' at index %d — defaulting to safe", lab, i)
            encoded[i, 0] = 1.0  # default to safe
    return encoded


def encode_categories(categories_list: list[list[str]], num_categories: int | None = None) -> np.ndarray:
    """Multi-hot encode category lists into a (N, num_categories) numpy array.

    Category order follows ``CATEGORY_NAMES``.
    """
    if num_categories is None:
        num_categories = len(CATEGORY_NAMES)

    cat_to_idx = {name: i for i, name in enumerate(CATEGORY_NAMES)}
    n = len(categories_list)
    encoded = np.zeros((n, num_categories), dtype=np.float32)
    for i, cats in enumerate(categories_list):
        for cat in cats:
            idx = cat_to_idx.get(cat)
            if idx is not None:
                encoded[i, idx] = 1.0
    return encoded


# ---------------------------------------------------------------------------
# Stratified split with test-set ratio override
# ---------------------------------------------------------------------------
def stratified_split_with_test_ratio_override(
    labels: list[str],
    test_split: float = 0.15,
    test_positive_ratio: float = 0.06,
    seed: int = 42,
) -> tuple[list[int], list[int]]:
    """Split indices into train/test with a controlled test-set positive ratio.

    The training set keeps whatever class ratio the full dataset has (~20-25%
    injection per the data plan). The test set is rebalanced so that positives
    (``"injection"`` + ``"suspicious"``) make up approximately
    ``test_positive_ratio`` of the test set — closer to real-world traffic.

    This prevents misleadingly optimistic metrics from an inflated test set.

    Args:
        labels: List of label strings for each document.
        test_split: Fraction of total data to allocate to the test set.
        test_positive_ratio: Desired fraction of positives in the test set.
        seed: Random seed for reproducibility.

    Returns:
        ``(train_indices, test_indices)`` — lists of integer indices.
    """
    rng = random.Random(seed)

    # Group indices by label
    groups: dict[str, list[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        groups[lab].append(i)

    # Shuffle within each group
    for indices in groups.values():
        rng.shuffle(indices)

    total = len(labels)
    test_size = max(1, int(total * test_split))

    # "Positive" = injection + suspicious; "Negative" = safe
    positive_keys = [k for k in groups if k in ("injection", "suspicious")]
    negative_keys = [k for k in groups if k not in ("injection", "suspicious")]

    all_positive = []
    for k in positive_keys:
        all_positive.extend(groups[k])
    all_negative = []
    for k in negative_keys:
        all_negative.extend(groups[k])

    rng.shuffle(all_positive)
    rng.shuffle(all_negative)

    # Compute how many positives/negatives go into the test set
    n_test_positive = max(1, int(test_size * test_positive_ratio))
    n_test_negative = test_size - n_test_positive

    # Clamp to available data
    n_test_positive = min(n_test_positive, len(all_positive))
    n_test_negative = min(n_test_negative, len(all_negative))

    test_indices = all_positive[:n_test_positive] + all_negative[:n_test_negative]
    train_indices = all_positive[n_test_positive:] + all_negative[n_test_negative:]

    rng.shuffle(test_indices)
    rng.shuffle(train_indices)

    actual_ratio = n_test_positive / max(1, len(test_indices))
    logger.info(
        "Split: %d train, %d test (test positive ratio: %.2f%%)",
        len(train_indices),
        len(test_indices),
        actual_ratio * 100,
    )

    return train_indices, test_indices


# ---------------------------------------------------------------------------
# Main dataset loader
# ---------------------------------------------------------------------------
async def load_labeled_dataset(
    test_split: float = 0.15,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load labeled documents from MongoDB and return train/test arrays.

    Returns:
        ``(train_texts, train_labels, train_categories,
          test_texts, test_labels, test_categories)``

        - ``*_texts``: numpy string arrays, shape ``(N, 1)``
        - ``*_labels``: one-hot numpy arrays, shape ``(N, 3)``
        - ``*_categories``: multi-hot numpy arrays, shape ``(N, num_categories)``
    """
    db = get_db()
    docs = await db.labeled_documents.find({}).to_list(length=None)

    if not docs:
        raise RuntimeError(
            "No labeled documents found in db.labeled_documents. "
            "Upload and label documents first."
        )

    texts = [d["text"] for d in docs]
    labels = [d["label"] for d in docs]
    categories = [d.get("categories", []) for d in docs]

    logger.info("Loaded %d labeled documents from database", len(docs))

    # Stratified split with realistic test-set ratio
    train_idx, test_idx = stratified_split_with_test_ratio_override(
        labels, test_split=test_split, test_positive_ratio=0.06
    )

    # Build arrays
    train_texts = np.array([[texts[i]] for i in train_idx])
    test_texts = np.array([[texts[i]] for i in test_idx])

    train_labels_enc = encode_labels([labels[i] for i in train_idx])
    test_labels_enc = encode_labels([labels[i] for i in test_idx])

    train_categories_enc = encode_categories([categories[i] for i in train_idx])
    test_categories_enc = encode_categories([categories[i] for i in test_idx])

    return (
        train_texts,
        train_labels_enc,
        train_categories_enc,
        test_texts,
        test_labels_enc,
        test_categories_enc,
    )
