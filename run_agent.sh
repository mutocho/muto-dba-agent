#!/usr/bin/env bash
cd "$(dirname "$0")"
exec uv run agent_server.py
