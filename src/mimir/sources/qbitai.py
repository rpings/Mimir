"""量子位 RSS source — Chinese AI news."""

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

QBITAI_RSS = "https://www.qbitai.com/feed"

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


async def _get(client: httpx.AsyncClient, url: str) -> str | None:
    for attempt in range(3):
        try:
            resp = await client.get(
                url,
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            if attempt == 2:
                log.warning("量子位 RSS failed: %s", exc)
                return None
            await asyncio.sleep(2 ** attempt)
    return None


def _parse(content: str) -> list[RawEntry]:
    feed = feedparser.parse(content)
    entries: list[RawEntry] = []
    for item in feed.entries:
        title = (item.get("title") or "").strip()
        link = (item.get("link") or "").strip()
        if not title or not link:
            continue
        summary = _strip_html(item.get("summary", "") or "")
        entries.append(RawEntry(
            title=title,
            link=link,
            summary=summary,
            published=_parse_date(item),
            source="qbitai",
            entry_type=EntryType.NEWS,
        ))
    log.info("qbitai: %d entries", len(entries))
    return entries


async def fetch_qbitai(*, client: httpx.AsyncClient) -> list[RawEntry]:
    body = await _get(client, QBITAI_RSS)
    if body is None:
        return []
    return _parse(body)
