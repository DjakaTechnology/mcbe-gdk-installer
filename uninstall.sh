#!/usr/bin/env bash
set -euo pipefail
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
rm -f "$HOME/.local/bin/mcbe-gdk-linux" \
      "$HOME/.local/bin/mcbe-gdk-linux-gui" \
      "$HOME/.local/bin/mcbe-gdk-linux-auth" \
      "$HOME/.local/bin/mcbe-gdk-linux-login" \
      "$HOME/.local/bin/mcbe-gdk-linux-logout" \
      "$HOME/.local/bin/mcbe-gdk-linux-config" \
      "$HOME/.local/bin/mcbe-gdk-linux-recover" \
      "$HOME/.local/bin/mcbe-gdk-linux-regolith-env" \
      "$HOME/.local/bin/mcbe-gdk-linux-rgl-env" \
"${XDG_DATA_HOME:-$HOME/.local/share}/applications/mcbe-gdk-linux.desktop"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.veedydev.MCBEGDKInstaller.desktop"
echo "Launchers removed. Runtime/profile remains at: $ROOT"
echo "Delete it manually if you also want to remove Xbox session data and the engine."
