#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"
TARGET_ZSHRC="${TARGET_ZSHRC:-$HOME/.zshrc}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for required in OPENAI_API_KEY AGENTOPS_API_KEY RABBITMQ_URL; do
  if [[ -z "${!required:-}" ]]; then
    echo "Missing required variable in $ENV_FILE: $required" >&2
    exit 1
  fi
done

export TARGET_ZSHRC OPENAI_API_KEY AGENTOPS_API_KEY RABBITMQ_URL
python3 - <<'PY'
import os
import re
import shlex
from pathlib import Path

target = Path(os.environ["TARGET_ZSHRC"]).expanduser()
target.parent.mkdir(parents=True, exist_ok=True)
text = target.read_text(encoding="utf-8") if target.exists() else ""

updates = {
    "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
    "AGENTOPS_API_KEY": os.environ["AGENTOPS_API_KEY"],
    "RABBITMQ_URL": os.environ["RABBITMQ_URL"],
}

for key, value in updates.items():
    line = f"export {key}={shlex.quote(value)}"
    pattern = re.compile(rf"(?m)^export {re.escape(key)}=.*$")
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"

target.write_text(text, encoding="utf-8")
PY

echo "Synced demo shell variables from $ENV_FILE into $TARGET_ZSHRC"
echo "  - OPENAI_API_KEY"
echo "  - AGENTOPS_API_KEY"
echo "  - RABBITMQ_URL"
