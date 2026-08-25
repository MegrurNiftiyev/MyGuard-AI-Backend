"""
Basic text normalization before tokenization.

This is NOT a substitute for RETVec's character-level processing — it just
handles trivial cleanup (extra whitespace, case folding) so the model sees
slightly cleaner input.
"""

import re
import unicodedata


def basic_normalize(text: str) -> str:
    """Normalize text for classification input.

    Steps:
      1. Unicode NFC normalization
      2. Lowercase
      3. Collapse consecutive whitespace into a single space
      4. Strip leading/trailing whitespace
    """
    # Unicode normalization (composed form)
    text = unicodedata.normalize("NFC", text)

    # Lowercase
    text = text.lower()

    # Collapse whitespace (newlines, tabs, multiple spaces → single space)
    text = re.sub(r"\s+", " ", text)

    # Strip edges
    text = text.strip()

    return text
