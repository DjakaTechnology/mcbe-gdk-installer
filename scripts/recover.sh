#!/usr/bin/env bash
set -euo pipefail

ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
export MCBE_GDK_ROOT="$ROOT"
export BOL_HOME="$ROOT/profile"
export PYTHONPATH="$ROOT/lib"
RUNTIME="$ROOT/lib/runtime.py"
LOCK="$BOL_HOME/.desktop-launch.lock"

[[ -f "$RUNTIME" ]] || {
  echo "MCBE GDK Installer runtime is missing; rerun install.sh." >&2
  exit 1
}

mkdir -p "$BOL_HOME"
exec 9>"$LOCK"
flock -n 9 || {
  echo "Minecraft is starting or running; recovery is blocked." >&2
  exit 1
}

exec python3 "$RUNTIME" gpu-recover
