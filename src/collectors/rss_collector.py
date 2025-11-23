# -*- coding: utf-8 -*-
"""RSS feed collector."""

import feedparser
from datetime import datetime
from typing import Any

import httpx

from src.collectors.base_collector import BaseCollector, CollectedEntry
from src.processors.content_cleaner import clean_html, extract_summary
from src.utils.logger import get_logger
from src.utils.retry_handler import retry_on_connection_error


class RSSCollector(BaseCollector):
    """Collects data from RSS feeds."""

    def __init__(
        self,
        feed_config: dict[str, str],
        max_entries: int = 30,
    ):
        """Initialize RSS collector.

        Args:
            feed_config: Feed configuration dictionary with:
                - name: str (feed name)
                - url: str (feed URL)
                - source_type: str (e.g., 'blog', 'paper')
            max_entries: Maximum number of entries to collect per feed.
        """
        self.feed_config = feed_config
        self.max_entries = max_entries
        self.logger = get_logger(__name__)

    async def acollect(self) -> list[CollectedEntry]:
        """Collect entries from RSS feed asynchronously.

        Returns:
            List of feed entries.

        Raises:
            ValueError: If feed URL is invalid or feed parsing fails.
            ConnectionError: If connection to feed fails.
        """
        url = self.feed_config.get("url")
        if not url:
            raise ValueError("Feed URL is required")

        try:
            # Use httpx for async HTTP requests
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                feed_content = response.text

            # Parse feed (feedparser is sync, but we're in async context)
            feed = feedparser.parse(feed_content)

            # Check for parsing errors
            if feed.bozo:
                error_msg = str(feed.bozo_exception) if hasattr(feed, 'bozo_exception') else "Unknown error"
                self.logger.warning(f"RSS feed parsing warning for {url}: {error_msg}")

            entries = []
            for entry in feed.entries[:self.max_entries]:
                processed_entry = self._process_entry(entry)
                if processed_entry:
                    entries.append(processed_entry)

            self.logger.info(f"Collected {len(entries)} entries from {self.feed_config.get('name', 'Unknown')}")
            return entries

        except httpx.HTTPError as e:
            self.logger.error(f"HTTP error fetching RSS feed {url}: {e}")
            raise ValueError(f"Failed to fetch RSS feed: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error collecting RSS feed {url}: {e}")
            raise ValueError(f"Failed to parse RSS feed: {e}") from e

    @retry_on_connection_error(max_attempts=3)
    def collect(self) -> list[CollectedEntry]:
        """Collect entries from RSS feed.

        Returns:
            List of feed entries, each containing:
                - title: str
                - link: str
                - summary: str
                - published: str (ISO format date string)
                - source_name: str
                - source_type: str

        Raises:
            ValueError: If feed URL is invalid or feed parsing fails.
            ConnectionError: If connection to feed fails.
        """
        url = self.feed_config.get("url")
        if not url:
            raise ValueError("Feed URL is required")

        self.logger.info(f"Fetching RSS feed: {self.feed_config.get('name', url)}")

        try:
            feed = feedparser.parse(url)

            # Check for parsing errors
            if feed.bozo:
                error_msg = str(feed.bozo_exception) if hasattr(feed, 'bozo_exception') else "Unknown error"
                self.logger.warning(f"RSS feed parsing warning for {url}: {error_msg}")

            entries = []
            for entry in feed.entries[:self.max_entries]:
                processed_entry = self._process_entry(entry)
                if processed_entry:
                    entries.append(processed_entry)

            self.logger.info(f"Collected {len(entries)} entries from {self.feed_config.get('name', url)}")
            return entries

        except Exception as e:
            self.logger.error(f"Failed to collect from RSS feed {url}: {e}")
            raise ValueError(f"Failed to parse RSS feed: {e}") from e

    def _process_entry(self, entry: feedparser.FeedParserDict) -> CollectedEntry | None:
        """Process a single RSS entry.

        Args:
            entry: Raw feedparser entry.

        Returns:
            Processed entry dictionary or None if invalid.
        """
        link = entry.get("link")
        if not link:
            return None

        title = entry.get("title", "Untitled")
        # Get summary/description from entry
        # For Atom feeds (like GitHub releases), summary may contain full HTML content
        raw_summary = entry.get("summary", "") or entry.get("description", "")
        
        # Clean HTML and extract meaningful summary
        if raw_summary:
            # Clean HTML tags and entities
            cleaned = clean_html(raw_summary)
            
            # Extract summary: first 3 sentences or max 500 chars
            if len(cleaned) > 500:
                # Try to extract first few sentences
                summary = extract_summary(cleaned, max_sentences=3)
                # If still too long, truncate
                if len(summary) > 500:
                    summary = cleaned[:497] + "..."
            else:
                summary = cleaned
        else:
            summary = ""
        
        published = entry.get("published") or entry.get("updated")

        # Parse date if available
        if published and hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                from time import mktime
                parsed_dt = datetime.fromtimestamp(mktime(entry.published_parsed))
                published = parsed_dt.isoformat()
            except (ValueError, OSError, OverflowError):
                published = datetime.now().isoformat()
        elif not published:
            published = datetime.now().isoformat()

        return CollectedEntry(
            title=title,
            link=link,
            summary=summary,
            published=published,
            source_name=self.feed_config.get("name", "Unknown"),
            source_type=self.feed_config.get("source_type", "blog"),
        )

    def get_source_name(self) -> str:
        """Get the name of this data source.

        Returns:
            Source name string.
        """
        return self.feed_config.get("name", "RSS Feed")

