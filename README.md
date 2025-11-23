# Mimir

<div align="center">

**Drink from the well of knowledge in the AI era**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Test Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](https://github.com/rpings/Mimir)

An intelligent AI intelligence collection and organization system that automates the collection, processing, and archiving of important information in the AI field.

[Features](#-features) • [Quick Start](#-quick-start) • [Configuration](#-configuration) • [Documentation](#-documentation)

</div>

---

## ✨ Features

### 🔍 Multi-Source Collection
- **RSS Feeds**: Collect from multiple RSS sources (blogs, papers, releases)
- **YouTube Channels**: Monitor YouTube channels via RSS feeds
- **Twitter/X**: Placeholder for Twitter API integration (requires API v2 credentials)
- **Extensible Architecture**: Easy to add new collectors via `BaseCollector` interface

### 🧠 Intelligent Processing
- **Keyword Classification**: Rule-based topic and priority classification
- **LLM Enhancement** (Optional):
  - Content summarization
  - Multi-language translation
  - Smart categorization
  - Cost tracking and budget controls
- **Hybrid Processing**: Combines keyword and LLM for best results
- **Graceful Degradation**: Falls back to keyword processing if LLM is unavailable

### 🚀 Performance & Scalability
- **Async Processing**: Concurrent collection and processing for better performance
- **Caching**: Local cache for deduplication and LLM result caching
- **Concurrent Execution**: Process multiple sources and entries in parallel
- **Resource Management**: Configurable concurrency limits

### 💾 Storage & Integration
- **Notion Integration**: Sync structured data to Notion databases
- **DingTalk Notifications**: Send notifications to DingTalk webhooks
- **Deduplication**: URL-based and semantic deduplication
- **Data Validation**: Pydantic models for type safety and validation

### 🛡️ Reliability
- **Error Handling**: Graceful failure handling with retry mechanisms
- **Budget Controls**: Daily and monthly LLM cost limits
- **Comprehensive Testing**: 94% test coverage with 187+ tests
- **Logging**: Structured logging with loguru

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Notion account and database (for storage)
- (Optional) OpenAI API key (for LLM features)
- (Optional) DingTalk webhook URL (for notifications)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/rpings/Mimir.git
   cd Mimir
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   Or use the provided run script:
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

3. **Configure environment variables:**
   ```bash
   export NOTION_TOKEN="your_notion_token"
   export NOTION_DATABASE_ID="your_database_id"
   
   # Optional: For LLM features
   export OPENAI_API_KEY="sk-..."
   export LLM_BASE_URL="http://localhost:11434/v1"  # For local models
   
   # Optional: For DingTalk notifications
   export DINGTALK_WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=..."
   export DINGTALK_SECRET="your_secret"  # Optional
   ```

4. **Configure sources:**
   - Edit `configs/sources/rss.yaml` to add RSS feeds
   - Edit `configs/sources/youtube.yaml` to add YouTube channels (optional)
   - Edit `configs/sources/rules.yaml` to customize classification rules

5. **Run:**
   ```bash
   # Sync mode (default)
   python main.py
   
   # Or async mode (faster, recommended for multiple sources)
   python main_async.py
   
   # Or use the run script
   ./run.sh          # Sync mode
   ./run.sh async    # Async mode
   ```

## 📖 Configuration

### Main Configuration (`configs/config.yml`)

```yaml
# Timezone
timezone: Asia/Shanghai

# Notion Integration
notion:
  database_id: ${NOTION_DATABASE_ID}  # From environment variable
  field_names:
    title: "Title"
    source_type: "Source Type"
    link: "Link"
    date: "Date"
    priority: "Priority"
    topics: "Topics"
    status: "Status"

# Processing Settings
processing:
  enable_keyword_classification: true
  deduplication:
    method: url  # url, semantic, both

# LLM Configuration (Optional)
llm:
  enabled: false  # Must be explicitly enabled
  provider: openai  # openai, anthropic, etc.
  model: gpt-4o-mini  # Recommended for cost efficiency
  base_url: null  # Optional: Custom API base URL
  daily_limit: 5.0  # USD per day
  monthly_budget: 50.0  # USD per month
  features:
    summarization: true
    translation: true
    smart_categorization: true
  translation:
    target_languages: ["zh", "en"]
  cache:
    enabled: true
    path: ./data/llm_cache
    ttl_days: 30

# Cache Settings
cache:
  enabled: true
  path: ./data/cache
  ttl_days: 30

# Retry Settings
retry:
  max_attempts: 3
  backoff_factor: 2

# DingTalk Notifications (Optional)
dingtalk:
  enabled: false
  webhook_url: ${DINGTALK_WEBHOOK_URL}
  secret: ${DINGTALK_SECRET}  # Optional
```

### Source Configuration

**RSS Sources** (`configs/sources/rss.yaml`):
```yaml
feeds:
  - name: OpenAI Blog
    url: https://openai.com/blog/rss
    source_type: blog
  - name: arXiv cs.AI
    url: https://export.arxiv.org/rss/cs.AI
    source_type: 论文
```

**YouTube Channels** (`configs/sources/youtube.yaml`):
```yaml
channels:
  - name: Two Minute Papers
    channel_id: UCbfYPyITQ-7l4upoX8nvctg
    source_type: video
```

**Classification Rules** (`configs/sources/rules.yaml`):
```yaml
topics:
  AI: ["artificial intelligence", "machine learning", "deep learning"]
  RAG: ["retrieval", "rag", "retrieval-augmented"]
priority:
  High: ["release", "breaking", "announcement"]
  Medium: ["beta", "preview", "update"]
```

## 🏗️ Architecture

```
Mimir/
├── .github/workflows/    # GitHub Actions automation
├── .cursor/rules/        # Project coding standards
├── src/
│   ├── collectors/       # Data collection (RSS, YouTube, Twitter)
│   │   ├── base_collector.py
│   │   ├── rss_collector.py
│   │   ├── youtube_collector.py
│   │   └── twitter_collector.py
│   ├── processors/       # Content processing
│   │   ├── base_processor.py
│   │   ├── keyword_processor.py
│   │   ├── llm_processor.py
│   │   ├── processor_pipeline.py
│   │   └── deduplicator.py
│   ├── storages/         # Data persistence
│   │   ├── base_storage.py
│   │   ├── notion_client.py
│   │   ├── dingtalk_client.py
│   │   ├── cache_manager.py
│   │   └── llm_cache.py
│   └── utils/            # Utilities
│       ├── config_loader.py
│       ├── cost_tracker.py
│       ├── logger.py
│       └── retry_handler.py
├── configs/              # Configuration files
│   ├── config.yml
│   └── sources/
│       ├── rss.yaml
│       ├── youtube.yaml
│       ├── twitter.yaml
│       └── rules.yaml
├── tests/                # Test suite (94% coverage)
├── main.py               # Sync entry point
├── main_async.py         # Async entry point (recommended)
├── run.sh                # Convenience run script
└── requirements.txt      # Dependencies
```

### Design Principles

- **Interface-Based**: Abstract base classes for extensibility
- **Dependency Injection**: Pass dependencies through constructors
- **Type Safety**: Pydantic models for validation
- **Error Handling**: Graceful failures with retry mechanisms
- **Testability**: High test coverage with comprehensive test suite

## 💰 Cost Considerations

### Without LLM (Default)
- **Cost**: $0 (GitHub Actions free tier)
- **Processing**: Keyword-based classification only

### With LLM Features
- **Estimated Cost**: $30-150/month (depending on usage)
  - GPT-4o-mini: ~$0.15 per 1M input tokens, ~$0.6 per 1M output tokens
  - Typical article: ~500-2000 tokens per feature
- **Budget Controls**:
  - Daily limits (default: $5/day)
  - Monthly budget (default: $50/month)
  - Automatic cost tracking and persistence
  - Budget enforcement before API calls
- **Local Models**: Use `base_url` to point to local model servers (Ollama, vLLM) for $0 cost

## 🔧 LLM Setup

### Using OpenAI

1. Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)
2. Set environment variable:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```
3. Enable in `configs/config.yml`:
   ```yaml
   llm:
     enabled: true
     provider: openai
     model: gpt-4o-mini
   ```

### Using Local Models (Ollama, vLLM, etc.)

1. Start your local model server:
   ```bash
   # Example: Ollama
   ollama serve
   ```

2. Configure in `configs/config.yml`:
   ```yaml
   llm:
     enabled: true
     provider: openai  # Use 'openai' for OpenAI-compatible APIs
     model: llama3  # Your local model name
     base_url: "http://localhost:11434/v1"
   ```

   Or use environment variable:
   ```bash
   export LLM_BASE_URL="http://localhost:11434/v1"
   ```

### Using Custom Proxies or Compatible APIs

Set `base_url` in config or `LLM_BASE_URL` environment variable to point to any OpenAI-compatible API endpoint.

**Priority**: `LLM_BASE_URL` env var > config `base_url` > provider default

## 🧪 Development

### Setup Development Environment

```bash
# Clone and setup
git clone https://github.com/rpings/Mimir.git
cd Mimir
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov pytest-asyncio black isort ruff mypy
```

### Code Style

- Follow **PEP 8** strictly
- Use **type hints** for all functions
- Maximum line length: **88 characters** (Black formatter)
- See `.cursor/rules/` for detailed coding standards

### Running Tests

```bash
# Run all tests
pytest tests/

# With coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_collectors.py -v
```

### Code Quality Tools

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## 📊 Project Status

- ✅ **Multi-source collection** (RSS, YouTube, Twitter placeholder)
- ✅ **Keyword-based classification**
- ✅ **LLM enhancement** (summarization, translation, categorization)
- ✅ **Async processing** for performance
- ✅ **Notion integration**
- ✅ **DingTalk notifications**
- ✅ **Cost tracking and budget controls**
- ✅ **Comprehensive testing** (94% coverage, 187+ tests)
- ✅ **GitHub Actions automation**

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Follow coding standards**: See `.cursor/rules/` for details
4. **Write tests**: Ensure new code has test coverage
5. **Commit changes**: Use [Conventional Commits](https://www.conventionalcommits.org/)
6. **Push to branch**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

### Coding Standards

- All code, comments, and documentation in **English**
- Follow **PEP 8** style guide
- Use **type hints** for all functions
- Write **docstrings** (Google style)
- Maintain **test coverage** above 80%

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by the need for automated AI intelligence collection
- Built with modern Python best practices
- Uses excellent open-source libraries: `pydantic`, `langchain`, `litellm`, `loguru`, `diskcache`

## 📚 Documentation

- **Architecture**: See `.cursor/rules/03-architecture.mdc`
- **Code Style**: See `.cursor/rules/02-code-style.mdc`
- **Testing**: See `.cursor/rules/05-testing.mdc`
- **Error Handling**: See `.cursor/rules/04-error-handling.mdc`

---

<div align="center">

**Made with ❤️ for the AI community**

[Report Bug](https://github.com/rpings/Mimir/issues) • [Request Feature](https://github.com/rpings/Mimir/issues) • [Contribute](https://github.com/rpings/Mimir/pulls)

</div>
