#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

(cd "$ROOT/mcp-router" && uv run main.py) &
ROUTER_PID=$!
(cd "$ROOT/agent" && uv run main.py) &
AGENT_PID=$!
trap "kill $ROUTER_PID $AGENT_PID 2>/dev/null" EXIT

(cd "$ROOT/ui" && uv run app.py)
