# -*- coding: utf-8 -*-
"""LLM result caching to avoid duplicate API calls."""

import hashlib
from pathlib import Path

import diskcache as dc

from src.utils.logger import get_logger


class LLMCache:
    """Cache for LLM processing results."""

    def __init__(
        self,
        cache_dir: str | None = None,
        ttl_days: int = 30,
    ):
        """Initialize LLM cache.

        Args:
            cache_dir: Cache directory path. Defaults to 'data/cache/llm'.
            ttl_days: Time-to-live for cache entries in days.
        """
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "cache" / "llm"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.ttl_days = ttl_days
        self.ttl_seconds = ttl_days * 24 * 60 * 60

        # Initialize diskcache
        self.cache = dc.Cache(
            str(self.cache_dir),
            size_limit=5000000,  # 5MB limit
            default_timeout=self.ttl_seconds,
        )

        self.logger = get_logger(__name__)

    def _get_cache_key(self, content: str, feature_type: str) -> str:
        """Generate cache key for content and feature type.

        Args:
            content: Content to cache (title + summary).
            feature_type: Type of LLM feature ('summary', 'translation', 'categorization').

        Returns:
            Cache key string (SHA256 hash).
        """
        key_string = f"{feature_type}:{content}"
        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

    def get(self, content: str, feature_type: str) -> str | None:
        """Get cached result.

        Args:
            content: Content to look up.
            feature_type: Type of LLM feature.

        Returns:
            Cached result or None if not found/expired.
        """
        key = self._get_cache_key(content, feature_type)
        result = self.cache.get(key)
        if result:
            self.logger.debug(f"Cache hit for {feature_type}")
        return result

    def set(self, content: str, feature_type: str, result: str) -> None:
        """Cache a result.

        Args:
            content: Content that was processed.
            feature_type: Type of LLM feature.
            result: Result to cache.
        """
        key = self._get_cache_key(content, feature_type)
        self.cache.set(key, result, expire=self.ttl_seconds)
        self.logger.debug(f"Cached result for {feature_type}")

    def clear(self) -> None:
        """Clear all cached entries."""
        self.cache.clear()
        self.logger.info("LLM cache cleared")

    def get_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        return {
            "total_entries": len(self.cache),
            "ttl_days": self.ttl_days,
        }

