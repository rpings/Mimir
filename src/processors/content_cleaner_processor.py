# -*- coding: utf-8 -*-
"""Content cleaning and normalization processor."""

from typing import Any

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.content_cleaner import (
    clean_html,
    extract_summary,
    normalize_text,
    truncate_text,
)
from src.processors.processing_context import ProcessingContext
from src.utils.logger import get_logger


class ContentCleanerProcessor(BaseProcessor):
    """Processor for cleaning and normalizing content.

    This processor:
    - Cleans HTML tags and entities
    - Normalizes text (whitespace, encoding)
    - Extracts clean summaries
    - Formats dates and URLs
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize content cleaner processor.

        Args:
            config: Configuration dictionary with:
                - enabled: bool (default: True)
                - remove_ads: bool (default: True)
                - normalize_encoding: bool (default: True)
                - max_summary_length: int (default: 500)
        """
        super().__init__(config)
        self.remove_ads = self.config.get("remove_ads", True)
        self.normalize_encoding = self.config.get("normalize_encoding", True)
        self.max_summary_length = self.config.get("max_summary_length", 500)
        self.logger = get_logger(__name__)

    def process(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:
        """Clean and normalize content.

        Args:
            entry: CollectedEntry or ProcessedEntry to clean.
            context: Optional processing context (not used in this processor).

        Returns:
            ProcessedEntry with cleaned content, or None if entry is invalid.
        """
        # Convert to ProcessedEntry if needed
        if isinstance(entry, ProcessedEntry):
            processed = entry
        else:
            processed = ProcessedEntry.from_collected(entry)

        # Clean summary content
        original_summary = processed.summary or ""
        cleaned_content = clean_html(original_summary)

        # Extract normalized text
        normalized = normalize_text(cleaned_content)

        # Extract clean summary (first 3 sentences, then truncate)
        if cleaned_content:
            summary_text = extract_summary(cleaned_content, max_sentences=3)
            summary_text = truncate_text(summary_text, self.max_summary_length)
        else:
            summary_text = ""

        # Update processed entry
        processed.cleaned_content = cleaned_content
        processed.normalized_text = normalized

        # Update summary with cleaned version if it's different
        if summary_text and summary_text != original_summary:
            processed.summary = summary_text

        # Validate entry is still valid after cleaning
        if not processed.title or not processed.link:
            self.logger.warning(f"Entry invalid after cleaning: {processed.title[:50]}")
            return None

        return processed

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "ContentCleanerProcessor"

