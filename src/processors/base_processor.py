# -*- coding: utf-8 -*-
"""Base processor interface."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from src.collectors.base_collector import CollectedEntry


class ProcessedEntry(CollectedEntry):
    """Processed entry with classification and optional LLM enhancements.

    Extends CollectedEntry with processing results. LLM fields are optional
    and will be None when LLM is disabled or fails (graceful degradation).
    """

    # Core processing fields (always present)
    topics: list[str] = Field(default_factory=list)
    priority: str = Field(default="Low")  # High/Medium/Low
    status: str | None = Field(default=None, max_length=50)

    # LLM-enhanced fields (optional, None if LLM disabled/failed)
    summary_llm: str | None = Field(default=None, max_length=5000)
    translation: dict[str, str] | None = Field(default=None)
    topics_llm: list[str] | None = Field(default=None)
    priority_llm: str | None = Field(default=None)

    # Metadata
    processing_method: str = Field(default="keyword")  # keyword, llm, hybrid
    llm_cost: float = Field(default=0.0, ge=0.0)
    llm_tokens: int = Field(default=0, ge=0)

    @classmethod
    def from_collected(cls, entry: CollectedEntry) -> "ProcessedEntry":
        """Create ProcessedEntry from CollectedEntry.

        Args:
            entry: CollectedEntry instance.

        Returns:
            ProcessedEntry with all collected fields copied.
        """
        return cls(
            title=entry.title,
            link=entry.link,
            summary=entry.summary,
            published=entry.published,
            source_name=entry.source_name,
            source_type=entry.source_type,
        )


class BaseProcessor(ABC):
    """Abstract base class for content processors."""

    @abstractmethod
    def process(self, entry: CollectedEntry) -> ProcessedEntry:
        """Process a single content entry.

        Args:
            entry: CollectedEntry with at least title, link, and summary.

        Returns:
            ProcessedEntry with classification results (topics, priority)
            and optional LLM enhancements.

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

