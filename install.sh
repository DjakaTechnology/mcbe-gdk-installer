#!/usr/bin/env bash
set -euo pipefail

ENGINE_REPO="veedy-dev/mcbe-gdk-engine"
ENGINE_RELEASE="v0.1.0"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_ASSET="GDK-Proton-mcbe-gdk-${ENGINE_RELEASE}.tar.gz"
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

usage() {
  cat <<USAGE
Usage: $0 /path/to/decrypted/Content [--version VERSION]

The directory must contain Minecraft.Windows.exe from an authorized,
decrypted Minecraft Bedrock GDK installation. This installer does not
contain, download, decrypt, or bypass licensing for Minecraft game files.
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 2; }
CONTENT="${1%/}"; shift
VERSION="local"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="${2:?missing version}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
CONTENT="$(realpath "$CONTENT")"
[[ -f "$CONTENT/Minecraft.Windows.exe" ]] || {
  echo "Error: $CONTENT/Minecraft.Windows.exe was not found." >&2; exit 1;
}
command -v curl >/dev/null || { echo "curl is required." >&2; exit 1; }
command -v tar >/dev/null || { echo "tar is required." >&2; exit 1; }
command -v sha256sum >/dev/null || { echo "sha256sum is required." >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required." >&2; exit 1; }

mkdir -p \
  "$ROOT/engine" "$ROOT/profile" "$ROOT/lib" "$ROOT/licenses" \
  "$BIN_DIR" "$APPLICATIONS_DIR"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

MCBE_GDK_ROOT="$ROOT" BOL_HOME="$ROOT/profile" \
PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$SCRIPT_DIR/scripts/runtime.py" ensure-deps || {
    echo "Install python-cryptography with your distribution package manager." >&2
    exit 1
  }

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "$value"
}

# Known Wine/GDK workaround. Preserve the file instead of deleting it.
if [[ -f "$CONTENT/Microsoft.WindowsAppRuntime.Bootstrap.dll" ]]; then
  mv "$CONTENT/Microsoft.WindowsAppRuntime.Bootstrap.dll" \
     "$CONTENT/Microsoft.WindowsAppRuntime.Bootstrap.dll.disabled"
fi

echo "Downloading the MCBE GDK compatibility engine..."
RELEASE_URL="https://github.com/$ENGINE_REPO/releases/download/$ENGINE_RELEASE"
curl -fL --retry 3 "$RELEASE_URL/$ENGINE_ASSET" -o "$TMP/$ENGINE_ASSET"
curl -fL --retry 3 "$RELEASE_URL/$ENGINE_ASSET.sha256" -o "$TMP/$ENGINE_ASSET.sha256"
(cd "$TMP" && sha256sum -c "$ENGINE_ASSET.sha256")
rm -rf "$ROOT/engine/GDK-Proton-mcbe-gdk"
tar -xzf "$TMP/$ENGINE_ASSET" -C "$ROOT/engine"

rm -rf "$ROOT/lib/auth" "$ROOT/lib/bol"
cp -a "$SCRIPT_DIR/auth" "$ROOT/lib/auth"
install -m755 "$SCRIPT_DIR/scripts/runtime.py" "$ROOT/lib/runtime.py"
install -m755 "$SCRIPT_DIR/scripts/gui.py" "$ROOT/lib/gui.py"
install -m644 "$SCRIPT_DIR/scripts/removal.py" "$ROOT/lib/removal.py"
install -m644 "$SCRIPT_DIR/auth/LICENSE" \
  "$ROOT/licenses/BedrockOnLinux-LICENSE"
printf '%s\n' "$CONTENT" > "$ROOT/game-dir"
printf '%s\n' "$SCRIPT_DIR" > "$ROOT/source-dir"
ln -sfn "$CONTENT" "$ROOT/profile/content"

ROOT_JSON="$(json_escape "$ROOT")"
CONTENT_JSON="$(json_escape "$CONTENT")"
VERSION_JSON="$(json_escape "$VERSION")"
cat > "$ROOT/profile/settings.json" <<JSON
{
  "proton_source": "custom",
  "proton_dir": "$ROOT_JSON/engine/GDK-Proton-mcbe-gdk",
  "proton": "$ROOT_JSON/engine/GDK-Proton-mcbe-gdk",
  "proton_tag": "custom-dir",
  "game_dir": "$CONTENT_JSON",
  "mc_version": "$VERSION_JSON",
  "diagnostics": false,
  "input_backend": "x11"
}
JSON

install -m755 "$SCRIPT_DIR/scripts/launch.sh" "$BIN_DIR/mcbe-gdk-linux"
install -m755 "$SCRIPT_DIR/scripts/gui-launch.sh" "$BIN_DIR/mcbe-gdk-linux-gui"
install -m755 "$SCRIPT_DIR/scripts/auth.sh" "$BIN_DIR/mcbe-gdk-linux-auth"
install -m755 "$SCRIPT_DIR/scripts/recover.sh" "$BIN_DIR/mcbe-gdk-linux-recover"
install -m755 "$SCRIPT_DIR/scripts/rgl-env.sh" "$BIN_DIR/mcbe-gdk-linux-regolith-env"
ln -sfn "mcbe-gdk-linux-auth" "$BIN_DIR/mcbe-gdk-linux-login"
ln -sfn "mcbe-gdk-linux-auth" "$BIN_DIR/mcbe-gdk-linux-logout"
ln -sfn "mcbe-gdk-linux-auth" "$BIN_DIR/mcbe-gdk-linux-config"
ln -sfn "mcbe-gdk-linux-regolith-env" "$BIN_DIR/mcbe-gdk-linux-rgl-env"

MCBE_GDK_ROOT="$ROOT" BOL_HOME="$ROOT/profile" PYTHONPATH="$ROOT/lib" \
  python3 "$ROOT/lib/runtime.py" ensure-umu

ICON="$ROOT/mcbe-gdk-installer.png"
ICON_VALUE="applications-games"
if [[ -f "$SCRIPT_DIR/assets/mcbe-gdk-installer.png" ]]; then
  install -m644 "$SCRIPT_DIR/assets/mcbe-gdk-installer.png" "$ICON"
  ICON_VALUE="$ICON"
fi

rm -f "$APPLICATIONS_DIR/mcbe-gdk-linux.desktop"
DESKTOP="$APPLICATIONS_DIR/io.github.veedydev.MCBEGDKInstaller.desktop"
cat > "$DESKTOP" <<EOF_DESKTOP
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
EOF_DESKTOP

GAME_DESKTOP="$APPLICATIONS_DIR/io.github.veedydev.MinecraftBedrock.desktop"
cat > "$GAME_DESKTOP" <<EOF_DESKTOP
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
EOF_DESKTOP

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

echo
echo "Installed successfully."
echo "Run: mcbe-gdk-linux-gui"
echo "Microsoft/Xbox sign-in opens automatically when needed."
