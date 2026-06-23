"""Shared test fixtures."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

from mimir.config import Config, LLMConfig, NotionConfig, SourcesConfig
from mimir.models import EntryType, RawEntry


@pytest.fixture
def llm_cfg() -> LLMConfig:
    return LLMConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")


@pytest.fixture
def notion_cfg() -> NotionConfig:
    return NotionConfig(token="secret_test", entries_db_id="entries_test", reports_db_id="reports_test")


@pytest.fixture
def sources_cfg() -> SourcesConfig:
    return SourcesConfig()


@pytest.fixture
def config(llm_cfg, notion_cfg, sources_cfg) -> Config:
    return Config(llm=llm_cfg, notion=notion_cfg, sources=sources_cfg)


@pytest.fixture
def sample_raw_entries() -> list[RawEntry]:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    return [
        RawEntry(
            title="Multi-Agent Planning with LLMs",
            link="https://arxiv.org/abs/2606.00001",
            summary="We propose a novel multi-agent planning framework that achieves SOTA results on SWE-bench.",
            published=now,
            source="arxiv:AI,CL,LG",
            entry_type=EntryType.PAPER,
        ),
        RawEntry(
            title="owner/repo",
            link="https://github.com/owner/repo",
            summary="A toolkit for serving and fine-tuning small language models.",
            published=now,
            source="github_trending",
            entry_type=EntryType.REPO,
        ),
        RawEntry(
            title="OpenAI announces GPT-5",
            link="https://example.com/news/1",
            summary="OpenAI released GPT-5 with major improvements.",
            published=now,
            source="hackernews",
            entry_type=EntryType.NEWS,
        ),
    ]
