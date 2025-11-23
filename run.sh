#!/bin/bash
# Mimir Run Script
# Supports both sync and async execution modes

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default mode (sync or async)
MODE="${1:-sync}"

echo -e "${GREEN}Mimir - AI Intelligence Collection System${NC}"
echo "=========================================="

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}Error: Python 3.11+ required, found $PYTHON_VERSION${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate

# Upgrade pip
echo -e "${GREEN}Upgrading pip...${NC}"
pip install --quiet --upgrade pip

# Install dependencies
echo -e "${GREEN}Installing dependencies...${NC}"
pip install --quiet -r requirements.txt

# Check required environment variables
if [ -z "$NOTION_TOKEN" ] || [ -z "$NOTION_DATABASE_ID" ]; then
    echo -e "${RED}Error: NOTION_TOKEN and NOTION_DATABASE_ID must be set${NC}"
    echo ""
    echo "Required environment variables:"
    echo "  NOTION_TOKEN=your_token"
    echo "  NOTION_DATABASE_ID=your_database_id"
    echo ""
    echo "Optional (for LLM features):"
    echo "  OPENAI_API_KEY=sk-...          # For OpenAI API"
    echo "  LLM_MODEL=gpt-4o-mini          # Model name (overrides config)"
    echo "  LLM_BASE_URL=http://...        # For local models or custom APIs"
    echo ""
    echo "You can set them in .env file or export them:"
    echo "  export NOTION_TOKEN=your_token"
    echo "  export NOTION_DATABASE_ID=your_database_id"
    echo "  export OPENAI_API_KEY=sk-...  # Optional"
    echo "  export LLM_MODEL=gpt-4o-mini  # Optional, overrides config"
    echo "  export LLM_BASE_URL=http://localhost:11434/v1  # Optional"
    echo ""
    echo "Or create a .env file:"
    echo "  NOTION_TOKEN=your_token"
    echo "  NOTION_DATABASE_ID=your_database_id"
    echo "  OPENAI_API_KEY=sk-...  # Optional"
    echo "  LLM_MODEL=gpt-4o-mini  # Optional, overrides config"
    echo "  LLM_BASE_URL=http://localhost:11434/v1  # Optional"
    exit 1
fi

# Check optional LLM environment variables
if [ -n "$OPENAI_API_KEY" ] || [ -n "$LLM_BASE_URL" ] || [ -n "$LLM_MODEL" ]; then
    echo -e "${GREEN}LLM features detected${NC}"
    if [ -n "$LLM_MODEL" ]; then
        echo "  Model: $LLM_MODEL (from environment variable)"
    fi
    if [ -n "$LLM_BASE_URL" ]; then
        echo "  Base URL: $LLM_BASE_URL (from environment variable)"
    fi
    echo "  Make sure to enable LLM in configs/config.yml:"
    echo "    llm:"
    echo "      enabled: true"
else
    echo -e "${YELLOW}LLM features not configured (using keyword processing only)${NC}"
    echo "  To enable LLM features, set OPENAI_API_KEY, LLM_MODEL, or LLM_BASE_URL"
fi

# Run Mimir
echo ""
echo -e "${GREEN}Running Mimir in ${MODE} mode...${NC}"
echo "=========================================="

if [ "$MODE" = "async" ]; then
    if [ -f "main_async.py" ]; then
        python main_async.py
    else
        echo -e "${YELLOW}Warning: main_async.py not found, falling back to sync mode${NC}"
        python main.py
    fi
else
    python main.py
fi

echo ""
echo -e "${GREEN}Done!${NC}"

