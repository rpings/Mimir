# -*- coding: utf-8 -*-
"""Information verification processor for fact-checking and source validation."""

from typing import Any
from urllib.parse import urlparse

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.processing_context import ProcessingContext
from src.utils.logger import get_logger


class InformationVerificationProcessor(BaseProcessor):
    """Processor for verifying information authenticity.

    Verifies:
    - Source validation: Domain checks, SSL, historical records
    - Cross-verification: Compare with other sources
    - Fact-checking: Use LLM to assess factual accuracy (optional)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize information verification processor.

        Args:
            config: Configuration dictionary with:
                - enabled: bool (default: True)
                - verify_source: bool (default: True) - Verify source domain
                - cross_verify: bool (default: False) - Cross-verify with other sources
                - fact_check_llm: bool (default: False) - Use LLM for fact-checking
                - source_whitelist: list[str] - Trusted source domains
        """
        super().__init__(config)
        self.verify_source = self.config.get("verify_source", True)
        self.cross_verify = self.config.get("cross_verify", False)
        self.fact_check_llm = self.config.get("fact_check_llm", False)
        self.source_whitelist = self.config.get("source_whitelist", [])
        self.logger = get_logger(__name__)

    def process(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:
        """Verify information authenticity.

        Args:
            entry: CollectedEntry or ProcessedEntry to verify.
            context: Optional processing context.

        Returns:
            ProcessedEntry with verification status, or None if verification fails.
        """
        # Convert to ProcessedEntry if needed
        if isinstance(entry, ProcessedEntry):
            processed = entry
        else:
            processed = ProcessedEntry.from_collected(entry)

        verification_score = 0.5  # Base score
        warnings: list[str] = []

        # Source verification
        if self.verify_source:
            source_score, source_warnings = self._verify_source(processed)
            verification_score = (verification_score * 0.6) + (source_score * 0.4)
            warnings.extend(source_warnings)

        # Cross-verification (simplified: in production, compare with database)
        if self.cross_verify:
            cross_score = self._cross_verify(processed, context)
            verification_score = (verification_score * 0.7) + (cross_score * 0.3)

        # Fact-checking with LLM (optional, expensive)
        if self.fact_check_llm and context:
            fact_score = self._fact_check_llm(processed, context)
            if fact_score is not None:
                verification_score = (verification_score * 0.8) + (fact_score * 0.2)

        # Determine verification status
        if verification_score >= 0.7:
            verification_status = "verified"
        elif verification_score >= 0.4:
            verification_status = "unverified"
        else:
            verification_status = "suspicious"

        # Update processed entry
        processed.verification_status = verification_status
        processed.verification_score = verification_score
        processed.verification_warnings = warnings

        # Filter suspicious content if score is too low
        if verification_score < 0.3:
            self.logger.debug(
                f"Filtered suspicious content: {processed.title[:50]} "
                f"(score: {verification_score:.2f})"
            )
            return None

        return processed

    def _verify_source(self, entry: ProcessedEntry) -> tuple[float, list[str]]:
        """Verify source domain and URL.

        Args:
            entry: ProcessedEntry to verify.

        Returns:
            Tuple of (score, warnings).
        """
        score = 0.5
        warnings: list[str] = []

        try:
            domain = urlparse(str(entry.link)).netloc.lower()
            domain = domain.replace("www.", "")

            # Check whitelist
            if self.source_whitelist:
                for trusted in self.source_whitelist:
                    if trusted.lower() in domain:
                        score = 1.0
                        return score, warnings

            # Check for suspicious patterns
            suspicious_patterns = [".tk", ".ml", ".ga", ".cf", ".gq", "bit.ly", "tinyurl"]
            for pattern in suspicious_patterns:
                if pattern in domain:
                    score = 0.2
                    warnings.append(f"Suspicious domain pattern: {pattern}")
                    break

            # Check for HTTPS
            if str(entry.link).startswith("https://"):
                score = min(score + 0.2, 1.0)
            else:
                score = max(score - 0.2, 0.0)
                warnings.append("Non-HTTPS URL")

        except Exception as e:
            self.logger.warning(f"Source verification failed: {e}")
            score = 0.3
            warnings.append("Source verification error")

        return score, warnings

    def _cross_verify(
        self, entry: ProcessedEntry, context: ProcessingContext | None = None
    ) -> float:
        """Cross-verify with other sources.

        Args:
            entry: ProcessedEntry to verify.
            context: Processing context.

        Returns:
            Cross-verification score (0.0-1.0).
        """
        # Simplified: in production, compare with database of known facts
        # For now, return base score
        return 0.5

    def _fact_check_llm(
        self, entry: ProcessedEntry, context: ProcessingContext | None = None
    ) -> float | None:
        """Fact-check using LLM.

        Args:
            entry: ProcessedEntry to fact-check.
            context: Processing context.

        Returns:
            Fact-check score (0.0-1.0) or None if failed.
        """
        # This would use LLM to fact-check, but it's expensive
        # For now, return None to skip
        return None

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "InformationVerificationProcessor"

