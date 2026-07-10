#!/usr/bin/env bash
cd "$(dirname "$0")"
uv run agent_server.py &
AGENT_PID=$!
trap "kill $AGENT_PID 2>/dev/null" EXIT
uv run app.py
