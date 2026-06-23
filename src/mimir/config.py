"""Configuration loader — TOML file + environment variable overrides.

Does NOT read .env files. Environment variables must be set externally
(e.g., GitHub Actions secrets, shell export, or direnv).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""


@dataclass
class SourcesConfig:
    arxiv_categories: list[str] = field(default_factory=lambda: ["cs.AI", "cs.CL", "cs.LG", "cs.CV"])
    arxiv_max_results: int = 50
    github_trending: bool = True
    github_max_repos: int = 25
    hackernews: bool = True
    hackernews_min_points: int = 50
    qbitai: bool = True


@dataclass
class NotionConfig:
    token: str = ""
    entries_db_id: str = ""
    reports_db_id: str = ""
    parent_page_id: str = ""


@dataclass
class ReportConfig:
    language: str = "zh"
    issues_dir: str = "issues"
    site_url: str = ""  # GitHub Pages base URL for report links


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    notion: NotionConfig = field(default_factory=NotionConfig)
    report: ReportConfig = field(default_factory=ReportConfig)


def load(path: str = "mimir.toml") -> Config:
    """Load config from TOML file. Environment variables take precedence."""
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))

    # -- LLM --
    llm_raw = raw.get("llm", {})
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or llm_raw.get("api_key", "")
    )
    if not api_key:
        api_key = ""  # optional — some commands (e.g. report) don't need LLM

    llm = LLMConfig(
        provider=llm_raw.get("provider", "deepseek"),
        model=os.environ.get("LLM_MODEL") or llm_raw.get("model", "deepseek-chat"),
        base_url=os.environ.get("LLM_BASE_URL") or llm_raw.get("base_url", "https://api.deepseek.com"),
        api_key=api_key,
    )

    # -- Sources --
    src_raw = raw.get("sources", {})
    sources = SourcesConfig(
        arxiv_categories=list(src_raw.get("arxiv_categories", ["cs.AI", "cs.CL", "cs.LG", "cs.CV"])),
        arxiv_max_results=int(src_raw.get("arxiv_max_results", 50)),
        github_trending=bool(src_raw.get("github_trending", True)),
        github_max_repos=int(src_raw.get("github_max_repos", 25)),
        hackernews=bool(src_raw.get("hackernews", True)),
        hackernews_min_points=int(src_raw.get("hackernews_min_points", 50)),
        qbitai=bool(src_raw.get("qbitai", True)),
    )

    # -- Notion --
    notion_raw = raw.get("notion", {})
    token = os.environ.get("NOTION_TOKEN") or notion_raw.get("token", "")
    entries_db = (
        os.environ.get("NOTION_ENTRIES_DB_ID")
        or os.environ.get("NOTION_DATABASE_ID")  # legacy compat
        or notion_raw.get("entries_db_id", "")
    )
    reports_db = (
        os.environ.get("NOTION_REPORTS_DB_ID")
        or notion_raw.get("reports_db_id", "")
    )
    if not token:
        raise ConfigError("NOTION_TOKEN environment variable is required")
    parent_page = (
        os.environ.get("NOTION_PARENT_PAGE_ID")
        or notion_raw.get("parent_page_id", "")
    )
    notion = NotionConfig(
        token=token, entries_db_id=entries_db,
        reports_db_id=reports_db, parent_page_id=parent_page,
    )

    # -- Report --
    rep_raw = raw.get("report", {})
    report = ReportConfig(
        language=str(rep_raw.get("language", "zh")),
        issues_dir=str(rep_raw.get("issues_dir", "issues")),
        site_url=str(rep_raw.get("site_url", "")),
    )

    return Config(llm=llm, sources=sources, notion=notion, report=report)
