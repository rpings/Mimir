# -*- coding: utf-8 -*-
"""Base processor interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseProcessor(ABC):
    """Abstract base class for content processors."""

    @abstractmethod
    def process(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single content entry.

        Args:
            entry: Raw content entry dictionary with at least:
                - title: str
                - link: str
                - summary: str (optional)

        Returns:
            Processed entry dictionary with additional fields:
                - topics: List[str] (topic tags)
                - priority: str (High/Medium/Low)
                - summary: str (cleaned summary, optional)
                - Any other processing results

        Raises:
            ValueError: If processing fails due to invalid input.
        """
        pass

    @abstractmethod
    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        pass

