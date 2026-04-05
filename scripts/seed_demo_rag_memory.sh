#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="${1:-$ROOT}"
FIXTURE="$ROOT/tests/fixtures/rag/buf1_leaf_memory.json"
TARGET_DIR="$WORKSPACE/artifacts/rag"
TARGET_FILE="$TARGET_DIR/memory.json"

mkdir -p "$TARGET_DIR"
cp "$FIXTURE" "$TARGET_FILE"

cat <<EOF
Seeded curated demo RAG memory at:
  $TARGET_FILE

Source fixture:
  $FIXTURE
EOF
