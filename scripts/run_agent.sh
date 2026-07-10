#!/usr/bin/env bash
cd "$(dirname "$0")/../agent"
exec uv run main.py
