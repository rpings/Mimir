# -*- coding: utf-8 -*-
"""LangChain-based processor pipeline."""

from langchain_core.runnables import RunnableLambda

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry


class ProcessorPipeline:
    """LangChain-based processor pipeline for chaining multiple processors."""

    def __init__(self, processors: list[BaseProcessor]):
        """Initialize processor pipeline.

        Args:
            processors: List of processors to chain in sequence.
        """
        self.processors = processors
        
        # Convert processors to LangChain Runnables
        runnables = [
            RunnableLambda(lambda x, p=p: p.process(x))
            for p in processors
        ]
        
        # Chain processors using LCEL (LangChain Expression Language)
        if runnables:
            self.chain = runnables[0]
            for runnable in runnables[1:]:
                self.chain = self.chain | runnable
        else:
            # Empty pipeline - just pass through
            self.chain = RunnableLambda(lambda x: ProcessedEntry.from_collected(x))

    def process(self, entry: CollectedEntry) -> ProcessedEntry:
        """Process entry through the pipeline.

        Args:
            entry: CollectedEntry to process.

        Returns:
            ProcessedEntry after all processors.
        """
        return self.chain.invoke(entry)

    async def aprocess(self, entry: CollectedEntry) -> ProcessedEntry:
        """Process entry asynchronously through the pipeline.

        Args:
            entry: CollectedEntry to process.

        Returns:
            ProcessedEntry after all processors.
        """
        return await self.chain.ainvoke(entry)

