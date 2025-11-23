# -*- coding: utf-8 -*-
"""Async main entry point for Mimir (Phase 3 - Performance Optimization)."""

import asyncio
import json
import os
import sys
from pathlib import Path

from loguru import logger

from src.collectors.rss_collector import RSSCollector
from src.processors.deduplicator import Deduplicator
from src.processors.keyword_processor import KeywordProcessor
from src.processors.llm_processor import LLMProcessor
from src.processors.processor_pipeline import ProcessorPipeline
from src.storages.cache_manager import CacheManager
from src.storages.notion_client import NotionStorage
from src.utils.config_loader import ConfigLoader
from src.utils.cost_tracker import BudgetExceededError, CostTracker
from src.utils.logger import setup_logger


async def process_feed_async(
    feed_config: dict[str, str],
    pipeline: ProcessorPipeline,
    deduplicator: Deduplicator,
    storage: NotionStorage,
    keyword_processor: KeywordProcessor,
) -> dict[str, int]:
    """Process a single feed asynchronously.

    Args:
        feed_config: Feed configuration dictionary.
        pipeline: Processor pipeline instance.
        deduplicator: Deduplicator instance.
        storage: Storage instance.
        keyword_processor: Keyword processor for fallback.

    Returns:
        Dictionary with statistics for this feed.
    """
    stats = {"created": 0, "skipped": 0, "errors": 0}
    feed_name = feed_config.get("name", "Unknown")
    logger.info(f"Processing feed: {feed_name}")

    try:
        collector = RSSCollector(feed_config=feed_config)

        # Collect entries asynchronously
        entries = await collector.acollect()

        # Process entries concurrently (with limit to avoid overwhelming)
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent entries per feed

        async def process_entry(entry):
            """Process a single entry."""
            async with semaphore:
                try:
                    # Check for duplicates
                    if deduplicator.is_duplicate(entry):
                        stats["skipped"] += 1
                        logger.debug(f"Skipped duplicate: {entry.title[:50]}")
                        return

                    # Process entry through pipeline (async)
                    try:
                        processed_entry = await pipeline.aprocess(entry)
                    except BudgetExceededError as e:
                        # Budget exceeded, continue with keyword-only processing
                        logger.warning(f"Budget exceeded, using keyword-only processing: {e}")
                        # Re-process with keyword processor only (sync, but fast)
                        processed_entry = keyword_processor.process(entry)

                    # Save to Notion (sync, but we're in async context)
                    if storage.save(processed_entry):
                        stats["created"] += 1
                        deduplicator.mark_as_processed(processed_entry)
                        logger.info(
                            f"Created: {processed_entry.title[:50]} "
                            f"[{', '.join(processed_entry.topics)}]"
                        )
                    else:
                        stats["errors"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    logger.error(f"Error processing entry: {e}", exc_info=True)

        # Process all entries concurrently
        await asyncio.gather(*[process_entry(entry) for entry in entries], return_exceptions=True)

    except Exception as e:
        stats["errors"] += 1
        logger.error(f"Error processing feed {feed_name}: {e}", exc_info=True)

    return stats


async def main_async() -> dict[str, int]:
    """Async main execution function.

    Returns:
        Dictionary with statistics: {"created": int, "skipped": int, "errors": int}
    """
    # Setup logging
    setup_logger(__name__, log_file="mimir_async.log")

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

        notion_config = config.get("notion", {})
        field_names = notion_config.get("field_names")
        storage = NotionStorage(
            token=notion_token,
            database_id=notion_db_id,
            timezone=config.get("timezone", "Asia/Shanghai"),
            field_names=field_names,
        )

        deduplicator = Deduplicator(
            storage=storage,
            cache_manager=cache_manager,
        )

        # Initialize cost tracker for LLM budget management
        llm_config = config.get("llm", {})
        cost_tracker = CostTracker(
            daily_limit=llm_config.get("daily_limit", 5.0),
            monthly_budget=llm_config.get("monthly_budget", 50.0),
        )

        # Initialize LLM cache
        llm_cache_config = llm_config.get("cache", {})
        from src.storages.llm_cache import LLMCache
        llm_cache = LLMCache(
            cache_dir=llm_cache_config.get("path"),
            ttl_days=llm_cache_config.get("ttl_days", 30),
        )

        # Create processor pipeline using LangChain
        keyword_processor = KeywordProcessor(rules=rules)
        processors = [keyword_processor]

        # Add LLMProcessor if enabled
        if llm_config.get("enabled", False):
            try:
                llm_processor = LLMProcessor(
                    config=llm_config,
                    cost_tracker=cost_tracker,
                    llm_cache=llm_cache,
                )
                processors.append(llm_processor)
                logger.info("LLM processing enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize LLMProcessor: {e}, continuing without LLM")
        else:
            logger.debug("LLM processing disabled")

        pipeline = ProcessorPipeline(processors=processors)

        # Statistics
        total_stats = {"created": 0, "skipped": 0, "errors": 0}

        # Process all feeds concurrently
        feed_semaphore = asyncio.Semaphore(10)  # Max 10 concurrent feeds

        async def process_feed_with_limit(feed_config):
            """Process feed with concurrency limit."""
            async with feed_semaphore:
                return await process_feed_async(
                    feed_config, pipeline, deduplicator, storage, keyword_processor
                )

        # Process all feeds concurrently
        feed_results = await asyncio.gather(
            *[process_feed_with_limit(feed_config) for feed_config in rss_sources],
            return_exceptions=True,
        )

        # Aggregate statistics
        for result in feed_results:
            if isinstance(result, dict):
                total_stats["created"] += result.get("created", 0)
                total_stats["skipped"] += result.get("skipped", 0)
                total_stats["errors"] += result.get("errors", 0)
            elif isinstance(result, Exception):
                total_stats["errors"] += 1
                logger.error(f"Feed processing exception: {result}", exc_info=True)

        # Output statistics
        stats_json = json.dumps(total_stats, ensure_ascii=False)
        logger.info(f"Processing complete: {stats_json}")

        # Output cost summary if LLM was enabled
        if llm_config.get("enabled", False):
            cost_summary = cost_tracker.get_cost_summary()
            logger.info(
                f"LLM Cost Summary: Daily ${cost_summary['daily_cost']:.4f}/{cost_summary['daily_limit']:.2f}, "
                f"Monthly ${cost_summary['monthly_cost']:.4f}/{cost_summary['monthly_budget']:.2f}"
            )
            total_stats["llm_daily_cost"] = cost_summary["daily_cost"]
            total_stats["llm_monthly_cost"] = cost_summary["monthly_cost"]

        print(json.dumps(total_stats, ensure_ascii=False))

        return total_stats

    except Exception as e:
        logger.exception("Fatal error in async main execution")
        sys.exit(1)


def main() -> dict[str, int]:
    """Main entry point (runs async main)."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    main()

