# -*- coding: utf-8 -*-
"""Cache manager using diskcache for local state tracking."""

from pathlib import Path

import diskcache as dc


class CacheManager:
    """Manages local cache for deduplication and state tracking using diskcache."""

    def __init__(
        self,
        cache_dir: str | None = None,
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
        self.ttl_seconds = ttl_days * 24 * 60 * 60

        # Initialize diskcache
        self.cache = dc.Cache(
            str(self.cache_dir),
            size_limit=1000000,  # 1MB limit
            default_timeout=self.ttl_seconds,
        )

    def has_url(self, url: str) -> bool:
        """Check if URL exists in cache.

        Args:
            url: URL string to check.

        Returns:
            True if URL is in cache and not expired.
        """
        return url in self.cache

    def add_url(self, url: str) -> None:
        """Add URL to cache.

        Args:
            url: URL string to add.
        """
        self.cache.set(url, True, expire=self.ttl_seconds)

    def get_url_hash(self, url: str) -> str:
        """Get hash of URL for deduplication.

        Args:
            url: URL string.

        Returns:
            SHA256 hash of URL.
        """
        import hashlib

        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def clear_expired(self) -> int:
        """Clear expired cache entries.

        Returns:
            Number of entries removed (diskcache handles this automatically).
        """
        # diskcache automatically expires entries, so we just return 0
        # The actual cleanup happens during cache operations
        return 0

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        return {
            "total_urls": len(self.cache),
            "ttl_days": self.ttl_days,
        }
