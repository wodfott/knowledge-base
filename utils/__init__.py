"""Utility functions: text processing, SimHash, embedding client."""

import re
import hashlib
from typing import Optional


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    return text


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """Split text into overlapping chunks, splitting on sentence boundaries."""
    sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # Add overlap
    if overlap > 0 and len(chunks) > 1:
        overlapped = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
                chunk = prev_tail + " " + chunk
            overlapped.append(chunk)
        chunks = overlapped

    return chunks


def generate_doc_id(title: str, content: str, source_url: Optional[str] = None) -> str:
    """Generate a unique document ID using SHA256."""
    raw = f"{title}|{source_url or ''}|{content[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_entity_id(name: str, entity_type: str) -> str:
    """Generate a unique entity ID."""
    raw = f"{name}|{entity_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def generate_relation_id(source: str, target: str, rel_type: str) -> str:
    """Generate a unique relation ID."""
    raw = f"{source}|{rel_type}|{target}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def simhash_similarity(hash1: int, hash2: int) -> float:
    """Compute SimHash similarity (Hamming distance based)."""
    xor = hash1 ^ hash2
    distance = bin(xor).count("1")
    return 1.0 - (distance / 64)


def compute_simhash(text: str) -> int:
    """Compute a simple 64-bit SimHash for deduplication."""
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return 0

    vector = [0] * 64
    for token in tokens:
        token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(64):
            if token_hash & (1 << i):
                vector[i] += 1
            else:
                vector[i] -= 1

    result = 0
    for i in range(64):
        if vector[i] > 0:
            result |= (1 << i)
    return result
