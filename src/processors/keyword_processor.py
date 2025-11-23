# -*- coding: utf-8 -*-
"""Keyword-based classification processor."""

import re
from typing import Any

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.content_cleaner import normalize_text
from src.utils.logger import get_logger


class KeywordProcessor(BaseProcessor):
    """Processes content using keyword-based classification."""

    def __init__(self, rules: dict[str, Any]):
        """Initialize keyword processor.

        Args:
            rules: Classification rules dictionary with:
                - topics: dict[str, list[str]] (topic name -> keyword list)
                - priority: dict[str, list[str]] (priority level -> keyword list)
        """
        self.rules = rules
        self.topic_rules = rules.get("topics", {})
        self.priority_rules = rules.get("priority", {})
        self.logger = get_logger(__name__)

    def process(self, entry: CollectedEntry) -> ProcessedEntry:
        """Process entry using keyword-based classification.

        Args:
            entry: CollectedEntry with title, summary, and link.

        Returns:
            ProcessedEntry with topics and priority assigned.
        """
        title = entry.title
        summary = entry.summary or ""

        # Classify topics
        topics = self._label_topics(title, summary)

        # Determine priority
        priority = self._guess_priority(title, summary)

        # Fallback for arXiv feeds
        if not topics and "arxiv" in str(entry.link).lower():
            if "retriev" in (title + summary).lower():
                topics = ["RAG"]
            else:
                topics = ["Agent"]

        # Create ProcessedEntry from CollectedEntry
        processed = ProcessedEntry.from_collected(entry)
        processed.topics = topics
        processed.priority = priority
        processed.processing_method = "keyword"

        return processed

    def _label_topics(self, title: str, summary: str) -> list[str]:
        """Label topics based on keyword matching.

        Args:
            title: Article title.
            summary: Article summary.

        Returns:
            List of matching topic names (sorted, unique).
        """
        text = f" {normalize_text(title)} {normalize_text(summary)} "
        matched_topics: set[str] = set()

        for topic, keywords in self.topic_rules.items():
            for keyword in keywords:
                # Case-insensitive matching with word boundaries
                pattern = re.compile(rf"\b{re.escape(keyword.lower())}\b", re.IGNORECASE)
                if pattern.search(text):
                    matched_topics.add(topic)
                    break  # One keyword match is enough for this topic

        return sorted(matched_topics)

    def _guess_priority(self, title: str, summary: str) -> str:
        """Guess priority based on keyword matching.

        Args:
            title: Article title.
            summary: Article summary.

        Returns:
            Priority level: "High", "Medium", or "Low".
        """
        text = normalize_text(title + " " + summary)

        # Check in order: High -> Medium -> Low
        for level in ["High", "Medium"]:
            keywords = self.priority_rules.get(level, [])
            for keyword in keywords:
                if keyword.lower() in text:
                    return level

        return "Low"

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "KeywordProcessor"

