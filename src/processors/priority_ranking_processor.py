# -*- coding: utf-8 -*-
"""Priority ranking processor for intelligent content prioritization."""

from typing import Any
from datetime import datetime, timezone

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.processing_context import ProcessingContext
from src.utils.logger import get_logger


class PriorityRankingProcessor(BaseProcessor):
    """Processor for intelligent priority ranking.

    Ranks content based on:
    - Quality: Overall quality score
    - Relevance: Relevance to user's focus areas
    - Timeliness: Information freshness
    - Source: Source authority
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize priority ranking processor.

        Args:
            config: Configuration dictionary with:
                - enabled: bool (default: True)
                - weights: dict with quality, relevance, timeliness, source weights
        """
        super().__init__(config)
        weights = self.config.get("weights", {})
        self.weight_quality = weights.get("quality", 0.4)
        self.weight_relevance = weights.get("relevance", 0.3)
        self.weight_timeliness = weights.get("timeliness", 0.2)
        self.weight_source = weights.get("source", 0.1)
        self.logger = get_logger(__name__)

    def process(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:
        """Rank content priority.

        Args:
            entry: CollectedEntry or ProcessedEntry to rank.
            context: Optional processing context.

        Returns:
            ProcessedEntry with priority ranking, or None if ranking fails.
        """
        # Convert to ProcessedEntry if needed
        if isinstance(entry, ProcessedEntry):
            processed = entry
        else:
            processed = ProcessedEntry.from_collected(entry)

        # Calculate priority score
        priority_score = self._calculate_priority_score(processed)

        # Determine final priority
        if priority_score >= 0.7:
            final_priority = "High"
        elif priority_score >= 0.4:
            final_priority = "Medium"
        else:
            final_priority = "Low"

        # Generate ranking reason
        ranking_reason = self._generate_ranking_reason(processed, priority_score)

        # Update processed entry
        processed.final_priority = final_priority
        processed.priority_score = priority_score
        processed.ranking_reason = ranking_reason

        # Also update the base priority field for backward compatibility
        if not processed.priority or processed.priority == "Low":
            processed.priority = final_priority

        return processed

    def _calculate_priority_score(self, entry: ProcessedEntry) -> float:
        """Calculate priority score.

        Args:
            entry: ProcessedEntry to score.

        Returns:
            Priority score (0.0-1.0).
        """
        score = 0.0

        # Quality component
        quality_score = entry.overall_quality if entry.overall_quality else 0.5
        score += quality_score * self.weight_quality

        # Relevance component (use topics as proxy)
        relevance_score = 0.5
        if entry.topics:
            relevance_score = min(0.5 + len(entry.topics) * 0.15, 1.0)
        score += relevance_score * self.weight_relevance

        # Timeliness component
        timeliness_score = self._calculate_timeliness(entry)
        score += timeliness_score * self.weight_timeliness

        # Source component (use verification score as proxy)
        source_score = entry.verification_score if entry.verification_score else 0.5
        score += source_score * self.weight_source

        return min(max(score, 0.0), 1.0)

    def _calculate_timeliness(self, entry: ProcessedEntry) -> float:
        """Calculate timeliness score.

        Args:
            entry: ProcessedEntry to score.

        Returns:
            Timeliness score (0.0-1.0).
        """
        if not entry.published:
            return 0.5

        try:
            # Parse ISO format date
            pub_date = datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_days = (now - pub_date).days

            # Score based on age (newer is better)
            if age_days < 1:
                return 1.0
            elif age_days < 7:
                return 0.9
            elif age_days < 30:
                return 0.7
            elif age_days < 90:
                return 0.5
            elif age_days < 365:
                return 0.3
            else:
                return 0.1

        except Exception:
            return 0.5

    def _generate_ranking_reason(self, entry: ProcessedEntry, score: float) -> str:
        """Generate ranking reason.

        Args:
            entry: ProcessedEntry.
            score: Priority score.

        Returns:
            Ranking reason string.
        """
        reasons: list[str] = []

        if entry.overall_quality and entry.overall_quality >= 0.7:
            reasons.append("high quality")
        if entry.topics and len(entry.topics) >= 2:
            reasons.append("highly relevant")
        if entry.verification_status == "verified":
            reasons.append("verified source")
        if entry.published:
            try:
                pub_date = datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                age_days = (now - pub_date).days
                if age_days < 7:
                    reasons.append("recent")
            except Exception:
                pass

        if reasons:
            return f"Ranked {entry.final_priority} due to: {', '.join(reasons)}"
        else:
            return f"Ranked {entry.final_priority} (score: {score:.2f})"

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "PriorityRankingProcessor"

