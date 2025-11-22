# -*- coding: utf-8 -*-
"""Base collector interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseCollector(ABC):
    """Abstract base class for data collectors."""

    @abstractmethod
    def collect(self) -> List[Dict[str, Any]]:
        """Collect data from source.

        Returns:
            List of collected items, each as a dictionary with at least:
            - title: str
            - link: str
            - summary: str (optional)
            - published: str (optional, ISO format date string)

        Raises:
            ValueError: If collection fails due to invalid configuration.
            ConnectionError: If connection to source fails.
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Get the name of this data source.

        Returns:
            Source name string.
        """
        pass

