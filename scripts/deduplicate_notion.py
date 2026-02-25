# -*- coding: utf-8 -*-
"""One-time script to remove duplicate pages from the Notion database.

Pages are grouped by normalized Link URL. For each group with more than one page,
the oldest (by created_time) is kept and the rest are archived (moved to Trash).

Run once to clean historical data. Ensure only one process runs this script
at a time to avoid races. Requires NOTION_TOKEN and NOTION_DATABASE_ID in
environment (or .env). Uses configs/config.yml for field names (link property).

Usage:
    From project root with venv activated:
    python scripts/deduplicate_notion.py

    Optional: --dry-run to only report what would be archived (no changes).
    Optional: --verify-only to only test connection and env, then exit (0=ok, 1=fail).
"""

import os
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Allow importing from src when run as script
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


def _load_dotenv() -> None:
    """Load .env from project root so NOTION_TOKEN and NOTION_DATABASE_ID are set."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_project_root, ".env"))
        return
    except ImportError:
        pass
    # Fallback: read .env manually (no python-dotenv dependency)
    env_path = os.path.join(_project_root, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and value and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

# Imports after _load_dotenv so .env is loaded before config/logger use env
from notion_client import Client  # noqa: E402

from src.storages.notion_client import _normalize_link  # noqa: E402
from src.utils.config_loader import ConfigLoader  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def _normalize_database_id(value: str) -> str:
    """Extract Notion database ID (32 hex chars, optional hyphens) from env value.

    If value is a URL (e.g. from copying the browser link), extract the id segment.
    Otherwise return value with hyphens stripped (API accepts both formats).

    Args:
        value: NOTION_DATABASE_ID from env (raw id or full Notion URL).

    Returns:
        Database ID safe for API path (no spaces, no URL parts).
    """
    s = (value or "").strip()
    if not s:
        return s
    # If it looks like a URL, take the last path segment before query/fragment
    if "://" in s or s.startswith("www."):
        # e.g. https://www.notion.so/workspace/abc123...?v=...
        parts = re.split(r"[?#]", s)[0].rstrip("/").split("/")
        for seg in reversed(parts):
            # Notion id: 32 hex chars, optionally with 4 hyphens
            clean = seg.replace("-", "")
            if len(clean) == 32 and re.match(r"^[0-9a-fA-F]+$", clean):
                return clean
        # Fallback: use last segment and strip to hex
        if parts:
            clean = re.sub(r"[^0-9a-fA-F]", "", parts[-1])
            if len(clean) == 32:
                return clean
    # Already an id: strip hyphens and any whitespace
    clean = re.sub(r"[^0-9a-fA-F]", "", s)
    return clean if len(clean) == 32 else s.replace("-", "").strip()


def _get_link_from_page(page: dict, link_prop_name: str) -> str | None:
    """Extract URL from a Notion page's link property."""
    props = page.get("properties", {})
    link_obj = props.get(link_prop_name)
    if not link_obj:
        return None
    url = link_obj.get("url")
    if url and isinstance(url, str):
        return url
    return None


def _get_data_source_id(client: Client, database_id: str) -> str | None:
    """Get first data source ID from database (API 2025-09-03)."""
    try:
        resp = client.databases.retrieve(database_id)
        sources = resp.get("data_sources") or []
        if not sources:
            logger.error("Database has no data_sources (2025 API)")
            return None
        return sources[0].get("id")
    except Exception as e:
        logger.error(f"Failed to get data_source_id: {e}")
        return None


def _verify_connection(client: Client, database_id: str) -> bool:
    """Test Notion API connection and database access (API 2025-09-03).

    Retrieves database to get data_source_id, then runs one query with page_size=1.

    Args:
        client: Notion client with auth set.
        database_id: Database ID (32-char hex or UUID with hyphens).

    Returns:
        True if query succeeded, False otherwise (caller should log and exit).
    """
    ds_id = _get_data_source_id(client, database_id)
    if not ds_id:
        return False
    try:
        response = client.data_sources.query(ds_id, page_size=1)
        if response is None:
            logger.error("Verify: empty response from Notion API")
            return False
        logger.info("Verify: connection and database access OK")
        return True
    except Exception as e:
        logger.error(f"Verify: connection failed: {e}")
        return False


