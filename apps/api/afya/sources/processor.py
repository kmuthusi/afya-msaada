"""Page-preserving PDF extraction with reference filtering and sentence-aware chunks."""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


def reference_page(raw: str) -> bool:
    head = raw[:600]
    if re.search(r"(?im)^\s*(?:\d+[. ]*)?references\s*$", head):
        return True
    lower = head.casefold()
    return "accompanying who documents" in lower or "other who documents" in lower


def chunks(text: str, *, max_chars: int = 1400, overlap_chars: int = 160) -> list[str]:
    clean = re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()
    if len(clean) < 80:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", clean)
    output = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                output.append(current.strip())
                current = ""
            for start in range(0, len(sentence), max_chars - overlap_chars):
                part = sentence[start:start + max_chars].strip()
                if len(part) >= 80:
                    output.append(part)
            continue
        if current and len(current) + len(sentence) + 1 > max_chars:
            output.append(current.strip())
            current = current[-overlap_chars:] + " " + sentence
        else:
            current = f"{current} {sentence}".strip()
    if len(current) >= 80:
        output.append(current.strip())
    return output


def extract(path: Path):
    for page, obj in enumerate(PdfReader(path).pages, 1):
        raw = obj.extract_text() or ""
        if reference_page(raw):
            continue
        for text in chunks(raw):
            yield page, text
