"""End-to-end test: collect → enrich → write → verify. Requires NOTION_TOKEN, NOTION_ENTRIES_DB_ID, LLM_API_KEY."""

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    not (os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_ENTRIES_DB_ID") and os.environ.get("LLM_API_KEY")),
    reason="Requires NOTION_TOKEN, NOTION_ENTRIES_DB_ID, LLM_API_KEY",
)

COMMON_FIELDS = ["Name", "Type", "Topic", "Link", "Status", "Priority"]
PAPER_FIELDS = COMMON_FIELDS + ["Overview", "Innovation", "Significance", "Authors", "Venue"]
REPO_FIELDS = COMMON_FIELDS + ["UseCase", "Stars"]
NEWS_FIELDS = COMMON_FIELDS + ["KeyPoint", "Verification"]


def _get_val(props, name):
    pv = props.get(name, {})
    t = pv.get("type", "")
    if t == "title":
        return (pv.get("title", [{}])[0].get("plain_text", "") or "")
    if t == "rich_text":
        return (pv.get("rich_text", [{}])[0].get("plain_text", "") or "")
    if t in ("select", "status"):
        s = pv.get("select") or pv.get("status")
        return s["name"] if s else ""
    if t == "url":
        return pv.get("url", "") or ""
    if t == "number":
        return str(pv.get("number") or 0)
    return ""


@pytest.mark.asyncio
async def test_end_to_end():
    from notion_client import Client

    from mimir.config import load
    from mimir.enrich import Enricher
    from mimir.notion import NotionStore
    from mimir.sources.arxiv import fetch_arxiv
    from mimir.sources.github import fetch_github_trending
    from mimir.sources.hackernews import fetch_hackernews
    from mimir.sources.qbitai import fetch_qbitai

    cfg = load("mimir.toml")

    # 1. Fetch 3 per source
    async with httpx.AsyncClient() as client:
        papers = (await fetch_arxiv(["cs.AI", "cs.CL"], max_results=3, client=client))[:3]
        try:
            repos = (await fetch_github_trending(max_repos=3, client=client))[:3]
        except Exception:
            repos = []
        hns = (await fetch_hackernews(min_points=50, client=client))[:3]
        qbs = (await fetch_qbitai(client=client))[:3]

    entries = papers + repos + hns + qbs
    assert len(entries) >= 5, f"Too few entries: {len(entries)}"

    # 2. Enrich
    enricher = Enricher(cfg.llm)
    enriched = await enricher.process_all(entries, concurrency=2)
    assert len(enriched) == len(entries)

    # 3. Verify enrichment quality (before Notion write)
    for entry in enriched:
        assert entry.topic, f"Empty topic for {entry.title[:30]}"
        assert entry.topic in (
            "ai_agent","rag","inference","multimodal","training",
            "safety","infra","ai_coding","open_models","industry"
        ), f"Invalid topic: {entry.topic}"
        if entry.entry_type.value == "paper":
            assert entry.overview, f"Paper without overview: {entry.title[:30]}"
            assert entry.innovation, f"Paper without innovation: {entry.title[:30]}"
        elif entry.entry_type.value == "repo":
            assert entry.use_case, f"Repo without use_case: {entry.title[:30]}"
        elif entry.entry_type.value == "news":
            assert entry.key_point, f"News without key_point: {entry.title[:30]}"
    print(f"✅ All {len(enriched)} entries enriched correctly")

    # 4. Write to Notion (best effort — may dedup)
    store = NotionStore(cfg.notion.token, cfg.notion.entries_db_id)
    created = store.insert_entries(enriched)
    print(f"Notion write: {created} new, {len(enriched) - created} skipped (dedup)")

    # 4. If new entries were written, read back and verify fields
    if created >= 1:
        c = Client(auth=cfg.notion.token)
        db = c.databases.retrieve(cfg.notion.entries_db_id)
        ds_id = db["data_sources"][0]["id"]
        recent = c.data_sources.query(ds_id, page_size=50)
        written_links = {entry.link: entry for entry in enriched}
        verified = 0

        for page in recent.get("results", []):
            props = page["properties"]
            link = _get_val(props, "Link")
            if link not in written_links:
                continue
            entry = written_links.pop(link)
            verified += 1
            name = _get_val(props, "Name")

            if entry.entry_type.value == "paper":
                fields = PAPER_FIELDS
            elif entry.entry_type.value == "repo":
                fields = REPO_FIELDS
            else:
                fields = NEWS_FIELDS

            for field in fields:
                val = _get_val(props, field)
                assert val, f"[{name}] {field} is empty"
                print(f"  ✅ [{name[:30]}] {field}: {val[:50]}")

        assert verified >= 1, "No entries found in Notion"
        print(f"\n✅ {verified} entries verified in Notion")