def run(dry_run: bool = False, verify_after: bool = True) -> dict[str, int]:
    """Scan Notion database, group pages by link, archive duplicate pages.

    Args:
        dry_run: If True, only log what would be done; do not archive.
        verify_after: If True and not dry_run, re-scan after archiving to verify
            no duplicate groups remain; set summary["verify_failed"] on failure.

    Returns:
        Summary dict with keys: total_pages, unique_links, duplicate_groups,
        pages_archived, errors, and optionally verify_failed.
    """
    token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")
    if not token or not database_id:
        logger.error("NOTION_TOKEN and NOTION_DATABASE_ID must be set (check .env)")
        sys.exit(1)

    db_id = _normalize_database_id(database_id)
    if len(db_id) != 32:
        logger.error(
            "NOTION_DATABASE_ID must be a 32-character hex id (or a Notion database URL)"
        )
        sys.exit(1)

    config_loader = ConfigLoader()
    config = config_loader.get_config()
    notion_config = config.get("notion", {})
    field_names = notion_config.get("field_names") or {}
    link_prop = field_names.get("link", "Link")

    client = Client(auth=token)

    # Startup verification: test connection and database access (2025 API: data_sources)
    if not _verify_connection(client, db_id):
        sys.exit(1)

    ds_id = _get_data_source_id(client, db_id)
    if not ds_id:
        logger.error("Could not resolve data_source_id from database")
        sys.exit(1)

    # Paginate and collect (page_id, created_time, normalized_link)
    link_to_pages: dict[str, list[dict]] = defaultdict(list)
    total_pages = 0
    cursor = None

    logger.info("Scanning Notion database for pages...")
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        try:
            response = client.data_sources.query(ds_id, **body)
        except Exception as e:
            logger.error(f"Failed to query database: {e}")
            return {
                "total_pages": total_pages,
                "unique_links": 0,
                "duplicate_groups": 0,
                "pages_archived": 0,
                "errors": 1,
            }
        results = response.get("results", [])
        for page in results:
            total_pages += 1
            page_id = page.get("id")
            created = page.get("created_time") or ""
            link = _get_link_from_page(page, link_prop)
            if not link:
                continue
            norm = _normalize_link(link)
            if not norm:
                continue
            link_to_pages[norm].append({"id": page_id, "created_time": created})
        logger.info(f"Scanned {total_pages} pages...")
        cursor = response.get("next_cursor")
        if not cursor:
            break

    unique_links = len(link_to_pages)
    duplicate_groups = sum(1 for pages in link_to_pages.values() if len(pages) > 1)
    to_archive_list: list[tuple[str, str]] = []  # (page_id, norm_link)
    for norm_link, pages in link_to_pages.items():
        if len(pages) <= 1:
            continue
        pages.sort(key=lambda p: p["created_time"])
        for p in pages[1:]:
            to_archive_list.append((p["id"], norm_link))

    pages_archived = 0
    errors = 0
    # Notion ~3 req/s; stagger starts so we run up to 3 concurrent, ~3 req/s
    rate_lock = threading.Lock()
    next_start: list[float] = [0.0]

    def archive_one(pid: str, norm_link: str) -> tuple[bool, bool]:
        """Archive one page. Returns (success, already_archived)."""
        if dry_run:
            return (True, False)
        with rate_lock:
            now = time.monotonic()
            t = max(now, next_start[0])
            next_start[0] = t + 0.34
        if t > now:
            time.sleep(t - now)
        try:
            client.request(
                path=f"pages/{pid}",
                method="PATCH",
                body={"archived": True},
            )
            return (True, False)
        except Exception as e:
            err_msg = str(e).lower()
            if "archived" in err_msg and "unarchive" in err_msg:
                return (True, True)
            raise

    max_workers = 3
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(archive_one, pid, norm_link): (pid, norm_link)
            for pid, norm_link in to_archive_list
        }
        for fut in as_completed(futures):
            pid, norm_link = futures[fut]
            try:
                ok, already = fut.result()
                pages_archived += 1
                if not already:
                    logger.info(f"{'[DRY-RUN] Would archive' if dry_run else 'Archived'} page {pid} (link: {norm_link[:60]}...)")
            except Exception as e:
                errors += 1
                logger.error(f"Failed to archive page {pid}: {e}")

    # Post-run verification: after real archiving, re-scan and ensure no duplicates remain
    verify_failed = False
    if verify_after and not dry_run and pages_archived > 0:
        logger.info("Verifying: re-scanning database to confirm no duplicate groups...")
        link_to_pages_after: dict[str, list[dict]] = defaultdict(list)
        cursor = None
        try:
            while True:
                body = {"page_size": 100}
                if cursor:
                    body["start_cursor"] = cursor
                response = client.data_sources.query(ds_id, **body)
                for page in response.get("results", []):
                    link = _get_link_from_page(page, link_prop)
                    if not link:
                        continue
                    norm = _normalize_link(link)
                    if norm:
                        link_to_pages_after[norm].append(page.get("id"))
                cursor = response.get("next_cursor")
                if not cursor:
                    break
            remaining = sum(1 for pages in link_to_pages_after.values() if len(pages) > 1)
            if remaining > 0:
                logger.error(
                    f"Verify failed: {remaining} link(s) still have more than one page"
                )
                verify_failed = True
            else:
                logger.info("Verify OK: no duplicate groups remain.")
        except Exception as e:
            logger.error(f"Verify failed during re-scan: {e}")
            verify_failed = True

    summary = {
        "total_pages": total_pages,
        "unique_links": unique_links,
        "duplicate_groups": duplicate_groups,
        "pages_archived": pages_archived,
        "errors": errors,
        "verify_failed": verify_failed,
    }
    logger.info(
        f"Done. total_pages={total_pages} unique_links={unique_links} "
        f"duplicate_groups={duplicate_groups} pages_archived={pages_archived} errors={errors}"
    )
    if dry_run:
        logger.info("Dry run: no pages were actually archived.")
    return summary


def main() -> None:
    """Entry point: parse args and run deduplication or verification."""
    if "--verify-only" in sys.argv:
        # Only test env and connection; exit 0 if OK, 1 if fail
        token = os.environ.get("NOTION_TOKEN")
        database_id = os.environ.get("NOTION_DATABASE_ID")
        if not token or not database_id:
            logger.error("NOTION_TOKEN and NOTION_DATABASE_ID must be set (check .env)")
            sys.exit(1)
        db_id = _normalize_database_id(database_id)
        if len(db_id) != 32:
            logger.error("NOTION_DATABASE_ID must be a 32-char hex id or Notion database URL")
            sys.exit(1)
        client = Client(auth=token)
        if _verify_connection(client, db_id):
            logger.info("Verify-only: all checks passed.")
            sys.exit(0)
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("Running in dry-run mode (no changes will be made).")
    summary = run(dry_run=dry_run, verify_after=True)
    print(
        f"total_pages={summary['total_pages']} unique_links={summary['unique_links']} "
        f"duplicate_groups={summary['duplicate_groups']} pages_archived={summary['pages_archived']} "
        f"errors={summary['errors']}"
    )
    # Exit non-zero if any errors or post-run verification failed
    if summary.get("verify_failed") or summary["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
