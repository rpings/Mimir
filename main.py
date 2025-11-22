# -*- coding: utf-8 -*-
"""Main entry point for Mimir."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from src.collectors.rss_collector import RSSCollector
from src.processors.deduplicator import Deduplicator
from src.processors.keyword_processor import KeywordProcessor
from src.storages.cache_manager import CacheManager
from src.storages.notion_client import NotionStorage
from src.utils.config_loader import ConfigLoader
from src.utils.logger import setup_logger


def main() -> Dict[str, int]:
    """Main execution function.

    Returns:
        Dictionary with statistics: {"created": int, "skipped": int, "errors": int}
    """
    # Setup logging
    logger = setup_logger(__name__, log_file="mimir.log")

    try:
        # Load configuration
        config_loader = ConfigLoader()
        config = config_loader.get_config()
        rules = config_loader.get_classification_rules()
        rss_sources = config_loader.get_rss_sources()

        # Initialize components
        cache_config = config.get("cache", {})
        cache_manager = CacheManager(
            ttl_days=cache_config.get("ttl_days", 30),
        )

        notion_token = os.environ.get("NOTION_TOKEN")
        notion_db_id = os.environ.get("NOTION_DATABASE_ID")

        if not notion_token or not notion_db_id:
            logger.error("NOTION_TOKEN and NOTION_DATABASE_ID must be set")
            sys.exit(1)

        storage = NotionStorage(
            token=notion_token,
            database_id=notion_db_id,
            timezone=config.get("timezone", "Asia/Shanghai"),
        )

        deduplicator = Deduplicator(
            storage=storage,
            cache_manager=cache_manager,
        )

        processor = KeywordProcessor(rules=rules)

        # Statistics
        stats = {"created": 0, "skipped": 0, "errors": 0}

        # Process each RSS feed
        for feed_config in rss_sources:
            feed_name = feed_config.get("name", "Unknown")
            logger.info(f"Processing feed: {feed_name}")

            try:
                collector = RSSCollector(feed_config=feed_config)

                # Collect entries
                entries = collector.collect()

                # Process each entry
                for entry in entries:
                    try:
                        # Check for duplicates
                        if deduplicator.is_duplicate(entry):
                            stats["skipped"] += 1
                            logger.debug(f"Skipped duplicate: {entry.get('title', '')[:50]}")
                            continue

                        # Process entry (classification, priority)
                        processed_entry = processor.process(entry)

                        # Save to Notion
                        if storage.save(processed_entry):
                            stats["created"] += 1
                            deduplicator.mark_as_processed(processed_entry)
                            logger.info(
                                f"Created: {processed_entry.get('title', '')[:50]} "
                                f"[{', '.join(processed_entry.get('topics', []))}]"
                            )
                        else:
                            stats["errors"] += 1

                    except Exception as e:
                        stats["errors"] += 1
                        logger.error(f"Error processing entry: {e}", exc_info=True)

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error processing feed {feed_name}: {e}", exc_info=True)
                # Continue with next feed
                continue

        # Output statistics
        logger.info(f"Processing complete: {json.dumps(stats, ensure_ascii=False)}")
        print(json.dumps(stats, ensure_ascii=False))

        return stats

    except Exception as e:
        logger.exception("Fatal error in main execution")
        sys.exit(1)


if __name__ == "__main__":
    main()

