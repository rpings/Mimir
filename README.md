# Mimir

> Drink from the well of knowledge in the AI era.

AI intelligence collection and organization system. Automatically collects, processes, and archives information from RSS, YouTube, and Twitter.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- Multi-source collection: RSS feeds, YouTube channels
- Processing pipeline: content cleaning, quality assessment, deduplication, classification, knowledge extraction
- Optional LLM enhancement: summarization, translation, categorization
- Notion integration for archiving
- Cost control with budget limits

## Quick Start

### Install

```bash
git clone https://github.com/rpings/Mimir.git
cd Mimir
pip install -r requirements.txt
```

### Configure

1. Set environment variables:
   ```bash
   export NOTION_TOKEN="your_token"
   export NOTION_DATABASE_ID="your_database_id"
   # Optional: LLM features
   export OPENAI_API_KEY="sk-..."
   ```

2. Edit configuration files:
   - `configs/sources/rss.yaml` - RSS feeds
   - `configs/sources/rules.yaml` - Classification rules
   - `configs/config.yml` - Main config

### Run

```bash
python main.py          # Sync mode
python main_async.py     # Async mode
```

## Configuration

See `configs/config.yml` for full configuration options.

Key settings:
- Processing pipeline processors (cleaning, quality, verification, etc.)
- LLM settings (optional, requires API key)
- Notion database configuration

## LLM Setup (Optional)

To enable LLM features:

1. Set `OPENAI_API_KEY` environment variable
2. Enable in `configs/config.yml`:
   ```yaml
   llm:
     enabled: true
     provider: openai
     model: gpt-4o-mini
   ```

For local models, set `base_url` in config or `LLM_BASE_URL` environment variable.

## Development

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test
pytest tests/

# Code quality
black src/ tests/
ruff check src/ tests/
```

## License

MIT License - see [LICENSE](LICENSE) file.
