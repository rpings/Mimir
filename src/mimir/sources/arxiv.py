"""arXiv API source — fetch latest papers by category."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from time import mktime

import feedparser
import httpx

from mimir.models import EntryType, RawEntry

log = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    return _WS_RE.sub(" ", _HTML_RE.sub(" ", text)).strip()


def _parse_date(item) -> datetime:
    parsed = getattr(item, "published_parsed", None) or getattr(item, "updated_parsed", None)
    if parsed:
        try:
            return datetime.fromtimestamp(mktime(parsed), tz=UTC)
        except (ValueError, OSError, OverflowError):
            pass
    return datetime.now(UTC)


async def _get(client: httpx.AsyncClient, url: str, **kwargs) -> str | None:
    for attempt in range(3):
        try:
            resp = await client.get(url, timeout=30.0, follow_redirects=True, **kwargs)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            if attempt == 2:
                log.warning("GET %s failed: %s", url[:80], exc)
                return None
            await asyncio.sleep(2 ** attempt)
    return None


def _parse(content: str, source_tag: str) -> list[RawEntry]:
    feed = feedparser.parse(content)
    entries: list[RawEntry] = []
    for item in feed.entries:
        link = (item.get("link") or "").strip()
        title = (item.get("title") or "").strip()
        if not link or not title:
            continue
        summary = _strip_html(item.get("summary", "") or "")
        author = (item.get("author") or "").strip()
        entries.append(RawEntry(
            title=title,
            link=link,
            summary=summary,
            extra={"authors": author},
            published=_parse_date(item),
            source=source_tag,
            entry_type=EntryType.PAPER,
        ))
    log.info("arxiv [%s]: %d entries", source_tag, len(entries))
    return entries


async def fetch_arxiv(
    categories: list[str],
    max_results: int = 50,
    *,
    client: httpx.AsyncClient,
) -> list[RawEntry]:
    query = " OR ".join(f"cat:{c}" for c in categories)
    body = await _get(client, ARXIV_API, params={
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    })
    if body is None:
        return []
    cats_short = ",".join(c.split(".")[-1][:4] for c in categories[:3])
    return _parse(body, f"arxiv:{cats_short}")
