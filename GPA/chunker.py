import re
from typing import List


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> List[str]:
    text = clean_text(text)

    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])

        if end == text_len:
            break

        start += (chunk_size - overlap)

    return chunks