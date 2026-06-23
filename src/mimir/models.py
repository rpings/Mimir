"""Data types for Mimir v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class EntryType(StrEnum):
    PAPER = "paper"
    REPO = "repo"
    NEWS = "news"


@dataclass
class RawEntry:
    """Output of source collectors."""
    title: str
    link: str
    summary: str
    published: datetime
    source: str
    entry_type: EntryType
    extra: dict = field(default_factory=dict)


@dataclass
class EnrichedEntry(RawEntry):
    """Output of AI processing, ready for Notion."""
    # Common
    topic: str = ""
    priority: str = "medium"
    # Paper
    overview: str = ""
    innovation: str = ""
    significance: str = ""
    authors: str = ""
    venue: str = ""
    # Repo
    use_case: str = ""
    stars: int = 0
    # News
    key_point: str = ""
    verification: str = ""

    def page_body(self) -> str:
        """Build page content for Notion (shown as Gallery card preview)."""
        if self.entry_type == EntryType.PAPER:
            parts = []
            if self.overview:
                parts.append(f"## 概述\n{self.overview}")
            if self.innovation:
                parts.append(f"## 创新点\n{self.innovation}")
            if self.significance:
                parts.append(f"## 为什么重要\n{self.significance}")
            return "\n\n".join(parts)
        elif self.entry_type == EntryType.REPO:
            return self.use_case or ""
        else:
            return self.key_point or ""


@dataclass
class TopicDef:
    """One topic in the AI taxonomy."""
    id: str
    name: str
    description: str
