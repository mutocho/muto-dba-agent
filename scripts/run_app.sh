#!/usr/bin/env bash
cd "$(dirname "$0")/../ui"
exec uv run app.py
