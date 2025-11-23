# -*- coding: utf-8 -*-
"""Base collector interface."""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class CollectedEntry(BaseModel):
    """Data contract for collected entries with automatic validation.

    Attributes:
        title: Entry title (required).
        link: Entry URL (required, validated as HTTP/HTTPS URL).
        summary: Entry summary/description (optional).
        published: Publication date in ISO format (optional).
        source_name: Name of the source (optional).
        source_type: Type of source, e.g., 'blog', 'paper' (optional).
    """

    title: str = Field(..., min_length=1, max_length=200)
    link: HttpUrl
    summary: str = Field(default="", max_length=10000)
    published: str | None = Field(default=None, max_length=50)
    source_name: str | None = Field(default=None, max_length=100)
    source_type: str | None = Field(default=None, max_length=50)

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            HttpUrl: str,
        },
    }

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for backward compatibility.

        Returns:
            Dictionary representation of the entry.
        """
        return {
            "title": self.title,
            "link": str(self.link),
            "summary": self.summary,
            "published": self.published,
            "source_name": self.source_name,
            "source_type": self.source_type,
        }


class BaseCollector(ABC):
    """Abstract base class for data collectors.

    All collectors must implement the `collect()` method to fetch data
    from their respective sources and return a list of standardized entries.
    """

    @abstractmethod
    def collect(self) -> list[CollectedEntry]:  # pragma: no cover
        """Collect data from source.

        Returns:
            List of collected items, each conforming to CollectedEntry contract.
            Each entry must have at least:
            - title: str
            - link: str
            Optional fields:
            - summary: str
            - published: str (ISO format date string)
            - source_name: str
            - source_type: str

        Raises:
            ValueError: If collection fails due to invalid configuration.
            ConnectionError: If connection to source fails.
            TimeoutError: If request times out.
        """
        pass

    async def acollect(self) -> list[CollectedEntry]:  # pragma: no cover
        """Collect data from source asynchronously.

        Default implementation calls synchronous collect().
        Override for async-optimized collectors.

        Returns:
            List of collected items, each conforming to CollectedEntry contract.

        Raises:
            ValueError: If collection fails due to invalid configuration.
            ConnectionError: If connection to source fails.
            TimeoutError: If request times out.
        """
        import asyncio
        return await asyncio.to_thread(self.collect)

    @abstractmethod
    def get_source_name(self) -> str:  # pragma: no cover
        """Get the name of this data source.

        Returns:
            Source name string (e.g., "OpenAI Blog RSS", "YouTube Channel").
        """
        pass
