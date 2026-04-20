#!/usr/bin/env bash
# Grafana mini step 0: first 5 PRs from golden_grafana_only/ (run from offline/ or via path below).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec uv run python -m code_review_benchmark.step0_orchestrate_forks \
  --golden-dir golden_grafana_only \
  --repos 1 \
  --prs-per-repo 5 \
  "$@"
