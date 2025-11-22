# -*- coding: utf-8 -*-
"""Cache manager for local state tracking."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set


class CacheManager:
    """Manages local cache for deduplication and state tracking."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_days: int = 30,
    ):
        """Initialize cache manager.

        Args:
            cache_dir: Cache directory path. Defaults to 'data/cache'.
            ttl_days: Time-to-live for cache entries in days.
        """
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.ttl_days = ttl_days
        self.url_cache_file = self.cache_dir / "urls.json"
        self._url_cache: Set[str] = set()
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if not self.url_cache_file.exists():
            return

        try:
            with open(self.url_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Filter expired entries
                now = datetime.now()
                self._url_cache = {
                    url
                    for url, timestamp_str in data.items()
                    if self._is_valid_entry(timestamp_str, now)
                }
        except (json.JSONDecodeError, KeyError, ValueError):
            # If cache is corrupted, start fresh
            self._url_cache = set()

    def _is_valid_entry(self, timestamp_str: str, now: datetime) -> bool:
        """Check if cache entry is still valid.

        Args:
            timestamp_str: ISO format timestamp string.
            now: Current datetime.

        Returns:
            True if entry is still valid (within TTL).
        """
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            age = now - timestamp
            return age < timedelta(days=self.ttl_days)
        except (ValueError, TypeError):
            return False

    def _save_cache(self) -> None:
        """Save cache to disk."""
        now = datetime.now().isoformat()
        data = {url: now for url in self._url_cache}

        try:
            with open(self.url_cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except (IOError, OSError):
            # If save fails, continue without cache persistence
            pass

    def has_url(self, url: str) -> bool:
        """Check if URL exists in cache.

        Args:
            url: URL string to check.

        Returns:
            True if URL is in cache.
        """
        return url in self._url_cache

    def add_url(self, url: str) -> None:
        """Add URL to cache.

        Args:
            url: URL string to add.
        """
        self._url_cache.add(url)
        self._save_cache()

    def get_url_hash(self, url: str) -> str:
        """Get hash of URL for deduplication.

        Args:
            url: URL string.

        Returns:
            SHA256 hash of URL.
        """
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def clear_expired(self) -> int:
        """Clear expired cache entries.

        Returns:
            Number of entries removed.
        """
        initial_count = len(self._url_cache)
        self._load_cache()  # Reload to filter expired
        removed = initial_count - len(self._url_cache)
        if removed > 0:
            self._save_cache()
        return removed

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        return {
            "total_urls": len(self._url_cache),
            "ttl_days": self.ttl_days,
        }

