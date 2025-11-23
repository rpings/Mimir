# Mimir

> Drink from the well of knowledge in the AI era.

**Mimir** (named after the well of wisdom in Norse mythology) is an intelligent AI intelligence collection and organization system that automates the collection, processing, and archiving of important information in the AI field.

## Overview

Mimir automatically collects information from multiple sources (RSS feeds, and later YouTube, Twitter), processes content using LLM (optional), and syncs structured data to Notion or DingTalk.

## Features

### Phase 1 (MVP) - Current
- ✅ Multi-source RSS feed collection
- ✅ Keyword-based classification and tagging
- ✅ Automated workflow via GitHub Actions
- ✅ Notion integration
- ✅ Zero cost (GitHub Actions free tier)

### Phase 2 (LLM Enhancement) - Available
- ✅ LLM-powered content summarization
- ✅ Intelligent translation
- ✅ Smart categorization
- ✅ Cost monitoring and budget controls
- ✅ Custom Base URL support (for local models, proxies, OpenAI-compatible APIs)

### Phase 3 (Optimization) - Future
- 📋 Performance optimization
- 📋 YouTube/Twitter integration
- 📋 DingTalk notifications

## Quick Start

### Prerequisites

- Python 3.11+
- Notion account and database
- GitHub account (for Actions)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/rpings/Mimir.git
cd Mimir
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure Notion:
   - Create a Notion Internal Integration
   - Grant access to your database
   - Get `NOTION_TOKEN` and `NOTION_DATABASE_ID`

4. Set up GitHub Actions secrets:
   - `NOTION_TOKEN`: Your Notion integration token
   - `NOTION_DATABASE_ID`: Your Notion database ID
   - `OPENAI_API_KEY`: Your OpenAI API key (if using LLM features with OpenAI)
   - `LLM_BASE_URL`: Optional custom API base URL (overrides config, for local models/proxies)

5. Configure RSS sources:
   - Edit `configs/sources/rss.yaml` to add your RSS feeds
   - Edit `configs/sources/rules.yaml` to customize classification rules

6. Run locally (optional):
```bash
python main.py
```

## Configuration

### Main Config (`configs/config.yml`)

```yaml
timezone: Asia/Shanghai
notion:
  database_id: ${NOTION_DATABASE_ID}
processing:
  enable_llm: false  # Deprecated: use llm.enabled instead
  enable_keyword_classification: true
  deduplication:
    method: url
cache:
  enabled: true
  path: ./data/cache
  ttl_days: 30
retry:
  max_attempts: 3
  backoff_factor: 2

# LLM Configuration (Phase 2)
llm:
  enabled: false  # Must be explicitly enabled
  provider: openai  # openai, anthropic, etc.
  model: gpt-4o-mini  # Model name (recommended for cost efficiency)
  base_url: null  # Optional: Custom API base URL
  # Examples:
  # base_url: "https://api.openai.com/v1"  # Default OpenAI endpoint
  # base_url: "http://localhost:1234/v1"  # Local model server (Ollama, vLLM, etc.)
  # base_url: "https://api.example.com/v1"  # Custom proxy or compatible API
  daily_limit: 5.0  # USD per day
  monthly_budget: 50.0  # USD per month
  features:
    summarization: true  # Generate LLM summaries
    translation: true  # Translate content
    smart_categorization: true  # Use LLM for topic/priority classification
  translation:
    target_languages: ["zh", "en"]  # Optional translation targets
```

### RSS Sources (`configs/sources/rss.yaml`)

Add your RSS feed URLs and source types.

### Classification Rules (`configs/sources/rules.yaml`)

Define topic keywords and priority rules for content classification.

## Project Structure

```
Mimir/
├── .github/workflows/    # GitHub Actions workflows
├── src/                  # Source code
│   ├── collectors/       # Data collection modules
│   ├── processors/       # Content processing modules
│   ├── storages/         # Data persistence modules
│   └── utils/            # Utility modules
├── configs/              # Configuration files
├── data/                 # Local data (cache, logs)
├── tests/                # Test files
└── main.py               # Main entry point
```

## Development

### Code Style

- Follow PEP 8
- Use type hints for all functions
- Maximum line length: 88 characters (Black formatter)
- See `.cursor/rules/` for detailed coding standards

### Testing

```bash
pytest tests/
```

### Running Locally

```bash
python main.py
```

## Cost Considerations

### Phase 1 (MVP)
- **Cost**: $0 (GitHub Actions free tier only)
- **LLM Calls**: 0

### Phase 2 (With LLM)
- **Estimated Cost**: $30-150/month (depending on usage)
  - GPT-4o-mini: ~$0.15 per 1M input tokens, ~$0.6 per 1M output tokens
  - Typical article: ~500-2000 tokens per feature (summary/translation/categorization)
- **Controls**: 
  - Daily limits (default: $5/day)
  - Monthly budget (default: $50/month)
  - Automatic cost tracking and persistence
  - Budget enforcement before API calls
- **Default**: LLM features disabled by default (`llm.enabled: false`)
- **Local Models**: Use `base_url` to point to local model servers (Ollama, vLLM) for $0 cost

## LLM Setup

### Using OpenAI (Default)

1. Get your OpenAI API key from https://platform.openai.com/api-keys
2. Set environment variable:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```
3. Enable LLM in `configs/config.yml`:
   ```yaml
   llm:
     enabled: true
     provider: openai
     model: gpt-4o-mini
   ```

### Using Local Models (Ollama, vLLM, etc.)

1. Start your local model server (e.g., Ollama on `http://localhost:11434`)
2. Configure base URL in `configs/config.yml`:
   ```yaml
   llm:
     enabled: true
     provider: openai  # Use 'openai' for OpenAI-compatible APIs
     model: llama3  # Your local model name
     base_url: "http://localhost:11434/v1"  # Your local server endpoint
   ```
   Or use environment variable:
   ```bash
   export LLM_BASE_URL="http://localhost:11434/v1"
   ```

### Using Custom Proxies or Compatible APIs

Set `base_url` in config or `LLM_BASE_URL` environment variable to point to any OpenAI-compatible API endpoint.

**Priority**: `LLM_BASE_URL` env var > config `base_url` > provider default

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please follow the coding standards defined in `.cursor/rules/`.

## Roadmap

See [mimir-ai.plan.md](mimir-ai.plan.md) for detailed implementation plan.

