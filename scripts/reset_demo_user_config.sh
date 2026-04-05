#!/usr/bin/env bash
set -euo pipefail

CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/mhd"

if [[ -d "$CONFIG_ROOT" ]]; then
  backup_path="${CONFIG_ROOT}.demo-backup-$(date +%Y%m%d-%H%M%S)"
  mv "$CONFIG_ROOT" "$backup_path"
  echo "Backed up existing user config:"
  echo "  $CONFIG_ROOT"
  echo "to:"
  echo "  $backup_path"
else
  echo "No existing user config to back up at:"
  echo "  $CONFIG_ROOT"
fi

echo
echo "Next mhd command will seed a fresh config tree at:"
echo "  $CONFIG_ROOT"
