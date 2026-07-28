#!/usr/bin/env bash
set -euo pipefail

REPO="veedy-dev/mcbe-gdk-installer"
SOURCE_DIR="${MCBE_GDK_SOURCE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mcbe-gdk-installer/source}"

run_root() {
  if (( EUID == 0 )); then
    "$@"
  elif command -v sudo >/dev/null; then
    sudo "$@"
  else
    echo "sudo is required to install dependencies." >&2
    exit 1
  fi
}

dependencies_ready() {
  local command
  for command in python3 curl tar unzip 7z sha256sum flock; do
    command -v "$command" >/dev/null || return 1
  done
  python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
from cryptography.fernet import Fernet
PY
}

install_dependencies() {
  echo "Installing system dependencies..."
  if command -v pacman >/dev/null; then
    run_root pacman -S --needed \
      gtk4 libadwaita python python-gobject python-cryptography \
      qrencode curl tar unzip 7zip
  elif command -v dnf >/dev/null; then
    run_root dnf install -y \
      gtk4 libadwaita python3 python3-gobject python3-cryptography \
      qrencode curl tar unzip p7zip p7zip-plugins
  elif command -v apt-get >/dev/null; then
    run_root apt-get update
    run_root apt-get install -y \
      python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
      python3-cryptography qrencode curl tar unzip 7zip
  else
    echo "Unsupported package manager. Install the dependencies listed at:" >&2
    echo "https://github.com/$REPO#requirements" >&2
    exit 1
  fi
}

[[ "$(uname -m)" == "x86_64" ]] || {
  echo "MCBE GDK Installer currently requires x86_64 Linux." >&2
  exit 1
}

dependencies_ready || install_dependencies
dependencies_ready || {
  echo "Required dependencies are still missing." >&2
  exit 1
}

parent="$(dirname "$SOURCE_DIR")"
mkdir -p "$parent"
stage="$(mktemp -d "$parent/.bootstrap.XXXXXX")"
trap 'rm -rf "$stage"' EXIT

echo "Downloading MCBE GDK Installer..."
curl -fsSL --retry 3 \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/$REPO/releases/latest" \
  -o "$stage/release.json"
mapfile -t release < <(
  python3 - "$stage/release.json" "$REPO" <<'PY'
import json
import re
import sys
from urllib.parse import urlparse

data = json.load(open(sys.argv[1], encoding="utf-8"))
repo = sys.argv[2]
tag = str(data["tag_name"])
if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
    raise SystemExit("The latest installer release has an invalid version.")
names = [
    f"mcbe-gdk-installer-{tag}.tar.gz",
    f"mcbe-gdk-installer-{tag}.tar.gz.sha256",
]
assets = {
    str(asset["name"]): str(asset["browser_download_url"])
    for asset in data.get("assets", [])
}
print(tag)
for name in names:
    url = assets.get(name, "")
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or f"/{repo}/releases/download/{tag}/" not in parsed.path
    ):
        raise SystemExit(f"The latest installer release is missing {name}.")
    print(url)
PY
)
tag="${release[0]}"
archive="mcbe-gdk-installer-$tag.tar.gz"
curl -fL --retry 3 "${release[1]}" -o "$stage/$archive"
curl -fL --retry 3 "${release[2]}" -o "$stage/$archive.sha256"
(cd "$stage" && sha256sum -c "$archive.sha256")
tar -xzf "$stage/$archive" -C "$stage"
source="$stage/mcbe-gdk-installer"
[[ "$(<"$source/VERSION")" == "$tag" ]] || {
  echo "Installer archive version does not match $tag." >&2
  exit 1
}
touch "$source/.mcbe-managed-source"

backup="$SOURCE_DIR.previous"
rm -rf "$backup"
[[ ! -e "$SOURCE_DIR" ]] || mv "$SOURCE_DIR" "$backup"
if mv "$source" "$SOURCE_DIR"; then
  rm -rf "$backup"
else
  [[ ! -e "$backup" ]] || mv "$backup" "$SOURCE_DIR"
  exit 1
fi

echo "Opening MCBE GDK Installer..."
exec "$SOURCE_DIR/gui.sh"
