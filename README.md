# Mimir

> Drink from the well of knowledge in the AI era.

Mimir is an AI-powered knowledge base that automatically collects, processes, and archives information from ArXiv, GitHub, Hacker News, and Chinese AI news (量子位). Entries are organized into a Notion kanban board with AI-generated summaries, topic classification, and priority ratings.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Quick Start

```bash
git clone https://github.com/rpings/Mimir.git
cd Mimir
pip install -e .
cp .env.example .env   # edit with your keys
mimir setup            # create Notion databases
mimir collect          # collect and process entries
```

## Required Environment Variables

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | API key for LLM provider (e.g., DeepSeek) |
| `NOTION_TOKEN` | Notion integration token |
| `NOTION_ENTRIES_DB_ID` | Database ID for collected entries |
| `NOTION_PARENT_PAGE_ID` | Parent page for `mimir setup` to create databases under |

## CLI Commands

| Command | Description |
|---------|-------------|
| `mimir setup` | Create Entries and Reports databases in Notion |
| `mimir collect [--dry-run]` | Fetch sources, enrich with AI, write to Entries DB |
| `mimir report [--week WNN]` | Generate weekly report, publish to GitHub Pages, write to Reports DB |

### collect

Downloads new content from all sources, deduplicates against existing Notion entries, runs AI enrichment (topic classification, summarization, priority scoring), and writes new entries to the Entries database.

Use `--dry-run` to preview what would be collected without writing anything.

### setup

Creates the required Notion databases (Entries DB and Reports DB) with the correct schema under the specified parent page. Run once after initial configuration.

### report

Generates a weekly HTML report summarizing trends, featured papers, notable projects, and important news. Reports are published to GitHub Pages and linked from the Reports database.

## Configuration

See `mimir.toml` for all configuration options. Each option includes inline documentation and the corresponding environment variable override.

## Architecture

| Layer | Technology |
|-------|-----------|
| Sources | ArXiv API, GitHub Trending, Hacker News, 量子位 |
| AI Processing | DeepSeek (3 prompts: paper, project, news) |
| Storage | Notion (Entries DB + Reports DB) |
| Scheduling | GitHub Actions (daily collect, weekly report) |
| Reports | Jinja2 + HTML → GitHub Pages |

See the [design docs](https://github.com/rpings/wiki) for detailed architecture and technical decisions.

## License

MIT License - see [LICENSE](LICENSE) file.
