# -*- coding: utf-8 -*-
"""Base storage interface."""

from abc import ABC, abstractmethod
from typing import Any

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry


class BaseStorage(ABC):
    """Abstract base class for data storage."""

    @abstractmethod
    def exists(self, entry: CollectedEntry | ProcessedEntry) -> bool:
        """Check if entry already exists in storage.

        Args:
            entry: Entry with at least 'link' field (CollectedEntry or ProcessedEntry).

        Returns:
            True if entry exists, False otherwise.
        """
        pass

    @abstractmethod
    def save(self, entry: ProcessedEntry) -> bool:
        """Save entry to storage.

        Args:
            entry: ProcessedEntry with required fields:
                - title: str
                - link: HttpUrl
                - source_type: str | None
                - topics: list[str]
                - priority: str
                - published: str | None (ISO format date string)

        Returns:
            True if saved successfully, False otherwise.

        Raises:
            ValueError: If entry is invalid or missing required fields.
            ConnectionError: If connection to storage fails.
        """
        pass

    @abstractmethod
    def query(self, **kwargs: Any) -> list[ProcessedEntry]:
        """Query entries from storage.

        Args:
            **kwargs: Query parameters (implementation-specific).

        Returns:
            List of matching ProcessedEntry instances.
        """
        pass

