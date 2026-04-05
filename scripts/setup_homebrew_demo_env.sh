#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="${1:-$HOME/Desktop/mhd-homebrew-demo}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}/mhd"
RAG_FIXTURE="$ROOT/tests/fixtures/rag/buf1_leaf_memory.json"

mkdir -p "$WORKSPACE"
rm -rf "$WORKSPACE/artifacts"
mkdir -p "$WORKSPACE/artifacts/rag"

cp "$ROOT/tests/test_specs/01_counter3_basic.txt" "$WORKSPACE/01_counter3_basic.txt"
cp "$ROOT/tests/test_specs/demo_inv1_wrapper_multimodule.txt" "$WORKSPACE/demo_inv1_wrapper_multimodule.txt"
cp "$RAG_FIXTURE" "$WORKSPACE/artifacts/rag/memory.json"
if [[ -f "$ROOT/artifacts/tmp/demo_bad_counter3_spec.txt" ]]; then
  cp "$ROOT/artifacts/tmp/demo_bad_counter3_spec.txt" "$WORKSPACE/demo_bad_counter3_spec.txt"
fi

cat <<EOF
Demo workspace prepared at:
  $WORKSPACE

Curated RAG memory seeded at:
  $WORKSPACE/artifacts/rag/memory.json

Installed mhd will seed its user config on first run at:
  $CONFIG_HOME

Standard shell setup:
  echo 'export OPENAI_API_KEY=...' >> ~/.zshrc
  echo 'export RABBITMQ_URL=amqp://guest:guest@localhost:5672/' >> ~/.zshrc
  exec zsh -l

Verification:
  brew services start rabbitmq
  mhd doctor
  mhd doctor --benchmark

Clean demo commands:
  cd "$WORKSPACE"
  mhd --spec-file 01_counter3_basic.txt --rag off --yes --narrative-mode deterministic --run-name demo_counter_det
  mhd --spec-file demo_inv1_wrapper_multimodule.txt --rag on --yes --narrative-mode llm --run-name demo_multimodule_buf_llm
  mhd benchmark list-problems --max-problems 10

Advanced overrides:
  MHD_ENV_FILE=/absolute/path/to/.env mhd doctor
  mhd --config "$CONFIG_HOME/runtime.yaml" ...
EOF
