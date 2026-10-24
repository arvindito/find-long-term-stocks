#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment in $DIR/.venv..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

PORT="${PORT:-8050}"
echo "=================================================================="
echo "  AlphaTerminal — Equity Research & Valuation Command Center"
echo "  URL: http://127.0.0.1:${PORT}"
echo "  DB : ../stock-sweeper/market_data.db (Read-Only URI ?mode=ro)"
echo "=================================================================="

exec .venv/bin/uvicorn app:app --host 127.0.0.1 --port "$PORT"
