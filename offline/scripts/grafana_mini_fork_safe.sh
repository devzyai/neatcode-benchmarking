#!/usr/bin/env bash
# Grafana mini step 0 with defaults that avoid parallel git push timeouts and make
# upstream clones persistent (same flags we recommend for first-time / flaky networks).
# Override clone parent: UPSTREAM_CLONE_DIR=/path ./scripts/grafana_mini_fork_safe.sh ...
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec ./scripts/grafana_mini_fork.sh \
  --upstream-clone-dir "${UPSTREAM_CLONE_DIR:-./upstream_clone}" \
  --prepare-concurrency 1 \
  --pr-open-concurrency 1 \
  "$@"
