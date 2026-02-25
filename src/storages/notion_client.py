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


def _normalize_link(link: str) -> str:
    """Normalize URL for consistent deduplication.

    Strips fragment, trailing slash, and defaults to https scheme so
    variants of the same URL are treated as one.

    Args:
        link: Raw URL string.

    Returns:
        Normalized URL string.
    """
    if not link or not link.strip():
        return ""
    s = link.strip()
    if "://" not in s:
        s = "https://" + s
    if s.startswith("http://"):
        s = "https://" + s[7:]
    # Strip fragment
    if "#" in s:
        s = s.split("#", 1)[0]
    # Strip trailing slash (except for bare "https://")
    if len(s) > 8 and s.endswith("/"):
        s = s[:-1]
    return s


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
        # Cache of existing links (normalized) for fallback when filter API is unsupported
        self._existing_links_cache: set[str] | None = None
        # Data source ID for 2025-09-03 API (query uses data_sources, not databases)
        self._data_source_id: str | None = None

    def _get_data_source_id(self) -> str | None:
        """Resolve data source ID from database (API 2025-09-03). Cached."""
        if self._data_source_id is not None:
            return self._data_source_id
        try:
            resp = self.client.databases.retrieve(self.database_id)
            sources = resp.get("data_sources") or []
            if not sources:
                self.logger.warning("Database has no data_sources (2025 API)")
                return None
            self._data_source_id = sources[0].get("id")
            return self._data_source_id
        except Exception as e:
            self.logger.warning(f"Failed to get data_source_id from database: {e}")
            return None

    def _load_existing_links(self) -> set[str]:
        """Paginate through database and collect all link URLs (normalized).

        Used when the filter API does not support URL (e.g. url filter invalid).
        Cached for the process lifetime. Uses data_sources/query (API 2025-09-03).

        Returns:
            Set of normalized link URLs present in the database.
        """
        if self._existing_links_cache is not None:
            return self._existing_links_cache
        ds_id = self._get_data_source_id()
        if not ds_id:
            return set()
        link_prop = self.field_names["link"]
        seen: set[str] = set()
        cursor: str | None = None
        try:
            while True:
                body: dict[str, Any] = {"page_size": 100}
                if cursor:
                    body["start_cursor"] = cursor
                response = self.client.data_sources.query(ds_id, **body)
                results = response.get("results", [])
                for page in results:
                    props = page.get("properties", {})
                    link_obj = props.get(link_prop)
                    if not link_obj:
                        continue
                    url = link_obj.get("url")
                    if url and isinstance(url, str):
                        seen.add(_normalize_link(url))
                cursor = response.get("next_cursor")
                if not cursor:
                    break
            self.logger.debug(f"Loaded {len(seen)} existing links from Notion for dedup fallback")
        except Exception as e:
            self.logger.warning(f"Failed to load existing links from Notion: {e}")
        self._existing_links_cache = seen
        return seen

    @retry_on_connection_error(max_attempts=3)
    def exists(self, entry: CollectedEntry | ProcessedEntry) -> bool:
        """Check if entry exists in Notion database.

        Tries rich_text filter first (Notion API does not support "url" filter type).
        On filter error, falls back to in-memory set of links loaded via pagination.

        Args:
            entry: Entry with link field (CollectedEntry or ProcessedEntry).

        Returns:
            True if entry exists, False otherwise.
            Returns False on error to allow retry, but caller should handle gracefully.
        """
        link = str(entry.link)
        if not link:
            return False
        normalized = _normalize_link(link)
        if not normalized:
            return False

        link_prop = self.field_names["link"]
        ds_id = self._get_data_source_id()
        if not ds_id:
            existing = self._load_existing_links()
            return normalized in existing

        # Try rich_text filter first (API supports rich_text, not url)
        try:
            response = self.client.data_sources.query(
                ds_id,
                filter={
                    "property": link_prop,
                    "rich_text": {"equals": normalized},
                },
                page_size=1,
            )
            results = response.get("results", [])
            if len(results) > 0:
                self.logger.debug(f"Entry exists in Notion: {link[:50]}...")
                return True
            return False
        except Exception as e:
            error_str = str(e).lower()
            if "validation" in error_str or "400" in error_str or "invalid" in error_str:
                self.logger.debug(
                    "rich_text filter not applicable for Link property, using link-set fallback"
                )
                existing = self._load_existing_links()
                return normalized in existing
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

            # Defensive check: do not create if entry already exists (by link)
            if self.exists(entry):
                self.logger.warning(
                    f"Entry already exists in Notion (skipping create): {title[:50]}..."
                )
                return False

            # Create page
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
                    self.logger.warning(
                        f"Entry already exists in Notion (duplicate): {title[:50]}..."
                    )
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
            ds_id = self._get_data_source_id()
            if not ds_id:
                return []
            body = {}
            if "filter" in kwargs:
                body["filter"] = kwargs["filter"]
            if "sorts" in kwargs:
                body["sorts"] = kwargs["sorts"]
            if "start_cursor" in kwargs:
                body["start_cursor"] = kwargs["start_cursor"]
            if "page_size" in kwargs:
                body["page_size"] = kwargs["page_size"]
            _ = self.client.data_sources.query(ds_id, **body)
            # TODO: Convert Notion results to ProcessedEntry
            return []
        except Exception as e:
            self.logger.error(f"Failed to query Notion database: {e}")
            return []

