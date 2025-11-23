# -*- coding: utf-8 -*-
"""Notion API client for data storage."""

from datetime import datetime
from typing import Any

from dateutil import parser as dt_parser
from notion_client import Client
import pytz

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
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
        field_names: dict[str, str] | None = None,
    ):
        """Initialize Notion storage.

        Args:
            token: Notion integration token.
            database_id: Notion database ID.
            timezone: Timezone for date operations.
            field_names: Dictionary mapping field keys to Notion property names.
                Defaults to English field names if not provided.
        """
        self.client = Client(auth=token)
        self.database_id = database_id
        self.timezone = pytz.timezone(timezone)
        self.logger = get_logger(__name__)
        
        # Default English field names (i18n compliant)
        default_fields = {
            "title": "Title",
            "source_type": "Source Type",
            "link": "Link",
            "date": "Date",
            "priority": "Priority",
            "topics": "Topics",
            "status": "Status",
        }
        self.field_names = field_names if field_names else default_fields

    @retry_on_connection_error(max_attempts=3)
    def exists(self, entry: CollectedEntry | ProcessedEntry) -> bool:
        """Check if entry exists in Notion database.

        Args:
            entry: Entry with link field (CollectedEntry or ProcessedEntry).

        Returns:
            True if entry exists, False otherwise.
            Returns False on error to allow retry, but caller should handle gracefully.
        """
        link = str(entry.link)
        if not link:
            return False

        try:
            # Format database ID: remove hyphens for URL path (Notion API requirement)
            db_id = self.database_id.replace("-", "")
            
            # Use request method - path should not include /v1/ prefix (added automatically)
            response = self.client.request(
                path=f"databases/{db_id}/query",
                method="POST",
                body={"filter": {"property": self.field_names["link"], "url": {"equals": link}}},
            )
            results = response.get("results", [])
            exists = len(results) > 0
            if exists:
                self.logger.debug(f"Entry exists in Notion: {link[:50]}...")
            return exists
        except Exception as e:
            # Log error but return False to allow retry
            # Caller should handle this gracefully (e.g., try save and catch duplicate error)
            self.logger.warning(f"Failed to query Notion database for existence check: {e}")
            return False

    @retry_on_connection_error(max_attempts=3)
    def save(self, entry: ProcessedEntry) -> bool:
        """Save entry to Notion database.

        Args:
            entry: ProcessedEntry with required fields.

        Returns:
            True if saved successfully, False otherwise.

        Raises:
            ValueError: If entry is invalid or missing required fields.
            ConnectionError: If connection to Notion fails.
        """
        try:
            # Parse date
            date_str = entry.published or datetime.now().isoformat()
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
            title = entry.title[:200] if len(entry.title) > 200 else entry.title

            # Prepare properties
            properties = {
                self.field_names["title"]: {"title": [{"text": {"content": title}}]},
                self.field_names["link"]: {"url": str(entry.link)},
                self.field_names["date"]: {"date": {"start": iso_date}},
                self.field_names["priority"]: {"select": {"name": entry.priority}},
                self.field_names["topics"]: {
                    "multi_select": [{"name": topic} for topic in entry.topics]
                },
            }

            # Add source_type if available
            if entry.source_type:
                properties[self.field_names["source_type"]] = {
                    "select": {"name": entry.source_type}
                }

            # Add status if available
            if entry.status:
                properties[self.field_names["status"]] = {
                    "select": {"name": entry.status}
                }

            # Create page
            # Note: Notion API will return error if duplicate, but we check exists() first
            try:
                self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                )
                self.logger.info(f"Saved entry to Notion: {title[:50]}...")
                return True
            except Exception as create_error:
                # Check if it's a duplicate error (Notion may return specific error codes)
                error_str = str(create_error).lower()
                if "duplicate" in error_str or "already exists" in error_str:
                    self.logger.warning(f"Entry already exists in Notion (duplicate): {title[:50]}...")
                    return False  # Not saved, but not an error
                # Re-raise other errors
                raise

        except Exception as e:
            self.logger.error(f"Failed to save entry to Notion: {e}")
            raise

    def query(self, **kwargs: Any) -> list[ProcessedEntry]:
        """Query entries from Notion database.

        Args:
            **kwargs: Query parameters:
                - filter: dict (Notion filter object)
                - sorts: list (Notion sort objects)
                - start_cursor: str (pagination cursor)
                - page_size: int (results per page)

        Returns:
            List of matching ProcessedEntry instances.
            Note: Currently returns empty list. Full ProcessedEntry
            conversion requires parsing Notion page properties.
        """
        try:
            # Use request method - path should not include /v1/ prefix (added automatically)
            body = {}
            if "filter" in kwargs:
                body["filter"] = kwargs["filter"]
            if "sorts" in kwargs:
                body["sorts"] = kwargs["sorts"]
            if "start_cursor" in kwargs:
                body["start_cursor"] = kwargs["start_cursor"]
            if "page_size" in kwargs:
                body["page_size"] = kwargs["page_size"]

            # Format database ID: remove hyphens for URL path (Notion API requirement)
            db_id = self.database_id.replace("-", "")
            
            response = self.client.request(
                path=f"databases/{db_id}/query",
                method="POST",
                body=body if body else None,
            )
            # TODO: Convert Notion results to ProcessedEntry
            # For now, return empty list as this method is not actively used
            return []
        except Exception as e:
            self.logger.error(f"Failed to query Notion database: {e}")
            return []

