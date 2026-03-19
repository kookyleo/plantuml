#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER_DIR="$ROOT_DIR/generated-tests"

"$ROOT_DIR/gradlew" --project-dir "$ROOT_DIR" --no-daemon jar

python3 "$ROOT_DIR/tools/generate_junit_skeletons.py" \
  --classes-dir "$ROOT_DIR/build/classes/java/main" \
  --output-dir "$RUNNER_DIR/src/test/java" \
  --report-dir "$RUNNER_DIR/build/reports/test-skeletons"

"$ROOT_DIR/gradlew" --project-dir "$RUNNER_DIR" --no-daemon test "$@"
