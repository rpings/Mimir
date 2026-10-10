"""GitHub Trending source — scrape trending repositories page."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from mimir.models import EntryType, RawEntry

log = logging.getLogger(__name__)

TRENDING_URL = "https://github.com/trending"


async def _get(client: httpx.AsyncClient, url: str) -> str | None:
    for attempt in range(3):
        try:
            resp = await client.get(
                url,
                timeout=30.0,
                follow_redirects=True,
                headers={"Accept": "text/html"},
            )
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            if attempt == 2:
                log.warning("GitHub Trending fetch failed: %s", exc)
                return None
            await asyncio.sleep(2 ** attempt)
    return None


def _parse(html: str, limit: int) -> list[RawEntry]:
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now(UTC)
    entries: list[RawEntry] = []
    for article in soup.select("article.Box-row"):
        heading = article.select_one("h2 a")
        if not heading:
            continue
        href = (heading.get("href") or "").strip()
        if not href:
            continue
        full_name = href.lstrip("/")
        link = f"https://github.com{href}"
        desc_el = article.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else ""
        # Total stars, from the stargazers link. The row's right-hand span reads
        # "N stars this week", which is a weekly gain — storing that under a field
        # every reader takes for a total made the reports claim e.g. 2.7k stars
        # for a repo with 400k.
        stars = 0
        stars_el = article.select_one('a[href$="/stargazers"]')
        if stars_el:
            m = re.search(r"([\d,]+)", stars_el.get_text(strip=True))
            if m:
                stars = int(m.group(1).replace(",", ""))
        entries.append(RawEntry(
            title=full_name,
            link=link,
            summary=description,
            extra={"stars": stars},
            published=now,
            source="github_trending",
            entry_type=EntryType.REPO,
        ))
        if len(entries) >= limit:
            break
    log.info("github trending: %d entries", len(entries))
    return entries


async def fetch_github_trending(
    max_repos: int = 25,
    *,
    client: httpx.AsyncClient,
) -> list[RawEntry]:
    url = f"{TRENDING_URL}?since=weekly&spoken_language_code=en"
    html = await _get(client, url)
    if html is None:
        return []
    return _parse(html, max_repos)
