"""
Shared text chunking logic for training and inference.
"""

def chunk_text(text: str, chunk_size: int = 60, overlap: int = 30) -> list[str]:
    """Chunk text into sliding word windows while preserving line breaks.

    Args:
        text: Raw document text input.
        chunk_size: Maximum words per chunk (default: 60).
        overlap: Word overlap between consecutive chunks (default: 30).

    Returns:
        List of text chunk strings.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    chunks = []
    for line in lines:
        words = line.split()
        if len(words) <= chunk_size:
            chunks.append(line)
        else:
            i = 0
            while i < len(words):
                c = " ".join(words[i:i + chunk_size])
                chunks.append(c)
                i += chunk_size - overlap
    return chunks
