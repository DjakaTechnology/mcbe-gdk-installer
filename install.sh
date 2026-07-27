#!/usr/bin/env bash
set -euo pipefail

REPO="veedy-dev/mcbe-gdk-linux"
RELEASE="v0.1.0"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BOL_VERSION="2.1.1"
BOL_ASSET="BedrockOnLinux-${BOL_VERSION}-x86_64.AppImage"
ENGINE_ASSET="GDK-Proton-mcbe-gdk-native12.tar.gz"
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/opt/bedrock-on-linux"
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

mkdir -p "$ROOT/engine" "$ROOT/profile" "$BIN_DIR" "$APP_DIR" "$APPLICATIONS_DIR"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

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

echo "Downloading BedrockOnLinux ${BOL_VERSION}..."
curl -fL --retry 3 \
  "https://github.com/Wyze3306/BedrockOnLinux/releases/download/v${BOL_VERSION}/${BOL_ASSET}" \
  -o "$APP_DIR/$BOL_ASSET"
curl -fL --retry 3 \
  "https://github.com/Wyze3306/BedrockOnLinux/releases/download/v${BOL_VERSION}/BedrockOnLinux-${BOL_VERSION}-SHA256SUMS" \
  -o "$TMP/bol.sha256"
EXPECTED="$(awk -v f="$BOL_ASSET" '$2==f || $2=="*"f {print $1; exit}' "$TMP/bol.sha256")"
[[ -n "$EXPECTED" ]] || { echo "Could not find BOL checksum." >&2; exit 1; }
echo "$EXPECTED  $APP_DIR/$BOL_ASSET" | sha256sum -c -
chmod +x "$APP_DIR/$BOL_ASSET"
ln -sfn "$BOL_ASSET" "$APP_DIR/BedrockOnLinux.AppImage"

echo "Downloading the MCBE GDK compatibility engine..."
RELEASE_URL="https://github.com/$REPO/releases/download/$RELEASE"
curl -fL --retry 3 "$RELEASE_URL/$ENGINE_ASSET" -o "$TMP/$ENGINE_ASSET"
curl -fL --retry 3 "$RELEASE_URL/$ENGINE_ASSET.sha256" -o "$TMP/$ENGINE_ASSET.sha256"
(cd "$TMP" && sha256sum -c "$ENGINE_ASSET.sha256")
rm -rf "$ROOT/engine/GDK-Proton-mcbe-gdk"
tar -xzf "$TMP/$ENGINE_ASSET" -C "$ROOT/engine"

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
install -m755 "$SCRIPT_DIR/scripts/configure.sh" "$BIN_DIR/mcbe-gdk-linux-config"
install -m755 "$SCRIPT_DIR/scripts/recover.sh" "$BIN_DIR/mcbe-gdk-linux-recover"
install -m755 "$SCRIPT_DIR/scripts/rgl-env.sh" "$BIN_DIR/mcbe-gdk-linux-regolith-env"
ln -sfn "mcbe-gdk-linux-regolith-env" "$BIN_DIR/mcbe-gdk-linux-rgl-env"

cat > "$APPLICATIONS_DIR/mcbe-gdk-linux.desktop" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Name=MCBE GDK Linux
Comment=Authorized Minecraft Bedrock GDK build using GDK-Proton
Exec=$BIN_DIR/mcbe-gdk-linux
Icon=minecraft
Terminal=false
Categories=Game;
StartupNotify=false
EOF_DESKTOP

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo
echo "Installed successfully."
echo "1. Run: mcbe-gdk-linux-config"
echo "2. Choose Sign In and authenticate your authorized Microsoft/Xbox account."
echo "3. Run: mcbe-gdk-linux"
echo "For Regolith/rgl: source <(mcbe-gdk-linux-regolith-env)"
