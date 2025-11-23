# -*- coding: utf-8 -*-
"""Main entry point for Mimir."""

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
from src.processors.content_cleaner_processor import ContentCleanerProcessor
from src.processors.quality_assessment_processor import QualityAssessmentProcessor
from src.processors.semantic_deduplicator_processor import SemanticDeduplicatorProcessor
from src.processors.information_verification_processor import InformationVerificationProcessor
from src.processors.knowledge_extraction_processor import KnowledgeExtractionProcessor
from src.processors.priority_ranking_processor import PriorityRankingProcessor
from src.storages.cache_manager import CacheManager
from src.storages.notion_client import NotionStorage
from src.utils.config_loader import ConfigLoader
from src.utils.cost_tracker import BudgetExceededError, CostTracker
from src.utils.logger import setup_logger


def main() -> dict[str, int]:
    """Main execution function.

    Returns:
        Dictionary with statistics: {"created": int, "skipped": int, "errors": int}
    """
    # Setup logging
    setup_logger(__name__, log_file="mimir.log")

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
        
        # Auto-enable LLM if environment variables are set (even if config says disabled)
        # This allows enabling LLM via environment variables without editing config file
        has_llm_env = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_BASE_URL"))
        if has_llm_env and not llm_config.get("enabled", False):
            logger.info("LLM environment variables detected, auto-enabling LLM processing")
            llm_config["enabled"] = True
        
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

        # Create processing context
        from src.processors.processing_context import ProcessingContext
        processing_context = ProcessingContext(
            cache=llm_cache,
            config=config,
        )

        # Create processor pipeline using LangChain
        processors = []

        # 1. Content cleaning processor
        cleaning_config = config.get("processing", {}).get("cleaning", {})
        if cleaning_config.get("enabled", True):
            cleaning_processor = ContentCleanerProcessor(config=cleaning_config)
            processors.append(cleaning_processor)
            logger.debug("Content cleaning processor enabled")

        # 2. Quality assessment processor
        quality_config = config.get("processing", {}).get("quality", {})
        if quality_config.get("enabled", True):
            quality_processor = QualityAssessmentProcessor(config=quality_config)
            processors.append(quality_processor)
            logger.debug("Quality assessment processor enabled")

        # 3. Semantic deduplication processor (optional)
        semantic_dedup_config = config.get("processing", {}).get("semantic_dedup", {})
        if semantic_dedup_config.get("enabled", False):
            semantic_processor = SemanticDeduplicatorProcessor(config=semantic_dedup_config)
            processors.append(semantic_processor)
            logger.debug("Semantic deduplication processor enabled")

        # 4. Information verification processor
        verification_config = config.get("processing", {}).get("verification", {})
        if verification_config.get("enabled", True):
            verification_processor = InformationVerificationProcessor(config=verification_config)
            processors.append(verification_processor)
            logger.debug("Information verification processor enabled")

        # 5. Keyword classification processor
        keyword_processor = KeywordProcessor(rules=rules)
        processors.append(keyword_processor)

        # 6. Knowledge extraction processor
        knowledge_config = config.get("processing", {}).get("knowledge_extraction", {})
        if knowledge_config.get("enabled", True):
            knowledge_processor = KnowledgeExtractionProcessor(config=knowledge_config)
            processors.append(knowledge_processor)
            logger.debug("Knowledge extraction processor enabled")

        # 7. Priority ranking processor
        ranking_config = config.get("processing", {}).get("ranking", {})
        if ranking_config.get("enabled", True):
            ranking_processor = PriorityRankingProcessor(config=ranking_config)
            processors.append(ranking_processor)
            logger.debug("Priority ranking processor enabled")

        # 8. Add LLMProcessor if enabled
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

        pipeline = ProcessorPipeline(processors=processors, context=processing_context)

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
                            logger.debug(f"Skipped duplicate: {entry.title[:50]}")
                            continue

                        # Process entry through pipeline (classification, priority, optional LLM)
                        try:
                            processed_entry = pipeline.process(entry)
                            # Check if entry was skipped (None return)
                            if processed_entry is None:
                                stats["skipped"] += 1
                                logger.debug(f"Skipped by pipeline: {entry.title[:50]}")
                                continue
                        except BudgetExceededError as e:
                            # Budget exceeded, continue with keyword-only processing
                            logger.warning(f"Budget exceeded, using keyword-only processing: {e}")
                            # Re-process with keyword processor only
                            processed_entry = keyword_processor.process(entry, processing_context)
                            if processed_entry is None:
                                stats["skipped"] += 1
                                continue

                        # Save to Notion
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

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error processing feed {feed_name}: {e}", exc_info=True)
                # Continue with next feed
                continue

        # Output statistics
        stats_json = json.dumps(stats, ensure_ascii=False)
        logger.info(f"Processing complete: {stats_json}")

        # Output cost summary if LLM was enabled
        if llm_config.get("enabled", False):
            cost_summary = cost_tracker.get_cost_summary()
            logger.info(
                f"LLM Cost Summary: Daily ${cost_summary['daily_cost']:.4f}/{cost_summary['daily_limit']:.2f}, "
                f"Monthly ${cost_summary['monthly_cost']:.4f}/{cost_summary['monthly_budget']:.2f}"
            )
            stats["llm_daily_cost"] = cost_summary["daily_cost"]
            stats["llm_monthly_cost"] = cost_summary["monthly_cost"]

        print(json.dumps(stats, ensure_ascii=False))

        return stats

    except Exception as e:
        logger.exception("Fatal error in main execution")
        sys.exit(1)


if __name__ == "__main__":
    main()

