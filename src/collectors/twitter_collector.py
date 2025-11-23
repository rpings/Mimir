# -*- coding: utf-8 -*-
"""Twitter/X collector (placeholder for Phase 3).

Note: Twitter/X API v2 requires authentication and has rate limits.
This is a placeholder implementation that can be extended with
Twitter API integration when API credentials are available.
"""

from datetime import datetime
from typing import Any

from src.collectors.base_collector import BaseCollector, CollectedEntry
from src.utils.logger import get_logger


class TwitterCollector(BaseCollector):
    """Collects data from Twitter/X accounts.

    Note: This is a placeholder implementation. Full implementation
    requires Twitter API v2 credentials and proper authentication.
    """

    def __init__(
        self,
        account_config: dict[str, str],
        max_entries: int = 30,
    ):
        """Initialize Twitter collector.

        Args:
            account_config: Account configuration dictionary with:
                - name: str (account name)
                - username: str (Twitter username, e.g., 'elonmusk')
                - source_type: str (e.g., 'social', 'news')
            max_entries: Maximum number of entries to collect per account.
        """
        self.account_config = account_config
        self.max_entries = max_entries
        self.logger = get_logger(__name__)

    async def acollect(self) -> list[CollectedEntry]:
        """Collect entries from Twitter account asynchronously.

        Note: This is a placeholder. Full implementation requires:
        - Twitter API v2 credentials (BEARER_TOKEN)
        - API endpoint: https://api.twitter.com/2/tweets/search/recent
        - Proper authentication headers

        Returns:
            List of tweet entries (currently empty placeholder).

        Raises:
            NotImplementedError: Until full API integration is implemented.
        """
        self.logger.warning(
            "Twitter collector is a placeholder. "
            "Full implementation requires Twitter API v2 credentials."
        )
        # Placeholder: return empty list
        # TODO: Implement Twitter API v2 integration
        return []

    def collect(self) -> list[CollectedEntry]:
        """Collect entries from Twitter account.

        Returns:
            List of tweet entries (currently empty placeholder).
        """
        import asyncio
        return asyncio.run(self.acollect())

    def get_source_name(self) -> str:
        """Get the name of this data source.

        Returns:
            Source name string.
        """
        return self.account_config.get("name", "Twitter Account")

