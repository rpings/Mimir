# -*- coding: utf-8 -*-
"""LLM-powered content processor using litellm."""

import json
import os
from typing import Any

from litellm import completion, cost_per_token
from litellm.exceptions import APIError, RateLimitError

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.utils.cost_tracker import BudgetExceededError, CostTracker
from src.utils.logger import get_logger


class LLMProcessingError(Exception):
    """Raised when LLM processing fails."""

    pass


class LLMProcessor(BaseProcessor):
    """LLM-powered content processor with summarization, translation, and categorization."""

    def __init__(
        self,
        config: dict[str, Any],
        cost_tracker: CostTracker,
    ):
        """Initialize LLM processor.

        Args:
            config: LLM configuration dictionary with:
                - enabled: bool
                - provider: str (e.g., 'openai')
                - model: str (e.g., 'gpt-4o-mini')
                - base_url: str | None (optional custom API base URL)
                - features: dict with summarization, translation, smart_categorization
                - translation: dict with target_languages
            cost_tracker: CostTracker instance for budget management.
        """
        self.config = config
        self.cost_tracker = cost_tracker
        self.enabled = config.get("enabled", False)
        self.provider = config.get("provider", "openai")
        self.model = config.get("model", "gpt-4o-mini")
        
        # Base URL support: env var > config > None (use provider default)
        self.base_url = os.environ.get("LLM_BASE_URL") or config.get("base_url")
        if self.base_url == "":
            self.base_url = None
        
        self.features = config.get("features", {})
        self.translation_config = config.get("translation", {})
        self.target_languages = self.translation_config.get("target_languages", [])
        
        self.logger = get_logger(__name__)

    def process(self, entry: CollectedEntry) -> ProcessedEntry:
        """Process entry using LLM enhancements.

        Args:
            entry: CollectedEntry to process (should already have topics/priority from keyword processor).

        Returns:
            ProcessedEntry with LLM enhancements added.
        """
        # Convert to ProcessedEntry if needed
        if isinstance(entry, ProcessedEntry):
            processed = entry
        else:
            processed = ProcessedEntry.from_collected(entry)

        if not self.enabled:
            self.logger.debug("LLM processing is disabled, skipping")
            return processed

        try:
            # Check budget before processing
            self.cost_tracker.check_budget()
        except BudgetExceededError as e:
            self.logger.warning(f"Budget exceeded, skipping LLM processing: {e}")
            return processed

        # Apply LLM features
        # Note: Costs are tracked in _call_llm, we just need to aggregate them
        llm_features_used = False

        try:
            # Summarization
            if self.features.get("summarization", False):
                summary = self._generate_summary(processed)
                if summary:
                    processed.summary_llm = summary
                    llm_features_used = True

            # Translation
            if self.features.get("translation", False) and self.target_languages:
                translations = self._translate_content(processed)
                if translations:
                    processed.translation = translations
                    llm_features_used = True

            # Smart categorization
            if self.features.get("smart_categorization", False):
                categories = self._smart_categorize(processed)
                if categories:
                    processed.topics_llm = categories.get("topics")
                    processed.priority_llm = categories.get("priority")
                    llm_features_used = True

            # Update processing method
            if llm_features_used:
                if processed.processing_method == "keyword":
                    processed.processing_method = "hybrid"
                else:
                    processed.processing_method = "llm"

        except (LLMProcessingError, BudgetExceededError) as e:
            self.logger.warning(f"LLM processing failed, using keyword results: {e}")
            # Return processed entry with keyword results only

        return processed

    def _call_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Call LLM API using litellm.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            temperature: Temperature for generation (0.0-1.0).

        Returns:
            LLM response dictionary with 'content', 'usage', etc.

        Raises:
            LLMProcessingError: If API call fails.
            BudgetExceededError: If budget is exceeded.
        """
        try:
            # Prepare litellm parameters
            params = {
                "model": f"{self.provider}/{self.model}",
                "messages": messages,
                "temperature": temperature,
            }
            
            # Add base_url if configured
            if self.base_url:
                params["api_base"] = self.base_url
                self.logger.debug(f"Using custom base URL: {self.base_url}")

            # Check budget before call
            # Estimate cost (rough estimate: $0.15 per 1M tokens for gpt-4o-mini)
            estimated_tokens = sum(len(msg.get("content", "")) for msg in messages) // 4
            estimated_cost = (estimated_tokens / 1_000_000) * 0.15
            self.cost_tracker.check_budget(estimated_cost)

            # Make API call
            response = completion(**params)

            # Extract response
            content = response.choices[0].message.content
            usage = response.usage

            # Calculate actual cost
            prompt_tokens = usage.prompt_tokens if hasattr(usage, "prompt_tokens") else 0
            completion_tokens = usage.completion_tokens if hasattr(usage, "completion_tokens") else 0
            
            try:
                cost = cost_per_token(
                    model=self.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            except Exception:
                # Fallback cost calculation for gpt-4o-mini
                cost = (prompt_tokens / 1_000_000 * 0.15) + (completion_tokens / 1_000_000 * 0.6)

            total_tokens = prompt_tokens + completion_tokens

            # Record cost
            self.cost_tracker.record_call(
                cost=cost,
                tokens=total_tokens,
                model=self.model,
            )

            return {
                "content": content,
                "cost": cost,
                "tokens": total_tokens,
            }

        except (APIError, RateLimitError) as e:
            raise LLMProcessingError(f"LLM API error: {e}") from e
        except BudgetExceededError:
            raise
        except Exception as e:
            raise LLMProcessingError(f"Unexpected LLM error: {e}") from e

    def _generate_summary(self, entry: ProcessedEntry) -> str | None:
        """Generate summary using LLM.

        Args:
            entry: ProcessedEntry with content to summarize.

        Returns:
            Generated summary or None if failed.
        """
        content = f"{entry.title}\n\n{entry.summary or ''}"
        if len(content) < 50:
            return None

        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that creates concise summaries of technical content. Summarize the following content in 2-3 sentences, focusing on key points and innovations.",
            },
            {
                "role": "user",
                "content": f"Summarize this content:\n\n{content}",
            },
        ]

        try:
            result = self._call_llm(messages, temperature=0.3)
            return result["content"].strip()
        except (LLMProcessingError, BudgetExceededError) as e:
            self.logger.warning(f"Failed to generate summary: {e}")
            return None

    def _translate_content(self, entry: ProcessedEntry) -> dict[str, str] | None:
        """Translate content to target languages.

        Args:
            entry: ProcessedEntry with content to translate.

        Returns:
            Dictionary mapping language codes to translated content, or None if failed.
        """
        if not self.target_languages:
            return None

        content = f"{entry.title}\n\n{entry.summary or ''}"
        if len(content) < 20:
            return None

        translations = {}
        for lang in self.target_languages:
            try:
                messages = [
                    {
                        "role": "system",
                        "content": f"You are a professional translator. Translate the following content to {lang}, maintaining technical accuracy and natural phrasing.",
                    },
                    {
                        "role": "user",
                        "content": f"Translate to {lang}:\n\n{content}",
                    },
                ]

                result = self._call_llm(messages, temperature=0.2)
                translations[lang] = result["content"].strip()
            except (LLMProcessingError, BudgetExceededError) as e:
                self.logger.warning(f"Failed to translate to {lang}: {e}")
                # Continue with other languages

        return translations if translations else None

    def _smart_categorize(self, entry: ProcessedEntry) -> dict[str, Any] | None:
        """Use LLM to categorize content and determine priority.

        Args:
            entry: ProcessedEntry with content to categorize.

        Returns:
            Dictionary with 'topics' and 'priority', or None if failed.
        """
        content = f"{entry.title}\n\n{entry.summary or ''}"
        if len(content) < 20:
            return None

        messages = [
            {
                "role": "system",
                "content": "You are a content categorization assistant. Analyze the content and provide:\n1. A list of 1-3 relevant topic tags (e.g., 'AI', 'RAG', 'Agent', 'Multimodal')\n2. A priority level: 'High', 'Medium', or 'Low'\n\nRespond in JSON format: {\"topics\": [\"tag1\", \"tag2\"], \"priority\": \"High\"}",
            },
            {
                "role": "user",
                "content": f"Categorize this content:\n\n{content}",
            },
        ]

        try:
            result = self._call_llm(messages, temperature=0.3)

            # Try to parse JSON response
            content_text = result["content"].strip()
            # Remove markdown code blocks if present
            if content_text.startswith("```"):
                lines = content_text.split("\n")
                content_text = "\n".join(lines[1:-1]) if len(lines) > 2 else content_text

            categories = json.loads(content_text)
            return {
                "topics": categories.get("topics", []),
                "priority": categories.get("priority", "Low"),
            }
        except (LLMProcessingError, BudgetExceededError, json.JSONDecodeError) as e:
            self.logger.warning(f"Failed to categorize with LLM: {e}")
            return None

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "LLMProcessor"

