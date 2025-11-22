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

### Phase 2 (LLM Enhancement) - Planned
- 🔄 LLM-powered content summarization
- 🔄 Intelligent translation
- 🔄 Smart categorization
- 🔄 Cost monitoring and budget controls

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
  enable_llm: false  # Phase 1: false, Phase 2: optional
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
- **Controls**: Daily limits, monthly budget, caching
- **Default**: LLM features disabled by default

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please follow the coding standards defined in `.cursor/rules/`.

## Roadmap

See [mimir-ai.plan.md](mimir-ai.plan.md) for detailed implementation plan.

