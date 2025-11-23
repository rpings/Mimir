# -*- coding: utf-8 -*-
"""YouTube channel collector using RSS feeds."""

import re
from datetime import datetime
from typing import Any

import httpx

from src.collectors.base_collector import BaseCollector, CollectedEntry
from src.utils.logger import get_logger
from src.utils.retry_handler import retry_on_connection_error


class YouTubeCollector(BaseCollector):
    """Collects data from YouTube channels via RSS feeds.

    YouTube provides RSS feeds for channels at:
    https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}
    or
    https://www.youtube.com/feeds/videos.xml?user={USERNAME}
    """

    def __init__(
        self,
        channel_config: dict[str, str],
        max_entries: int = 30,
    ):
        """Initialize YouTube collector.

        Args:
            channel_config: Channel configuration dictionary with:
                - name: str (channel name)
                - channel_id: str (YouTube channel ID) OR username: str
                - source_type: str (e.g., 'video', 'tutorial')
            max_entries: Maximum number of entries to collect per channel.
        """
        self.channel_config = channel_config
        self.max_entries = max_entries
        self.logger = get_logger(__name__)

    def _get_rss_url(self) -> str:
        """Get YouTube RSS feed URL from channel configuration.

        Returns:
            RSS feed URL string.

        Raises:
            ValueError: If neither channel_id nor username is provided.
        """
        channel_id = self.channel_config.get("channel_id")
        username = self.channel_config.get("username")

        if channel_id:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        elif username:
            return f"https://www.youtube.com/feeds/videos.xml?user={username}"
        else:
            raise ValueError("Either 'channel_id' or 'username' must be provided in channel_config")

    async def acollect(self) -> list[CollectedEntry]:
        """Collect entries from YouTube channel asynchronously.

        Returns:
            List of video entries.

        Raises:
            ValueError: If channel configuration is invalid or collection fails.
            ConnectionError: If connection to YouTube fails.
        """
        rss_url = self._get_rss_url()

        try:
            # Use httpx for async HTTP requests
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(rss_url)
                response.raise_for_status()
                feed_content = response.text

            # Parse RSS feed (YouTube uses Atom format)
            import feedparser
            feed = feedparser.parse(feed_content)

            # Check for parsing errors
            if feed.bozo:
                error_msg = str(feed.bozo_exception) if hasattr(feed, 'bozo_exception') else "Unknown error"
                self.logger.warning(f"YouTube feed parsing warning for {rss_url}: {error_msg}")

            entries = []
            for entry in feed.entries[:self.max_entries]:
                processed_entry = self._process_entry(entry)
                if processed_entry:
                    entries.append(processed_entry)

            self.logger.info(f"Collected {len(entries)} entries from {self.channel_config.get('name', 'Unknown')}")
            return entries

        except httpx.HTTPError as e:
            self.logger.error(f"HTTP error fetching YouTube feed {rss_url}: {e}")
            raise ValueError(f"Failed to fetch YouTube feed: {e}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error collecting YouTube feed {rss_url}: {e}")
            raise ValueError(f"Failed to parse YouTube feed: {e}") from e

    @retry_on_connection_error(max_attempts=3)
    def collect(self) -> list[CollectedEntry]:
        """Collect entries from YouTube channel.

        Returns:
            List of video entries.

        Raises:
            ValueError: If channel configuration is invalid or collection fails.
            ConnectionError: If connection to YouTube fails.
        """
        import asyncio
        return asyncio.run(self.acollect())

    def _process_entry(self, entry: dict[str, Any]) -> CollectedEntry | None:
        """Process a single YouTube video entry.

        Args:
            entry: Raw feedparser entry.

        Returns:
            Processed entry or None if invalid.
        """
        link = entry.get("link")
        if not link:
            return None

        title = entry.get("title", "Untitled")
        summary = entry.get("summary", "")
        
        # Extract video description from summary (may contain HTML)
        if summary:
            # Remove HTML tags
            summary = re.sub(r"<[^>]+>", "", summary)
            # Clean up whitespace
            summary = re.sub(r"\s+", " ", summary).strip()

        # Parse published date
        published = entry.get("published") or entry.get("updated")
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
            source_name=self.channel_config.get("name", "Unknown YouTube Channel"),
            source_type=self.channel_config.get("source_type", "video"),
        )

    def get_source_name(self) -> str:
        """Get the name of this data source.

        Returns:
            Source name string.
        """
        return self.channel_config.get("name", "YouTube Channel")

