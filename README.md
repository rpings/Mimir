# Mimir

> Drink from the well of knowledge in the AI era.

AI intelligence collection and organization system. Automatically collects, processes, and archives information from RSS, YouTube, and Twitter.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Multi-source collection**: RSS feeds, YouTube channels, Twitter/X (placeholder)
- **Intelligent processing**: Keyword classification + optional LLM enhancement
- **Storage**: Notion integration, DingTalk notifications
- **Performance**: Async processing, caching, deduplication
- **Cost control**: Budget limits, cost tracking, local model support

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
   export LLM_BASE_URL="http://localhost:11434/v1"  # For local models
   ```

2. Edit configuration files:
   - `configs/sources/rss.yaml` - RSS feeds
   - `configs/sources/youtube.yaml` - YouTube channels
   - `configs/sources/rules.yaml` - Classification rules
   - `configs/config.yml` - Main config

### Run

```bash
# Sync mode
python main.py

# Async mode (recommended)
python main_async.py

# Or use run script
./run.sh          # sync
./run.sh async    # async
```

## Configuration

### Main Config (`configs/config.yml`)

```yaml
timezone: Asia/Shanghai

notion:
  database_id: ${NOTION_DATABASE_ID}

llm:
  enabled: false  # Enable for LLM features
  provider: openai
  model: gpt-4o-mini
  base_url: null  # Custom API URL (e.g., local models)
  daily_limit: 5.0
  monthly_budget: 50.0
  features:
    summarization: true
    translation: true
    smart_categorization: true

dingtalk:
  enabled: false
  webhook_url: ${DINGTALK_WEBHOOK_URL}
  secret: ${DINGTALK_SECRET}
```

## LLM Setup

### OpenAI

```bash
export OPENAI_API_KEY="sk-..."
```

Enable in `configs/config.yml`:
```yaml
llm:
  enabled: true
  provider: openai
  model: gpt-4o-mini
```

### Local Models (Ollama, vLLM)

```yaml
llm:
  enabled: true
  provider: openai
  model: llama3
  base_url: "http://localhost:11434/v1"
```

Or: `export LLM_BASE_URL="http://localhost:11434/v1"`

**Priority**: `LLM_BASE_URL` env var > config `base_url` > provider default

## Development

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test
pytest tests/ --cov=src

# Code quality
black src/ tests/
isort src/ tests/
ruff check src/ tests/
mypy src/
```

## Project Structure

```
Mimir/
├── src/
│   ├── collectors/    # RSS, YouTube, Twitter
│   ├── processors/    # Keyword, LLM, pipeline
│   ├── storages/      # Notion, DingTalk, cache
│   └── utils/         # Config, logger, retry
├── configs/           # Configuration files
├── tests/             # Test suite (94% coverage)
├── main.py            # Sync entry point
└── main_async.py      # Async entry point
```

## Cost

- **Without LLM**: $0 (GitHub Actions free tier)
- **With LLM**: ~$30-150/month (configurable limits)
- **Local models**: $0 (use `base_url`)

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Follow coding standards in `.cursor/rules/`
4. Write tests
5. Commit with [Conventional Commits](https://www.conventionalcommits.org/)
6. Push and open Pull Request
