# -*- coding: utf-8 -*-
"""Deduplication logic."""

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.storages.base_storage import BaseStorage
from src.storages.cache_manager import CacheManager


class Deduplicator:
    """Handles content deduplication using cache and storage."""

    def __init__(
        self,
        storage: BaseStorage,
        cache_manager: CacheManager,
    ):
        """Initialize deduplicator.

        Args:
            storage: Storage instance for checking existing entries.
            cache_manager: Cache manager for local URL tracking.
        """
        self.storage = storage
        self.cache_manager = cache_manager

    def is_duplicate(self, entry: CollectedEntry | ProcessedEntry) -> bool:
        """Check if entry is a duplicate.

        Args:
            entry: Entry with link field (CollectedEntry or ProcessedEntry).

        Returns:
            True if entry is a duplicate, False otherwise.
        """
        link = str(entry.link)
        if not link:
            return False

        # Check local cache first (fast)
        if self.cache_manager.has_url(link):
            return True

        # Check storage (slower, but authoritative)
        if self.storage.exists(entry):
            # Add to cache for future fast lookup
            self.cache_manager.add_url(link)
            return True

        return False

    def mark_as_processed(self, entry: CollectedEntry | ProcessedEntry) -> None:
        """Mark entry as processed (add to cache).

        Args:
            entry: Entry with link field (CollectedEntry or ProcessedEntry).
        """
        link = str(entry.link)
        if link:
            self.cache_manager.add_url(link)

