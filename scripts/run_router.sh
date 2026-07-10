#!/usr/bin/env bash
cd "$(dirname "$0")/../mcp-router"
exec uv run main.py
