"""Notion API operations — 2025 API: data_sources for query, pages for create."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from notion_client import Client

from mimir.models import EnrichedEntry, EntryType

log = logging.getLogger(__name__)

RATE = 0.35

TYPE_LABELS: dict[EntryType, str] = {
    EntryType.PAPER: "📄 论文",
    EntryType.REPO: "🛠️ 项目",
    EntryType.NEWS: "📰 新闻",
}


def _valid_venue(v: str) -> str:
    venues = {"arXiv", "NeurIPS", "ICML", "ICLR", "CVPR", "ACL", "Other"}
    return v if v in venues else "Other"


def _verification_label(v: str) -> str:
    return v.capitalize() if v in ("verified", "unverified", "rumor") else "Unverified"


def _priority_label(p: str) -> str:
    mapping = {"high": "★★★", "medium": "★★", "low": "★"}
    return mapping.get(p, "★★")


def _topic_label(topic_id: str) -> str:
    mapping = {
        "ai_agent": "AI Agent", "rag": "RAG / 检索增强",
        "inference": "推理优化", "multimodal": "多模态",
        "training": "训练与微调", "safety": "安全与对齐",
        "infra": "基础设施", "ai_coding": "AI Coding",
        "open_models": "开源模型", "industry": "行业动态",
    }
    return mapping.get(topic_id, "行业动态")


class NotionStore:
    """Read and write entries in a Notion database (2025 API)."""

    def __init__(self, token: str, database_id: str):
        if not token:
            raise ValueError("NOTION_TOKEN is required")
        if not database_id:
            raise ValueError("NOTION_DATABASE_ID is required")
        self._client = Client(auth=token)
        self._db_id = database_id
        self._ds_id: str | None = None  # data source ID (2025 API)
        self._last_req = 0.0
        self._links: set[str] = set()

    @property
    def client(self) -> Client:
        """Public accessor for the Notion API client."""
        return self._client

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_req
        if elapsed < RATE:
            time.sleep(RATE - elapsed)
        self._last_req = time.monotonic()

    def _get_data_source_id(self) -> str:
        """Resolve data_source ID from the database (2025 API)."""
        if self._ds_id:
            return self._ds_id
        self._rate_limit()
        resp = self._client.databases.retrieve(self._db_id)
        sources = resp.get("data_sources") or []
        if not sources:
            raise RuntimeError("Database has no data_sources (2025 API)")
        self._ds_id = sources[0]["id"]
        log.info("resolved data_source_id: %s", self._ds_id)
        return self._ds_id

    def load_existing_links(self) -> set[str]:
        """Fetch all existing link URLs for dedup (2025 API: data_sources.query)."""
        if self._links:
            return self._links
        ds_id = self._get_data_source_id()
        cursor: str | None = None
        while True:
            self._rate_limit()
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            resp = self._client.data_sources.query(ds_id, **params)
            for page in resp.get("results", []):
                link_prop = page.get("properties", {}).get("Link", {})
                url = link_prop.get("url", "")
                if url:
                    self._links.add(url)
            cursor = resp.get("next_cursor")
            if not cursor:
                break
        log.info("loaded %d existing links", len(self._links))
        return self._links

    def insert_entries(self, entries: list[EnrichedEntry], *, dry_run: bool = False) -> int:
        """Write entries to Notion. Returns count of newly created pages."""
        if not self._links:
            self.load_existing_links()

        created = 0
        for entry in entries:
            if entry.link in self._links:
                continue
            if dry_run:
                self._links.add(entry.link)
                created += 1
                continue

            try:
                self._create_page(entry)
                self._links.add(entry.link)
                created += 1
            except Exception as exc:
                log.warning("failed to create page for %s: %s", entry.link[:60], exc)

        log.info("inserted %d/%d entries", created, len(entries))
        return created

    def _create_page(self, entry: EnrichedEntry) -> None:
        props: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": entry.title[:200]}}]},
            "Type": {"select": {"name": TYPE_LABELS.get(entry.entry_type, "📰 新闻")}},
            "Topic": {"select": {"name": _topic_label(entry.topic)}},
            "Link": {"url": entry.link},
            "Published": {"date": {"start": entry.published.strftime("%Y-%m-%d")}},
            "Collected": {"date": {"start": datetime.now(UTC).strftime("%Y-%m-%d")}},
            "Status": {"status": {"name": "待读"}},
        }

        if entry.priority:
            props["Priority"] = {"select": {"name": _priority_label(entry.priority)}}

        # Paper-specific
        if entry.entry_type == EntryType.PAPER:
            if entry.overview:
                props["Overview"] = {"rich_text": [{"text": {"content": entry.overview[:500]}}]}
            if entry.innovation:
                props["Innovation"] = {"rich_text": [{"text": {"content": entry.innovation[:500]}}]}
            if entry.significance:
                props["Significance"] = {"rich_text": [{"text": {"content": entry.significance[:300]}}]}
            if entry.authors:
                props["Authors"] = {"rich_text": [{"text": {"content": entry.authors[:300]}}]}
            if entry.venue:
                props["Venue"] = {"select": {"name": _valid_venue(entry.venue)}}
        # Repo-specific
        elif entry.entry_type == EntryType.REPO:
            if entry.use_case:
                props["UseCase"] = {"rich_text": [{"text": {"content": entry.use_case[:500]}}]}
            if entry.stars:
                props["Stars"] = {"number": entry.stars}
        # News-specific
        elif entry.entry_type == EntryType.NEWS:
            if entry.key_point:
                props["KeyPoint"] = {"rich_text": [{"text": {"content": entry.key_point[:300]}}]}
            if entry.verification:
                props["Verification"] = {"select": {"name": _verification_label(entry.verification)}}

        # Page content for Gallery preview
        children = None
        body = entry.page_body()
        if body:
            children = [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": body[:2000]}}]},
            }]

        params: dict[str, Any] = {
            "parent": {"database_id": self._db_id},
            "properties": props,
        }
        if children:
            params["children"] = children

        self._rate_limit()
        self._client.pages.create(**params)


def _entries_props() -> dict[str, Any]:
    """Return the standard Entries DB properties."""
    return {
        "Name": {"title": {}},
        "Type": {"select": {"options": [
            {"name": "📄 论文", "color": "blue"},
            {"name": "🛠️ 项目", "color": "green"},
            {"name": "📰 新闻", "color": "yellow"},
        ]}},
        "Topic": {"select": {"options": [
            {"name": "AI Agent", "color": "red"},
            {"name": "RAG / 检索增强", "color": "orange"},
            {"name": "推理优化", "color": "blue"},
            {"name": "多模态", "color": "purple"},
            {"name": "训练与微调", "color": "pink"},
            {"name": "安全与对齐", "color": "gray"},
            {"name": "基础设施", "color": "brown"},
            {"name": "AI Coding", "color": "green"},
            {"name": "开源模型", "color": "blue"},
            {"name": "行业动态", "color": "yellow"},
        ]}},
        "Link": {"url": {}},
        "Published": {"date": {}},
        "Collected": {"date": {}},
        "Priority": {"select": {"options": [
            {"name": "★★★", "color": "red"},
            {"name": "★★", "color": "orange"},
            {"name": "★", "color": "gray"},
        ]}},
        "Status": {"status": {"options": [
            {"name": "待读", "color": "red"},
            {"name": "已读", "color": "green"},
            {"name": "已归档", "color": "gray"},
        ]}},
        "Overview": {"rich_text": {}},
        "Innovation": {"rich_text": {}},
        "Significance": {"rich_text": {}},
        "Authors": {"rich_text": {}},
        "Venue": {"select": {"options": [
            {"name": "arXiv", "color": "blue"},
            {"name": "NeurIPS", "color": "red"},
            {"name": "ICML", "color": "orange"},
            {"name": "ICLR", "color": "purple"},
            {"name": "CVPR", "color": "green"},
            {"name": "ACL", "color": "pink"},
            {"name": "Other", "color": "gray"},
        ]}},
        "UseCase": {"rich_text": {}},
        "Stars": {"number": {"format": "number"}},
        "KeyPoint": {"rich_text": {}},
        "Verification": {"select": {"options": [
            {"name": "Verified", "color": "green"},
            {"name": "Unverified", "color": "orange"},
            {"name": "Rumor", "color": "red"},
        ]}},
    }


def _reports_props() -> dict[str, Any]:
    """Return the standard Reports DB properties (report-level only, not entries)."""
    return {
        "Name": {"title": {}},
        "Date": {"date": {}},
        "Period": {"select": {"options": [
            {"name": "Weekly", "color": "blue"},
            {"name": "Monthly", "color": "purple"},
        ]}},
        "Link": {"url": {}},
        "Total": {"number": {"format": "number"}},
        "Papers": {"number": {"format": "number"}},
        "Repos": {"number": {"format": "number"}},
        "News": {"number": {"format": "number"}},
        "Hottest": {"select": {}},
        "HighPriority": {"number": {"format": "number"}},
        "Highlights": {"rich_text": {}},
    }


def repair_database(token: str, database_id: str) -> bool:
    """Ensure a database's data_source has all required properties."""
    import time as _time
    client = Client(auth=token)
    _time.sleep(0.35)
    db = client.databases.retrieve(database_id)
    sources = db.get("data_sources") or []
    if not sources:
        return False
    ds_id = sources[0]["id"]
    _time.sleep(0.35)
    client.data_sources.update(ds_id, properties=_entries_props())  # type: ignore[arg-type]
    return True


