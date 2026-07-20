"""Simple in-memory semantic cache for LLM responses."""

import hashlib
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SemanticCache:
    """TTL-based cache with intent-based key generation."""

    def __init__(self, ttl_days: int = 7):
        self._cache: dict[str, dict] = {}
        self._ttl_seconds = ttl_days * 86400

    def _key(self, question: str) -> str:
        """Generate a cache key from the question (normalized)."""
        normalized = question.strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get(self, question: str) -> dict | None:
        """Try to get a cached response."""
        key = self._key(question)
        entry = self._cache.get(key)
        if entry:
            age = time.time() - entry["timestamp"]
            if age < self._ttl_seconds:
                logger.info(f"Cache hit for: {question[:50]}")
                return entry["response"]
            else:
                del self._cache[key]
        return None

    def set(self, question: str, response: dict):
        """Cache a response."""
        key = self._key(question)
        self._cache[key] = {
            "response": response,
            "timestamp": time.time(),
        }

    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# Singleton
semantic_cache = SemanticCache(ttl_days=7)
