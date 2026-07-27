# MCBE GDK Installer

Run an authorized Minecraft Bedrock GDK build on Linux with standalone
Microsoft/Xbox authentication and Regolith/rgl addon exports.

## What it does

- Accepts an authorized `.zip`, `.msixvc`, or `.msixv`
- Provides a desktop UI for installation, account login, and launching
- Decrypts `/LT` test-crypted development packages entirely on Linux
- Installs an MCBE-compatible GDK-Proton xuser engine
- Opens Microsoft device-code sign-in automatically when needed
- Launches directly through `umu` without the BedrockOnLinux AppImage
- Keeps its profile separate from other Minecraft installations
- Installs a standard XDG desktop entry for desktop environments and app launchers
- Provides the correct `COM_MOJANG` path for Regolith and rgl

> [!IMPORTANT]
> This project does not include Minecraft files, credentials, licenses,
> decryption keys, or DRM bypasses. You must have authorized access to the
> build and Microsoft GDK.

Requires x86_64 Linux, GTK4, Libadwaita, Python 3 with PyGObject and
`cryptography`, `curl`, `tar`, `unzip`, `7z`, `sha256sum`, and `flock`.
Install `qrencode` to show a QR code; the URL and device code are always
available.

**CachyOS / Arch**

```bash
sudo pacman -S --needed gtk4 libadwaita python-gobject python-cryptography qrencode curl tar unzip p7zip
```

## Setup

### 1. Open the setup UI

```bash
git clone https://github.com/veedy-dev/mcbe-gdk-installer.git
cd mcbe-gdk-installer
./gui.sh
```

Choose the authorized `.zip`, `.msixvc`, or `.msixv`, then click **Install**.
The installer downloads its pinned tools, verifies their checksums, extracts the
public GDK test key locally, decrypts the package, and installs it.
The first run temporarily downloads the official Microsoft GDK archive.
Installing a newer build replaces only the game files; the isolated account,
worlds, and profile data are preserved.

### 2. Sign in and launch

In the UI, click **Sign in**. Scan the QR code or open the displayed URL, then
enter the Microsoft device code. Click **Launch Minecraft** when the account is
connected.

The app is also available as **MCBE GDK Installer** in compatible
application launchers. Desktops that group XDG categories place it under
**Games**; launchers used with Hyprland usually expose it through search.

## Regolith / rgl path

Point `COM_MOJANG` to the isolated MCBE GDK profile before using Regolith or rgl.

**Bash/Zsh**

```bash
source <(mcbe-gdk-linux-regolith-env)
```

**Fish**

```fish
mcbe-gdk-linux-regolith-env --fish | source
```

## Manual install

The terminal installer performs the same native Linux setup:

```bash
./easy-install.sh "/path/to/Minecraft-package.msixvc"
```

If you already have a decrypted `Content` directory:

```bash
./install.sh "/path/to/decrypted/Content" --version 1.26.32.2
```

Rerun the same command after `git pull` to update an existing installation.

## Commands

| Purpose | Command |
| --- | --- |
| Open setup/account UI | `./gui.sh` or `mcbe-gdk-linux-gui` |
| Package-to-Linux setup | `./easy-install.sh /path/to/mcbe-gdk-build.msixvc` |
| Launch Minecraft | `mcbe-gdk-linux` |
| Check Xbox account | `mcbe-gdk-linux-auth` |
| Sign in again | `mcbe-gdk-linux-login` |
| Sign out | `mcbe-gdk-linux-logout` |
| Set Regolith/rgl path | `mcbe-gdk-linux-regolith-env` |
| Remove launchers | `./uninstall.sh` |

## Documentation

- [Native `/LT` package extraction](docs/DECRYPTION.md)
- [Engine sources and provenance](docs/ENGINE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Engine source

The compatibility engine is built from pinned public WineGDK sources documented
in [Engine sources and provenance](docs/ENGINE.md). Authentication and prefix
setup use a pinned, MIT-licensed subset of
[BedrockOnLinux](https://github.com/Wyze3306/BedrockOnLinux). Its launcher,
AppImage, GUI, and game-management code are not installed.

## License

The installer and documentation are MIT licensed. Vendored and runtime
components retain their upstream licenses. This project is unofficial and is
not affiliated with Microsoft or Mojang.
