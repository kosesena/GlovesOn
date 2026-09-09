#!/usr/bin/env bash
# Publish the agent. Works from any tab.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python agent/publish.py "$@"
