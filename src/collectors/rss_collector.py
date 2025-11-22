# -*- coding: utf-8 -*-
"""RSS feed collector."""

import feedparser
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.collectors.base_collector import BaseCollector
from src.utils.logger import get_logger
from src.utils.retry_handler import retry_on_connection_error


class RSSCollector(BaseCollector):
    """Collects data from RSS feeds."""

    def __init__(
        self,
        feed_config: Dict[str, str],
        max_entries: int = 30,
    ):
        """Initialize RSS collector.

        Args:
            feed_config: Feed configuration dictionary with:
                - name: str (feed name)
                - url: str (feed URL)
                - source_type: str (e.g., '博客', '论文')
            max_entries: Maximum number of entries to collect per feed.
        """
        self.feed_config = feed_config
        self.max_entries = max_entries
        self.logger = get_logger(__name__)

    @retry_on_connection_error(max_attempts=3)
    def collect(self) -> List[Dict[str, Any]]:
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

    def _process_entry(self, entry: feedparser.FeedParserDict) -> Optional[Dict[str, Any]]:
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
        summary = entry.get("summary", "")
        published = entry.get("published") or entry.get("updated")

        # Parse date if available
        if published and hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                from time import mktime
                from datetime import datetime
                published = datetime.fromtimestamp(mktime(entry.published_parsed)).isoformat()
            except (ValueError, OSError, OverflowError):
                published = datetime.now().isoformat()
        elif not published:
            published = datetime.now().isoformat()

        return {
            "title": title,
            "link": link,
            "summary": summary,
            "published": published,
            "source_name": self.feed_config.get("name", "Unknown"),
            "source_type": self.feed_config.get("source_type", "博客"),
        }

    def get_source_name(self) -> str:
        """Get the name of this data source.

        Returns:
            Source name string.
        """
        return self.feed_config.get("name", "RSS Feed")

