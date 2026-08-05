#!/usr/bin/env bash
set -euo pipefail
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/mcbe-gdk-linux"
BASE="$ROOT/profile/compatdata/pfx/drive_c/users/steamuser/AppData/Roaming/Minecraft Bedrock/Users/Shared/games/com.mojang"
mkdir -p "$BASE"

case "${1:-}" in
  "")
    printf 'export COM_MOJANG=%q\n' "$BASE"
    ;;
  --fish)
    escaped="${BASE//\\/\\\\}"
    escaped="${escaped//\'/\\\'}"
    printf "set -gx COM_MOJANG '%s'\n" "$escaped"
    ;;
  -h|--help)
    printf 'Usage: %s [--fish]\n' "$(basename "$0")"
    ;;
  *)
    printf 'Unknown argument: %s\n' "$1" >&2
    exit 2
    ;;
esac
