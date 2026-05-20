#!/bin/bash
# Setup script for Agent Memory Fabric
# Creates virtual environment and installs all dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Agent Memory Fabric Setup ==="
echo "Project: $PROJECT_DIR"
echo ""

# Check Python version
PYTHON=${PYTHON:-python3}
PY_VERSION=$($PYTHON --version 2>&1)
echo "Python: $PY_VERSION"

# Option 1: Use uv (recommended, faster)
if command -v uv &> /dev/null; then
    echo "Using uv (recommended)..."
    uv sync --extra full --extra dev
    echo ""
    echo "Done! Run commands with: uv run python -m ..."
    echo "  Example: uv run python -m benchmarks.run_experiment --synthetic"
    echo "  Tests:   uv run pytest tests/ -v"
    exit 0
fi

# Option 2: Traditional venv
echo "uv not found, using traditional venv..."
$PYTHON -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[full,dev]"

echo ""
echo "Done! Activate the environment with:"
echo "  source .venv/bin/activate"
echo ""
echo "Then run:"
echo "  python -m benchmarks.run_experiment --synthetic"
echo "  pytest tests/ -v"
