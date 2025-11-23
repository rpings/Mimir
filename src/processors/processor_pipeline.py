# -*- coding: utf-8 -*-
"""LangChain-based processor pipeline with advanced features."""

from langchain_core.runnables import RunnableLambda

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.processing_context import ProcessingContext


class SkipMarker:
    """Marker class to indicate entry should be skipped."""

    def __init__(self, entry: CollectedEntry | ProcessedEntry):
        """Initialize skip marker.

        Args:
            entry: Entry that should be skipped.
        """
        self.entry = entry


class ProcessorPipeline:
    """LangChain-based processor pipeline with skip support and error handling.

    Features:
    - Skip mechanism: Processors can return None to skip entries
    - Error recovery: Automatic fallback on processor errors
    - Context sharing: Shared resources across processors
    - Async support: Full async/await support
    """

    def __init__(
        self,
        processors: list[BaseProcessor],
        context: ProcessingContext | None = None,
    ):
        """Initialize processor pipeline.

        Args:
            processors: List of processors to chain in sequence.
            context: Shared context for all processors.
        """
        self.processors = processors
        self.context = context or ProcessingContext()
        self.chain = self._build_chain()

    def _build_chain(self):
        """Build LangChain pipeline with skip support and error handling.

        Returns:
            LangChain Runnable chain.
        """
        runnables = []

        for processor in self.processors:
            if not processor.is_enabled():
                continue

            # Wrap processor with skip detection and error recovery
            def process_with_error_handling(x, p=processor, ctx=self.context):
                """Process with error handling and skip detection."""
                try:
                    return self._process_with_skip(x, p, ctx)
                except Exception:
                    # On error, pass through the entry
                    return x

            runnable = RunnableLambda(process_with_error_handling)
            runnables.append(runnable)

        # Chain all processors
        if not runnables:
            # Empty pipeline - just convert to ProcessedEntry
            return RunnableLambda(lambda x: ProcessedEntry.from_collected(x))

        chain = runnables[0]
        for runnable in runnables[1:]:
            chain = chain | runnable

        return chain

    def _process_with_skip(
        self,
        entry: CollectedEntry | ProcessedEntry,
        processor: BaseProcessor,
        context: ProcessingContext,
    ) -> ProcessedEntry | SkipMarker:
        """Process entry and handle skip (None return).

        Args:
            entry: Entry to process.
            processor: Processor to use.
            context: Processing context.

        Returns:
            ProcessedEntry or SkipMarker if entry should be skipped.
        """
        result = processor.process(entry, context)

        # If None, return a special marker to indicate skip
        if result is None:
            return SkipMarker(entry)

        return result

    def process(self, entry: CollectedEntry) -> ProcessedEntry | None:
        """Process entry through the pipeline.

        Args:
            entry: CollectedEntry to process.

        Returns:
            ProcessedEntry after all processors, or None if skipped.
        """
        result = self.chain.invoke(entry)

        # Check for skip marker
        if isinstance(result, SkipMarker):
            return None

        return result

    async def aprocess(self, entry: CollectedEntry) -> ProcessedEntry | None:
        """Process entry asynchronously through the pipeline.

        Args:
            entry: CollectedEntry to process.

        Returns:
            ProcessedEntry after all processors, or None if skipped.
        """
        result = await self.chain.ainvoke(entry)

        # Check for skip marker
        if isinstance(result, SkipMarker):
            return None

        return result