def repair_reports_database(token: str, database_id: str) -> bool:
    """Fix Reports DB schema — strip entry-level fields, add report-level fields."""
    import time as _time
    client = Client(auth=token)
    _time.sleep(0.35)
    db = client.databases.retrieve(database_id)
    sources = db.get("data_sources") or []
    if not sources:
        return False
    ds_id = sources[0]["id"]
    _time.sleep(0.35)
    client.data_sources.update(ds_id, properties=_reports_props())  # type: ignore[arg-type]
    return True


def find_database(token: str, name: str) -> str | None:
    """Search for an existing database by name under a parent page. Returns ID or None."""
    import time as _time
    client = Client(auth=token)
    _time.sleep(0.35)
    results = client.search(
        query=name,
        filter={"property": "object", "value": "data_source"},
    ).get("results", [])
    for db in results:
        title = "".join(t.get("plain_text", "") for t in (db.get("title") or []))
        if title == name:
            return db["id"]
    return None


def setup_entries_database(token: str, parent_page_id: str) -> str:
    """Create the Entries database with all properties. Returns database ID."""
    import time as _time

    client = Client(auth=token)
    props = _entries_props()

    _time.sleep(0.35)
    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"text": {"content": "Entries"}}],
        properties=props,  # type: ignore[arg-type]
    )
    # 2025 API: ensure properties on data_source
    sources = db.get("data_sources") or []
    if sources:
        ds_id = sources[0]["id"]
        _time.sleep(0.35)
        client.data_sources.update(ds_id, properties=props)  # type: ignore[arg-type]
    return db["id"]


def setup_reports_database(token: str, parent_page_id: str) -> str:
    """Create the Reports database. Returns database ID."""
    import time as _time

    client = Client(auth=token)
    props = _reports_props()

    _time.sleep(0.35)
    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"text": {"content": "Reports"}}],
        properties=props,  # type: ignore[arg-type]
    )
    sources = db.get("data_sources") or []
    if sources:
        ds_id = sources[0]["id"]
        _time.sleep(0.35)
        client.data_sources.update(ds_id, properties=props)  # type: ignore[arg-type]
    return db["id"]
