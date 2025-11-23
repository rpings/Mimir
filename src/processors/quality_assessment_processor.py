# -*- coding: utf-8 -*-
"""Quality assessment processor for evaluating information quality."""

from typing import Any
from urllib.parse import urlparse

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.processing_context import ProcessingContext
from src.utils.logger import get_logger


class QualityAssessmentProcessor(BaseProcessor):
    """Processor for assessing information quality.

    Evaluates:
    - Credibility: Source authority and historical accuracy
    - Completeness: Content completeness and presence of key information
    - Relevance: Relevance to user's focus areas
    - Timeliness: Information freshness
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize quality assessment processor.

        Args:
            config: Configuration dictionary with:
                - enabled: bool (default: True)
                - min_quality_score: float (default: 0.3) - Minimum score to pass
                - source_whitelist: list[str] - Trusted source domains
                - source_blacklist: list[str] - Untrusted source domains
                - min_content_length: int (default: 50) - Minimum content length
        """
        super().__init__(config)
        self.min_quality_score = self.config.get("min_quality_score", 0.3)
        self.source_whitelist = self.config.get("source_whitelist", [])
        self.source_blacklist = self.config.get("source_blacklist", [])
        self.min_content_length = self.config.get("min_content_length", 50)
        self.logger = get_logger(__name__)

    def process(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:
        """Assess information quality.

        Args:
            entry: CollectedEntry or ProcessedEntry to assess.
            context: Optional processing context (not used in this processor).

        Returns:
            ProcessedEntry with quality scores, or None if quality is too low.
        """
        # Convert to ProcessedEntry if needed
        if isinstance(entry, ProcessedEntry):
            processed = entry
        else:
            processed = ProcessedEntry.from_collected(entry)

        # Calculate quality scores
        credibility = self._assess_credibility(processed)
        completeness = self._assess_completeness(processed)
        relevance = self._assess_relevance(processed)
        timeliness = self._assess_timeliness(processed)

        # Calculate overall quality (weighted average)
        overall_quality = (
            credibility * 0.4
            + completeness * 0.3
            + relevance * 0.2
            + timeliness * 0.1
        )

        # Assign quality grade
        if overall_quality >= 0.8:
            quality_grade = "A"
        elif overall_quality >= 0.6:
            quality_grade = "B"
        elif overall_quality >= 0.4:
            quality_grade = "C"
        else:
            quality_grade = "D"

        # Update processed entry
        processed.quality_scores = {
            "credibility": credibility,
            "completeness": completeness,
            "relevance": relevance,
            "timeliness": timeliness,
        }
        processed.quality_grade = quality_grade
        processed.overall_quality = overall_quality

        # Filter out low quality entries
        if overall_quality < self.min_quality_score:
            self.logger.debug(
                f"Filtered low quality entry: {processed.title[:50]} "
                f"(score: {overall_quality:.2f})"
            )
            return None

        return processed

    def _assess_credibility(self, entry: ProcessedEntry) -> float:
        """Assess source credibility.

        Args:
            entry: ProcessedEntry to assess.

        Returns:
            Credibility score (0.0-1.0).
        """
        score = 0.5  # Base score

        # Check source domain
        try:
            domain = urlparse(str(entry.link)).netloc.lower()
            domain = domain.replace("www.", "")

            # Whitelist boost
            if self.source_whitelist:
                for trusted in self.source_whitelist:
                    if trusted.lower() in domain:
                        score = 1.0
                        break

            # Blacklist penalty
            if self.source_blacklist:
                for untrusted in self.source_blacklist:
                    if untrusted.lower() in domain:
                        score = 0.0
                        break

            # Known authoritative domains
            authoritative_domains = [
                "arxiv.org",
                "github.com",
                "openai.com",
                "anthropic.com",
                "deepmind.com",
                "huggingface.co",
                "paperswithcode.com",
            ]
            for auth_domain in authoritative_domains:
                if auth_domain in domain:
                    score = min(score + 0.2, 1.0)
                    break

        except Exception:
            # Invalid URL, lower credibility
            score = 0.3

        return min(max(score, 0.0), 1.0)

    def _assess_completeness(self, entry: ProcessedEntry) -> float:
        """Assess content completeness.

        Args:
            entry: ProcessedEntry to assess.

        Returns:
            Completeness score (0.0-1.0).
        """
        score = 0.5  # Base score

        # Check content length
        content = entry.cleaned_content or entry.summary or ""
        content_length = len(content)

        if content_length < self.min_content_length:
            score = 0.2
        elif content_length < 100:
            score = 0.4
        elif content_length < 200:
            score = 0.6
        elif content_length < 500:
            score = 0.8
        else:
            score = 1.0

        # Check for key elements
        has_title = bool(entry.title and len(entry.title) > 5)
        has_summary = bool(content and len(content) > 20)
        has_link = bool(entry.link)

        element_count = sum([has_title, has_summary, has_link])
        element_score = element_count / 3.0

        # Combine length and element scores
        final_score = (score * 0.6) + (element_score * 0.4)

        return min(max(final_score, 0.0), 1.0)

    def _assess_relevance(self, entry: ProcessedEntry) -> float:
        """Assess content relevance.

        Args:
            entry: ProcessedEntry to assess.

        Returns:
            Relevance score (0.0-1.0).
        """
        # For now, use a base score
        # In the future, this could use user preferences or topic matching
        score = 0.7  # Base relevance score

        # Boost if entry has topics assigned
        if entry.topics:
            score = min(score + 0.2, 1.0)

        return min(max(score, 0.0), 1.0)

    def _assess_timeliness(self, entry: ProcessedEntry) -> float:
        """Assess information timeliness.

        Args:
            entry: ProcessedEntry to assess.

        Returns:
            Timeliness score (0.0-1.0).
        """
        score = 0.5  # Base score

        # Check published date
        if entry.published:
            try:
                from datetime import datetime, timezone

                # Parse ISO format date
                pub_date = datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                age_days = (now - pub_date).days

                # Score based on age
                if age_days < 7:
                    score = 1.0
                elif age_days < 30:
                    score = 0.8
                elif age_days < 90:
                    score = 0.6
                elif age_days < 365:
                    score = 0.4
                else:
                    score = 0.2

            except Exception:
                # Date parsing failed, use base score
                pass

        return min(max(score, 0.0), 1.0)

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "QualityAssessmentProcessor"

