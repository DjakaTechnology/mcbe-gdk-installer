#!/usr/bin/env bash
set -euo pipefail
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
export BOL_HOME="$ROOT/profile"
export PROTON_USE_WOW64=1
exec "$HOME/.local/opt/bedrock-on-linux/BedrockOnLinux.AppImage" gui "$@"
