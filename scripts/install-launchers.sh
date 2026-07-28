#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:?usage: install-launchers.sh ROOT SOURCE}"
SOURCE="${2:?usage: install-launchers.sh ROOT SOURCE}"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$ROOT/lib" "$ROOT/licenses" "$BIN_DIR" "$APPLICATIONS_DIR"
rm -rf "$ROOT/lib/auth" "$ROOT/lib/bol"
cp -a "$SOURCE/auth" "$ROOT/lib/auth"
install -m755 "$SOURCE/scripts/runtime.py" "$ROOT/lib/runtime.py"
install -m755 "$SOURCE/scripts/gui.py" "$ROOT/lib/gui.py"
install -m755 "$SOURCE/scripts/updates.py" "$ROOT/lib/updates.py"
install -m644 "$SOURCE/scripts/removal.py" "$ROOT/lib/removal.py"
install -m644 "$SOURCE/auth/LICENSE" "$ROOT/licenses/BedrockOnLinux-LICENSE"
printf '%s\n' "$SOURCE" >"$ROOT/source-dir"

install -m755 "$SOURCE/scripts/launch.sh" "$BIN_DIR/mcbe-gdk-linux"
install -m755 "$SOURCE/scripts/gui-launch.sh" "$BIN_DIR/mcbe-gdk-linux-gui"
install -m755 "$SOURCE/scripts/auth.sh" "$BIN_DIR/mcbe-gdk-linux-auth"
install -m755 "$SOURCE/scripts/recover.sh" "$BIN_DIR/mcbe-gdk-linux-recover"
install -m755 "$SOURCE/scripts/rgl-env.sh" "$BIN_DIR/mcbe-gdk-linux-regolith-env"
ln -sfn "mcbe-gdk-linux-auth" "$BIN_DIR/mcbe-gdk-linux-login"
ln -sfn "mcbe-gdk-linux-auth" "$BIN_DIR/mcbe-gdk-linux-logout"
ln -sfn "mcbe-gdk-linux-auth" "$BIN_DIR/mcbe-gdk-linux-config"
ln -sfn "mcbe-gdk-linux-regolith-env" "$BIN_DIR/mcbe-gdk-linux-rgl-env"

ICON="$ROOT/mcbe-gdk-installer.png"
ICON_VALUE="applications-games"
if [[ -f "$SOURCE/assets/mcbe-gdk-installer.png" ]]; then
  install -m644 "$SOURCE/assets/mcbe-gdk-installer.png" "$ICON"
  ICON_VALUE="$ICON"
fi

rm -f "$APPLICATIONS_DIR/mcbe-gdk-linux.desktop"
cat >"$APPLICATIONS_DIR/io.github.veedydev.MCBEGDKInstaller.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MCBE GDK Installer
GenericName=Minecraft Bedrock GDK Installer
Comment=Install, authenticate, and launch Minecraft Bedrock GDK builds on Linux
Exec=$BIN_DIR/mcbe-gdk-linux-gui
Icon=$ICON_VALUE
Terminal=false
Categories=Game;
Keywords=Minecraft;Bedrock;GDK;Xbox;Installer;Linux;
X-KDE-Keywords=minecraft,bedrock,gdk,xbox,installer
StartupNotify=true
StartupWMClass=io.github.veedydev.MCBEGDKInstaller
EOF

cat >"$APPLICATIONS_DIR/io.github.veedydev.MinecraftBedrock.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Minecraft Bedrock
Comment=Launch Minecraft Bedrock
Exec=$BIN_DIR/mcbe-gdk-linux
Icon=$ICON_VALUE
Terminal=false
Categories=Game;
Keywords=Minecraft;Bedrock;Xbox;Game;
StartupNotify=true
EOF

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi
