"""
RETVec tokenizer wrapper.

Thin convenience layer around ``retvec.tf.RETVecTokenizer``.
The tokenizer is embedded directly in the Keras model graph (see
``architecture.py``), so this module provides standalone utilities
for any out-of-graph usage.
"""

from retvec.tf import RETVecTokenizer as _RETVecTokenizer


def get_tokenizer(sequence_length: int = 128) -> _RETVecTokenizer:
    """Return a configured RETVec tokenizer instance.

    Args:
        sequence_length: Number of tokens to produce per input string.

    Returns:
        A ``RETVecTokenizer`` Keras layer.
    """
    return _RETVecTokenizer(sequence_length=sequence_length)
