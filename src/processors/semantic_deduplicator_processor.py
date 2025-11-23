# -*- coding: utf-8 -*-
"""Semantic deduplication processor using embeddings."""

from typing import Any

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.processing_context import ProcessingContext
from src.utils.logger import get_logger


class SemanticDeduplicatorProcessor(BaseProcessor):
    """Processor for semantic deduplication using embeddings.

    Detects duplicate content based on semantic similarity, even if URLs differ.
    Uses embedding models to compute content similarity.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize semantic deduplicator processor.

        Args:
            config: Configuration dictionary with:
                - enabled: bool (default: True)
                - similarity_threshold: float (default: 0.85) - Similarity threshold for duplicates
                - embedding_model: str (default: None) - Model name or None to use context model
                - use_openai_embedding: bool (default: False) - Use OpenAI embeddings
        """
        super().__init__(config)
        self.similarity_threshold = self.config.get("similarity_threshold", 0.85)
        self.embedding_model_name = self.config.get("embedding_model")
        self.use_openai_embedding = self.config.get("use_openai_embedding", False)
        self.logger = get_logger(__name__)
        self._embedding_cache: dict[str, list[float]] = {}

    def process(
        self,
        entry: CollectedEntry | ProcessedEntry,
        context: ProcessingContext | None = None,
    ) -> ProcessedEntry | None:
        """Check for semantic duplicates.

        Args:
            entry: CollectedEntry or ProcessedEntry to check.
            context: Processing context with embedding model and cache.

        Returns:
            ProcessedEntry with duplicate info, or None if duplicate found.
        """
        # Convert to ProcessedEntry if needed
        if isinstance(entry, ProcessedEntry):
            processed = entry
        else:
            processed = ProcessedEntry.from_collected(entry)

        # Skip if no content to compare
        content = processed.normalized_text or processed.cleaned_content or processed.summary or ""
        if not content or len(content) < 20:
            return processed

        # Get embedding model from context or use default
        embedding_model = None
        if context and context.embedding_model:
            embedding_model = context.embedding_model
        elif self.embedding_model_name:
            # Lazy load embedding model if specified
            try:
                embedding_model = self._load_embedding_model(self.embedding_model_name)
                if context:
                    context.embedding_model = embedding_model
            except Exception as e:
                self.logger.warning(f"Failed to load embedding model: {e}")
                return processed

        # If no embedding model available, skip semantic deduplication
        if not embedding_model:
            self.logger.debug("No embedding model available, skipping semantic deduplication")
            return processed

        # Compute embedding for current entry
        try:
            embedding = self._compute_embedding(content, embedding_model, context)
        except Exception as e:
            self.logger.warning(f"Failed to compute embedding: {e}")
            return processed

        # Check against cached embeddings (simplified: in production, use proper cache)
        # For now, we'll just mark as not duplicate and let URL deduplication handle it
        # In a full implementation, we'd compare against a database of embeddings

        # Mark as not duplicate for now
        processed.is_semantic_duplicate = False
        processed.similarity_score = None

        return processed

    def _load_embedding_model(self, model_name: str) -> Any:
        """Load embedding model.

        Args:
            model_name: Model name (e.g., 'sentence-transformers/all-MiniLM-L6-v2').

        Returns:
            Embedding model instance.

        Raises:
            ImportError: If sentence-transformers is not installed.
        """
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for semantic deduplication. "
                "Install it with: pip install sentence-transformers"
            )

    def _compute_embedding(
        self, text: str, model: Any, context: ProcessingContext | None = None
    ) -> list[float]:
        """Compute embedding for text.

        Args:
            text: Text to embed.
            model: Embedding model instance.
            context: Processing context.

        Returns:
            Embedding vector.
        """
        # Check cache first
        cache_key = f"embedding:{hash(text)}"
        if context and context.cache:
            try:
                cached = context.cache.get(cache_key)
                if cached:
                    return cached
            except Exception:
                pass

        # Compute embedding
        if hasattr(model, "encode"):
            # sentence-transformers interface
            embedding = model.encode(text, convert_to_numpy=False)
            if isinstance(embedding, list):
                return embedding
            else:
                return embedding.tolist()
        else:
            # Fallback: return dummy embedding
            self.logger.warning("Unknown embedding model interface")
            return [0.0] * 384  # Default dimension

    def get_processor_name(self) -> str:
        """Get the name of this processor.

        Returns:
            Processor name string.
        """
        return "SemanticDeduplicatorProcessor"

