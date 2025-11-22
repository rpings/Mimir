# -*- coding: utf-8 -*-
"""Base storage interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseStorage(ABC):
    """Abstract base class for data storage."""

    @abstractmethod
    def exists(self, entry: Dict[str, Any]) -> bool:
        """Check if entry already exists in storage.

        Args:
            entry: Entry dictionary with at least 'link' field.

        Returns:
            True if entry exists, False otherwise.
        """
        pass

    @abstractmethod
    def save(self, entry: Dict[str, Any]) -> bool:
        """Save entry to storage.

        Args:
            entry: Processed entry dictionary with required fields:
                - title: str
                - link: str
                - source_type: str
                - topics: List[str]
                - priority: str
                - date: str (ISO format date string)

        Returns:
            True if saved successfully, False otherwise.

        Raises:
            ValueError: If entry is invalid or missing required fields.
            ConnectionError: If connection to storage fails.
        """
        pass

    @abstractmethod
    def query(self, **kwargs: Any) -> list[Dict[str, Any]]:
        """Query entries from storage.

        Args:
            **kwargs: Query parameters (implementation-specific).

        Returns:
            List of matching entries.
        """
        pass

