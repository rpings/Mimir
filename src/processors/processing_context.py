# -*- coding: utf-8 -*-
"""Processing context for sharing resources across processors."""

from typing import Any


class ProcessingContext:
    """Shared context for processors in pipeline.

    This context allows processors to share resources like embedding models,
    caches, and configuration without tight coupling.

    Attributes:
        embedding_model: Embedding model instance for semantic operations.
        cache: Cache instance for storing intermediate results.
        config: Global configuration dictionary.
        stats: Statistics dictionary for tracking processing metrics.
    """

    def __init__(
        self,
        embedding_model: Any | None = None,
        cache: Any | None = None,
        config: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
    ):
        """Initialize processing context.

        Args:
            embedding_model: Embedding model instance (e.g., sentence-transformers).
            cache: Cache instance for storing results.
            config: Global configuration dictionary.
            stats: Statistics dictionary for tracking metrics.
        """
        self.embedding_model = embedding_model
        self.cache = cache
        self.config = config or {}
        self.stats = stats or {}

    def get_stat(self, key: str, default: int = 0) -> int:
        """Get a statistic value.

        Args:
            key: Statistic key.
            default: Default value if key not found.

        Returns:
            Statistic value.
        """
        return self.stats.get(key, default)

    def increment_stat(self, key: str, amount: int = 1) -> None:
        """Increment a statistic value.

        Args:
            key: Statistic key.
            amount: Amount to increment by.
        """
        self.stats[key] = self.stats.get(key, 0) + amount

