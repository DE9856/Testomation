#!/usr/bin/env bash
# Spike: run the kill-rate benchmark (menu.py) for each given model, one after another.
# Usage: spike/bakeoff.sh model [model ...]   → spike/results/menu_<model>/summary.json each
set -u
cd "$(dirname "$0")/.."
for m in "$@"; do
  echo "=== $m $(date +%H:%M)"
  uv run python spike/menu.py "$m" 2>&1 | grep -E "kill rate|Traceback|Error:" | head -5
done
echo "=== done $(date +%H:%M)"
