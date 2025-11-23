# -*- coding: utf-8 -*-
"""Content cleaning utilities."""

import re
from html import unescape


def clean_html(html_content: str) -> str:
    """Remove HTML tags and decode HTML entities.

    Args:
        html_content: HTML content string.

    Returns:
        Cleaned text content.
    """
    if not html_content:
        return ""

    # Decode HTML entities
    text = unescape(html_content)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_text(text: str | None) -> str:
    """Normalize text for comparison and processing.

    Args:
        text: Input text string.

    Returns:
        Normalized text (lowercase, whitespace normalized).
    """
    if not text:
        return ""

    # Convert to lowercase
    normalized = text.lower()

    # Normalize whitespace
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to maximum length.

    Args:
        text: Input text string.
        max_length: Maximum length in characters.

    Returns:
        Truncated text with ellipsis if needed.
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    # Truncate and add ellipsis
    return text[: max_length - 3] + "..."


def extract_summary(content: str, max_sentences: int = 3) -> str:
    """Extract summary from content (first N sentences).

    Args:
        content: Full content text.
        max_sentences: Maximum number of sentences to extract.

    Returns:
        Summary text.
    """
    if not content:
        return ""

    # Split into sentences (simple approach)
    sentences = re.split(r"[.!?]+\s+", content)

    # Take first N sentences
    summary_sentences = sentences[:max_sentences]

    # Join and clean
    summary = ". ".join(summary_sentences)
    if summary and not summary.endswith("."):
        summary += "."

    return summary.strip()

