#!/usr/bin/env bash
set -euo pipefail

ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
export MCBE_GDK_ROOT="$ROOT"
export BOL_HOME="$ROOT/profile"
export PYTHONPATH="$ROOT/lib"
LOCK="$BOL_HOME/.desktop-launch.lock"

mkdir -p "$BOL_HOME"
exec 9>"$LOCK"
flock -n 9 || {
  echo "Minecraft is starting or running; try again after it closes." >&2
  exit 1
}

case "$(basename "$0")" in
  *-login|*-config) set -- login "$@" ;;
  *-logout) set -- logout "$@" ;;
esac

if (($# == 0)); then
  set -- status
fi
exec python3 "$ROOT/lib/runtime.py" "$@"
