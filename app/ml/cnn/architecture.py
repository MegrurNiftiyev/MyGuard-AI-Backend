"""
RETVec + CNN classification model architecture.

Dual-output model:
  - ``label``: 3-class softmax (safe / suspicious / injection)
  - ``categories``: multi-label sigmoid (e.g. Instruction Override, Ranking Manipulation)

The RETVec tokenizer layer handles character-level embedding directly from
raw text strings — no separate preprocessing step required.
"""

import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"
import tensorflow as tf
try:
    import tf_keras as keras
    from tf_keras import layers, Model
except ImportError:
    from tensorflow.keras import layers, Model
from retvec.tf import RETVecTokenizer


LABEL_NAMES = ["safe", "suspicious", "injection"]


def build_model(sequence_length: int = 128) -> Model:
    """Build and compile the RETVec+CNN classification model.

    Architecture:
        Input (raw text string)
        → RETVecTokenizer (character-level embeddings, ``sequence_length`` tokens)
        → Conv1D(128, kernel_size=5, relu)
        → GlobalMaxPooling1D
        → Dense(64, relu) → Dropout(0.3)
        → Output head:
            - ``label``: Dense(3, softmax) — safe / suspicious / injection

    Args:
        sequence_length: Number of tokens for RETVec (default 128).

    Returns:
        Compiled Keras ``Model``.
    """
    inputs = layers.Input(shape=(1,), dtype=tf.string, name="text_input")

    # RETVec tokenizer layer — converts raw text to character-level embeddings
    x = RETVecTokenizer(sequence_length=sequence_length)(inputs)

    # 1-D convolution over the token sequence
    x = layers.Conv1D(128, 5, activation="relu")(x)
    x = layers.GlobalMaxPooling1D()(x)

    # Shared dense trunk
    x = layers.Dense(64, activation="relu")(x)
    x = layers.Dropout(0.3)(x)

    # Output head: risk label (3-way classification)
    label_output = layers.Dense(3, activation="softmax", name="label")(x)

    model = Model(inputs=inputs, outputs=label_output)
    model.compile(
        optimizer="adam",
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model
