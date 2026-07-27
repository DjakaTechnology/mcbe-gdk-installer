#!/usr/bin/env bash
set -euo pipefail

ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
export BOL_HOME="$ROOT/profile"
APP="$HOME/.local/opt/bedrock-on-linux/BedrockOnLinux.AppImage"
MARKER="$BOL_HOME/.gpu-launch-in-progress.json"

[[ -x "$APP" ]] || {
  echo "BedrockOnLinux is missing; rerun install.sh." >&2
  exit 1
}

if [[ -f "$MARKER" ]]; then
  current_boot="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
  marker_boot="$(
    grep -o '"boot_id":"[^"]*"' "$MARKER" 2>/dev/null |
      head -1 | cut -d'"' -f4 || true
  )"
  if [[ -n "$current_boot" && "$marker_boot" == "$current_boot" ]]; then
    echo "Recovery is intentionally blocked during the same boot." >&2
    echo "Reboot Linux once, then run mcbe-gdk-linux-recover again." >&2
    exit 1
  fi
fi

exec "$APP" doctor --acknowledge-gpu-crash
