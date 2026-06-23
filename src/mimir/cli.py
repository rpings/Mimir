"""CLI entry point for Mimir."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

import httpx

from mimir import config as config_module
from mimir.enrich import Enricher
from mimir.notion import NotionStore
from mimir.sources.arxiv import fetch_arxiv
from mimir.sources.github import fetch_github_trending
from mimir.sources.hackernews import fetch_hackernews
from mimir.sources.qbitai import fetch_qbitai


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _cmd_collect(cfg, *, dry_run: bool = False) -> int:
    print("Mimir collect\n")

    # ── 1. Fetch sources ──
    print("─ 采集 ─")
    t0 = time.monotonic()
    all_entries = []

    async with httpx.AsyncClient() as client:
        tasks = []

        # arXiv
        if cfg.sources.arxiv_categories:
            tasks.append(("arxiv", fetch_arxiv(
                cfg.sources.arxiv_categories,
                max_results=cfg.sources.arxiv_max_results,
                client=client,
            )))

        # GitHub Trending
        if cfg.sources.github_trending:
            tasks.append(("github", fetch_github_trending(
                max_repos=cfg.sources.github_max_repos,
                client=client,
            )))

        # Hacker News
        if cfg.sources.hackernews:
            tasks.append(("hn", fetch_hackernews(
                min_points=cfg.sources.hackernews_min_points,
                client=client,
            )))

        # 量子位
        if cfg.sources.qbitai:
            tasks.append(("qbitai", fetch_qbitai(client=client)))

        for name, coro in tasks:
            try:
                entries = await coro
                print(f"  {name}: {len(entries)} entries")
                all_entries.extend(entries)
            except Exception as exc:
                print(f"  {name}: FAILED — {exc}")

    fetch_time = time.monotonic() - t0
    print(f"  total: {len(all_entries)} entries ({fetch_time:.1f}s)")

    if not all_entries:
        print("\nNo entries collected.")
        return 0

    # ── 2. Dedup ──
    store = NotionStore(cfg.notion.token, cfg.notion.entries_db_id)
    existing = store.load_existing_links()
    new = [e for e in all_entries if e.link not in existing]
    skipped = len(all_entries) - len(new)
    print("\n─ 去重 ─")
    print(f"  existing: {len(existing)}, new: {len(new)}, skipped: {skipped}")

    if not new:
        print("No new entries.")
        return 0

    if dry_run:
        print("\n[dry-run] Would process and insert:")
        for e in new[:10]:
            print(f"  [{e.entry_type.value}] {e.title[:70]}")
        if len(new) > 10:
            print(f"  ... and {len(new) - 10} more")
        return 0

    # ── 3. AI Processing ──
    print("\n─ AI 处理 (DeepSeek) ─")
    t1 = time.monotonic()
    enricher = Enricher(cfg.llm)
    enriched = await enricher.process_all(new)
    print(f"  processed: {len(enriched)} entries ({time.monotonic() - t1:.1f}s)")

    # ── 4. Write to Notion ──
    print("\n─ 写入 Notion ─")
    t2 = time.monotonic()
    created = store.insert_entries(enriched)
    print(f"  created: {created} pages ({time.monotonic() - t2:.1f}s)")

    # ── Summary ──
    print(f"\n{'='*40}")
    print(f"Total: {len(all_entries)} collected, {skipped} skipped, {created} new")
    print(f"Time: fetch {fetch_time:.1f}s + enrich {time.monotonic()-t1:.1f}s")
    return 0


def _cmd_setup(cfg) -> int:
    """Verify config and set up Notion databases."""

    from mimir.notion import (
        NotionStore,
        find_database,
        repair_database,
        setup_entries_database,
        setup_reports_database,
    )

    created_entries = ""
    created_reports = ""

    print("Mimir v2 Setup\n" + "=" * 50)

    # ── 1. LLM ──
    print("\n[LLM]")
    print(f"  Provider: {cfg.llm.provider} / {cfg.llm.model}")
    if cfg.llm.api_key:
        print(f"  API Key:  ****{cfg.llm.api_key[-4:]}")
    else:
        print("  API Key:  MISSING — set LLM_API_KEY in environment")
        return 1

    # ── 2. Notion ──
    print("\n[Notion]")
    if not cfg.notion.token:
        print("  Token: MISSING — set NOTION_TOKEN in environment")
        return 1
    print(f"  Token:    ****{cfg.notion.token[-4:]}")

    # ── 3. Create or verify Entries DB ──
    entries_id = cfg.notion.entries_db_id
    if entries_id:
        try:
            NotionStore(cfg.notion.token, entries_id)._client.databases.retrieve(entries_id)
            repair_database(cfg.notion.token, entries_id)
            print(f"  Entries DB: {entries_id} — exists (repaired)")
        except Exception:
            print(f"  Entries DB: {entries_id} — NOT FOUND, will create new one")
            entries_id = ""
    else:
        print("  Entries DB: not configured, will create new one")

    if not entries_id:
        parent = cfg.notion.parent_page_id
        if not parent:
            print("  ERROR: Set NOTION_PARENT_PAGE_ID (or parent_page_id in mimir.toml)")
            return 1
        # Search for existing DB before creating
        existing = find_database(cfg.notion.token, "Entries")
        if existing:
            entries_id = existing
            print(f"  Entries DB: {entries_id} — found existing")
        else:
            try:
                entries_id = setup_entries_database(cfg.notion.token, parent)
            except Exception as exc:
                print(f"  Entries DB: FAILED — {exc}")
                return 1
        created_entries = entries_id
        print(f"  Entries DB: {entries_id} — {'found' if existing else 'CREATED'}")
    else:
        created_entries = entries_id

    # ── 4. Create or verify Reports DB ──
    reports_id = cfg.notion.reports_db_id
    if reports_id:
        try:
            NotionStore(cfg.notion.token, reports_id)._client.databases.retrieve(reports_id)
            repair_database(cfg.notion.token, reports_id)
            print(f"  Reports DB: {reports_id} — exists (repaired)")
        except Exception:
            print(f"  Reports DB: {reports_id} — NOT FOUND, will create new one")
            reports_id = ""
    else:
        print("  Reports DB: not configured, will create new one")

    if not reports_id:
        parent = cfg.notion.parent_page_id
        if parent:
            existing = find_database(cfg.notion.token, "Reports")
            if existing:
                reports_id = existing
            else:
                try:
                    reports_id = setup_reports_database(cfg.notion.token, parent)
                except Exception as exc:
                    print(f"  Reports DB: FAILED — {exc}")
                    reports_id = ""
            if reports_id:
                created_reports = reports_id
                print(f"  Reports DB: {reports_id} — {'found' if existing else 'CREATED'}")
        else:
            print("  Reports DB: skipped (no parent_page_id)")
    else:
        created_reports = reports_id

    # ── 5. Config instructions ──
    if created_entries or created_reports:
        print(f"\n{'='*50}")
        print("Database IDs — add to .env (local) or GitHub Secrets (CI):")
        if created_entries:
            print(f"  NOTION_ENTRIES_DB_ID={created_entries}")
        if created_reports:
            print(f"  NOTION_REPORTS_DB_ID={created_reports}")

    # ── 6. Manual steps (API can't do) ──
    print(f"\n{'='*50}")
    print("Manual steps (do once in Notion UI):")
    print("  1. Open Entries DB, create 5 views:")
    print("     Gallery(🔥今日新增) — filter: Created is today, Card preview=Page content")
    print("     Table(📄论文) — filter: Type = 📄 论文")
    print("     Table(🛠️项目) — filter: Type = 🛠️ 项目")
    print("     Table(📰新闻) — filter: Type = 📰 新闻")
    print("     Board(📋按主题) — group by Topic")
    print("  2. Grant Notion Integration access to both databases")
    print("     (Settings → Connections → add your integration)")

    print(f"\n{'='*50}")
    print("Setup complete.")
    return 0


def _cmd_report(cfg, period: str = "week") -> int:
    """Generate weekly or monthly report from Notion entries."""
    from mimir.notion import NotionStore
    from mimir.report import generate

    client = NotionStore(cfg.notion.token, cfg.notion.entries_db_id)
    path = generate(cfg, client, period=period)
    print(f"Report: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mimir",
        description="Mimir — personal AI knowledge base with Notion kanban.",
    )
    parser.add_argument("--config", default="mimir.toml", help="config file path")
    parser.add_argument("--verbose", action="store_true", help="debug logging")

    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect", help="collect sources → AI process → write Notion")
    p.add_argument("--dry-run", action="store_true", help="print what would be done, do not write")
    p_report = sub.add_parser("report", help="generate weekly or monthly HTML report")
    p_report.add_argument("--period", choices=["week", "month"], default="week",
                          help="report period (default: week)")
    sub.add_parser("setup", help="verify config and Notion connectivity")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        cfg = config_module.load(args.config)
    except config_module.ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    if args.cmd == "collect":
        return asyncio.run(_cmd_collect(cfg, dry_run=args.dry_run))
    elif args.cmd == "report":
        return _cmd_report(cfg, period=args.period)
    elif args.cmd == "setup":
        return _cmd_setup(cfg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
