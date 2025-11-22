# -*- coding: utf-8 -*-
"""Notion API client for data storage."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from dateutil import parser as dt_parser
from notion_client import Client
import pytz

from src.storages.base_storage import BaseStorage
from src.utils.logger import get_logger
from src.utils.retry_handler import retry_on_connection_error


class NotionStorage(BaseStorage):
    """Notion database storage implementation."""

    def __init__(
        self,
        token: str,
        database_id: str,
        timezone: str = "Asia/Shanghai",
    ):
        """Initialize Notion storage.

        Args:
            token: Notion integration token.
            database_id: Notion database ID.
            timezone: Timezone for date operations.
        """
        self.client = Client(auth=token)
        self.database_id = database_id
        self.timezone = pytz.timezone(timezone)
        self.logger = get_logger(__name__)

    @retry_on_connection_error(max_attempts=3)
    def exists(self, entry: Dict[str, Any]) -> bool:
        """Check if entry exists in Notion database.

        Args:
            entry: Entry dictionary with at least 'link' field.

        Returns:
            True if entry exists, False otherwise.
        """
        link = entry.get("link")
        if not link:
            return False

        try:
            response = self.client.databases.query(
                database_id=self.database_id,
                filter={"property": "链接", "url": {"equals": link}},
            )
            return len(response.get("results", [])) > 0
        except Exception as e:
            self.logger.error(f"Failed to query Notion database: {e}")
            return False

    @retry_on_connection_error(max_attempts=3)
    def save(self, entry: Dict[str, Any]) -> bool:
        """Save entry to Notion database.

        Args:
            entry: Processed entry dictionary with required fields:
                - title: str
                - link: str
                - source_type: str
                - topics: List[str]
                - priority: str
                - published: str (ISO format date string)

        Returns:
            True if saved successfully, False otherwise.

        Raises:
            ValueError: If entry is invalid or missing required fields.
            ConnectionError: If connection to Notion fails.
        """
        # Validate required fields
        required_fields = ["title", "link", "source_type", "topics", "priority"]
        for field in required_fields:
            if field not in entry:
                raise ValueError(f"Missing required field: {field}")

        try:
            # Parse date
            date_str = entry.get("published", datetime.now().isoformat())
            try:
                dt = dt_parser.parse(date_str)
                if dt.tzinfo is None:
                    dt = self.timezone.localize(dt)
                else:
                    dt = dt.astimezone(self.timezone)
                iso_date = dt.date().isoformat()
            except (ValueError, TypeError):
                iso_date = datetime.now(self.timezone).date().isoformat()

            # Truncate title if too long (Notion has limits)
            title = entry["title"][:200] if len(entry["title"]) > 200 else entry["title"]

            # Create page
            self.client.pages.create(
                parent={"database_id": self.database_id},
                properties={
                    "情报标题": {"title": [{"text": {"content": title}}]},
                    "来源类型": {"select": {"name": entry["source_type"]}},
                    "链接": {"url": entry["link"]},
                    "日期": {"date": {"start": iso_date}},
                    "优先级": {"select": {"name": entry["priority"]}},
                    "主题": {
                        "multi_select": [{"name": topic} for topic in entry["topics"]]
                    },
                },
            )

            self.logger.info(f"Saved entry to Notion: {title[:50]}...")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save entry to Notion: {e}")
            raise

    def query(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Query entries from Notion database.

        Args:
            **kwargs: Query parameters:
                - filter: Dict (Notion filter object)
                - sorts: List (Notion sort objects)

        Returns:
            List of matching entries.
        """
        try:
            response = self.client.databases.query(
                database_id=self.database_id,
                **kwargs,
            )
            return response.get("results", [])
        except Exception as e:
            self.logger.error(f"Failed to query Notion database: {e}")
            return []

