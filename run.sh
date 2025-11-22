#!/bin/bash
# Simple run script for Mimir

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check environment variables
if [ -z "$NOTION_TOKEN" ] || [ -z "$NOTION_DATABASE_ID" ]; then
    echo "Warning: NOTION_TOKEN and NOTION_DATABASE_ID must be set"
    echo "You can set them in .env file or export them:"
    echo "  export NOTION_TOKEN=your_token"
    echo "  export NOTION_DATABASE_ID=your_database_id"
    exit 1
fi

# Run Mimir
echo "Running Mimir..."
python main.py

