"""Hacker News API source — fetch top stories with AI-related title filtering."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from mimir.models import EntryType, RawEntry

log = logging.getLogger(__name__)

HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"

# Keywords for AI-related filtering
_AI_KEYWORDS = [
    "ai ", "llm", "gpt", "agent", "model", "openai", "anthropic", "deepseek",
    "rag", "vector", "embedding", "transformer", "diffusion", "open source",
    "benchmark", "fine-tun", "gpu", "nvidia", "chatgpt", "claude", "gemini",
    "llama", "qwen", "mistral", "cuda", "inference", "training", "dataset",
    "machine learning", "deep learning", "neural", "token", "prompt",
    "embedding", "rerank", "langchain", "vllm", "sora", "stable diffusion",
]


async def _get_json(client: httpx.AsyncClient, url: str) -> dict | list | None:
    for attempt in range(3):
        try:
            resp = await client.get(url, timeout=15.0, follow_redirects=True)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            if attempt == 2:
                log.warning("HN API failed: %s", exc)
                return None
            await asyncio.sleep(2 ** attempt)
    return None


def _is_ai_related(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in _AI_KEYWORDS)


async def fetch_hackernews(
    min_points: int = 50,
    *,
    client: httpx.AsyncClient,
) -> list[RawEntry]:
    story_ids = await _get_json(client, HN_TOP_STORIES)
    if not story_ids or not isinstance(story_ids, list):
        return []

    # Fetch top 200 stories in parallel
    ids_to_check = story_ids[:200]
    tasks = [_get_json(client, HN_ITEM.format(sid)) for sid in ids_to_check]
    results = await asyncio.gather(*tasks)

    entries: list[RawEntry] = []
    for item in results:
        if not item or not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title or not _is_ai_related(title):
            continue
        score = item.get("score", 0) or 0
        if score < min_points:
            continue
        url = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}"
        entries.append(RawEntry(
            title=title,
            link=url,
            summary=f"HN {score} points | {item.get('descendants', 0)} comments",
            published=datetime.fromtimestamp(item.get("time", 0), tz=UTC),
            source="hackernews",
            entry_type=EntryType.NEWS,
        ))
    log.info("hackernews: %d AI-related entries (min %d pts)", len(entries), min_points)
    return entries
