# -*- coding: utf-8 -*-
"""Base processor interface."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from src.collectors.base_collector import CollectedEntry
from src.processors.processing_context import ProcessingContext


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

    # Content cleaning fields
    cleaned_content: str | None = Field(default=None, max_length=10000)
    normalized_text: str | None = Field(default=None, max_length=10000)

    # Quality assessment fields
    quality_scores: dict[str, float] | None = Field(default=None)
    quality_grade: str | None = Field(default=None, max_length=1)  # A/B/C/D
    overall_quality: float = Field(default=0.0, ge=0.0, le=1.0)

    # Semantic deduplication fields
    is_semantic_duplicate: bool = Field(default=False)
    duplicate_of: str | None = Field(default=None)
    similarity_score: float | None = Field(default=None, ge=0.0, le=1.0)

    # Information verification fields
    verification_status: str | None = Field(default=None, max_length=20)  # verified/suspicious/unverified
    verification_score: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_warnings: list[str] = Field(default_factory=list)

    # Knowledge extraction fields
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    structured_summary: dict[str, Any] | None = Field(default=None)
    auto_tags: list[str] = Field(default_factory=list)

    # Priority ranking fields
    final_priority: str = Field(default="Low", max_length=10)  # High/Medium/Low
    priority_score: float = Field(default=0.0, ge=0.0, le=1.0)
    ranking_reason: str | None = Field(default=None, max_length=500)

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
    """Abstract base class for content processors.

    Processors can accept both CollectedEntry and ProcessedEntry, allowing
    them to be chained in a pipeline. They can return None to indicate
    that the entry should be skipped.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize processor.

        Args:
            config: Processor-specific configuration dictionary.
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)

    @abstractmethod
    def process(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:  # pragma: no cover
        """Process a single content entry.

        Args:
            entry: CollectedEntry or ProcessedEntry to process.
            context: Optional shared context for pipeline resources.

        Returns:
            ProcessedEntry with processing results, or None if entry should be skipped.

        Raises:
            ValueError: If processing fails due to invalid input.
        """
        pass

    async def aprocess(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:
        """Process entry asynchronously.

        Default implementation calls process() in thread pool.
        Override for async-optimized processors.

        Args:
            entry: CollectedEntry or ProcessedEntry to process.
            context: Optional shared context for pipeline resources.

        Returns:
            ProcessedEntry with processing results, or None if entry should be skipped.
        """
        return await asyncio.to_thread(self.process, entry, context)

    @abstractmethod
    def get_processor_name(self) -> str:  # pragma: no cover
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        pass

    def is_enabled(self) -> bool:
        """Check if processor is enabled.

        Returns:
            True if processor is enabled, False otherwise.
        """
        return self.enabled

