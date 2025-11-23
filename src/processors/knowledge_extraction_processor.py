# -*- coding: utf-8 -*-
"""Knowledge extraction processor for structured information extraction."""

import json
import re
from typing import Any

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.processing_context import ProcessingContext
from src.utils.logger import get_logger


class KnowledgeExtractionProcessor(BaseProcessor):
    """Processor for extracting structured knowledge from content.

    Extracts:
    - Entities: People, organizations, technologies, concepts
    - Relations: Relationships between entities
    - Key points: Core insights, innovations, conclusions
    - Structured summary: Background, method, result, significance
    - Auto tags: Automatically generated tags
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize knowledge extraction processor.

        Args:
            config: Configuration dictionary with:
                - enabled: bool (default: True)
                - extract_entities: bool (default: True)
                - extract_relations: bool (default: True)
                - extract_key_points: bool (default: True)
                - use_llm: bool (default: False) - Use LLM for extraction
        """
        super().__init__(config)
        self.extract_entities = self.config.get("extract_entities", True)
        self.extract_relations = self.config.get("extract_relations", True)
        self.extract_key_points = self.config.get("extract_key_points", True)
        self.use_llm = self.config.get("use_llm", False)
        self.logger = get_logger(__name__)

        # Common entity patterns
        self.entity_patterns = {
            "technology": [
                r"\b(?:GPT|BERT|Transformer|LLM|NLP|AI|ML|DL)\b",
                r"\b(?:PyTorch|TensorFlow|JAX|HuggingFace)\b",
            ],
            "organization": [
                r"\b(?:OpenAI|Anthropic|Google|Meta|Microsoft|DeepMind)\b",
            ],
        }

    def process(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:
        """Extract structured knowledge.

        Args:
            entry: CollectedEntry or ProcessedEntry to extract from.
            context: Optional processing context.

        Returns:
            ProcessedEntry with extracted knowledge, or None if extraction fails.
        """
        # Convert to ProcessedEntry if needed
        if isinstance(entry, ProcessedEntry):
            processed = entry
        else:
            processed = ProcessedEntry.from_collected(entry)

        content = processed.cleaned_content or processed.summary or ""
        if not content or len(content) < 20:
            return processed

        # Extract entities
        if self.extract_entities:
            entities = self._extract_entities(content)
            processed.entities = entities

        # Extract relations (simplified)
        if self.extract_relations:
            relations = self._extract_relations(content, processed.entities)
            processed.relations = relations

        # Extract key points
        if self.extract_key_points:
            key_points = self._extract_key_points(content)
            processed.key_points = key_points

        # Generate structured summary
        structured_summary = self._generate_structured_summary(content)
        processed.structured_summary = structured_summary

        # Generate auto tags
        auto_tags = self._generate_auto_tags(processed)
        processed.auto_tags = auto_tags

        return processed

    def _extract_entities(self, content: str) -> list[dict[str, Any]]:
        """Extract entities from content.

        Args:
            content: Content text.

        Returns:
            List of entity dictionaries with type, name, context.
        """
        entities: list[dict[str, Any]] = []

        # Extract using patterns
        for entity_type, patterns in self.entity_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    entity = {
                        "type": entity_type,
                        "name": match.group(0),
                        "context": content[max(0, match.start() - 50) : match.end() + 50],
                    }
                    # Avoid duplicates
                    if not any(e["name"] == entity["name"] for e in entities):
                        entities.append(entity)

        return entities

    def _extract_relations(
        self, content: str, entities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Extract relations between entities.

        Args:
            content: Content text.
            entities: List of extracted entities.

        Returns:
            List of relation dictionaries with subject, predicate, object.
        """
        relations: list[dict[str, Any]] = []

        # Simplified: extract common relation patterns
        relation_patterns = [
            (r"(\w+)\s+(?:uses|implements|based on|built with)\s+(\w+)", "uses"),
            (r"(\w+)\s+(?:from|by)\s+(\w+)", "from"),
        ]

        for pattern, predicate in relation_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                subject = match.group(1)
                obj = match.group(2)
                relation = {
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                }
                relations.append(relation)

        return relations

    def _extract_key_points(self, content: str) -> list[str]:
        """Extract key points from content.

        Args:
            content: Content text.

        Returns:
            List of key point strings.
        """
        key_points: list[str] = []

        # Extract sentences with key indicators
        sentences = re.split(r"[.!?]+\s+", content)
        key_indicators = [
            "introduces",
            "proposes",
            "achieves",
            "demonstrates",
            "shows",
            "presents",
            "novel",
            "breakthrough",
            "state of the art",
        ]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            for indicator in key_indicators:
                if indicator in sentence_lower and len(sentence) > 20:
                    key_points.append(sentence.strip())
                    break

        # Limit to top 5 key points
        return key_points[:5]

    def _generate_structured_summary(self, content: str) -> dict[str, Any]:
        """Generate structured summary.

        Args:
            content: Content text.

        Returns:
            Dictionary with background, method, result, significance.
        """
        # Simplified: extract first few sentences for each section
        sentences = re.split(r"[.!?]+\s+", content)
        num_sentences = len(sentences)

        return {
            "background": ". ".join(sentences[: max(1, num_sentences // 4)]) + ".",
            "method": ". ".join(
                sentences[max(1, num_sentences // 4) : max(2, num_sentences // 2)]
            )
            + ".",
            "result": ". ".join(
                sentences[max(2, num_sentences // 2) : max(3, num_sentences * 3 // 4)]
            )
            + ".",
            "significance": ". ".join(sentences[max(3, num_sentences * 3 // 4) :]) + ".",
        }

    def _generate_auto_tags(self, entry: ProcessedEntry) -> list[str]:
        """Generate automatic tags.

        Args:
            entry: ProcessedEntry to tag.

        Returns:
            List of tag strings.
        """
        tags: list[str] = []

        # Use existing topics as tags
        if entry.topics:
            tags.extend(entry.topics)

        # Extract tags from entities
        if entry.entities:
            entity_names = [e["name"] for e in entry.entities[:5]]
            tags.extend(entity_names)

        # Remove duplicates and limit
        tags = list(dict.fromkeys(tags))[:10]

        return tags

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "KnowledgeExtractionProcessor"

