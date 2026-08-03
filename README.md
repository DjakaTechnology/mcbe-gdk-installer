<p align="center">
  <img src="assets/mcbe-gdk-installer.png" width="128" alt="MCBE GDK Installer">
</p>

# MCBE GDK Installer

Minecraft Bedrock GDK builds installer on Linux with working Xbox authentication.

> Compatibility engine source and releases:
> [mcbe-gdk-engine](https://github.com/veedy-dev/mcbe-gdk-engine).

## What it does

- Accepts `.zip`, `.msixvc`, or `.msixv` packages
- Provides a desktop UI for installation, account login, and launching
- Notifies you about installer and compatibility-engine updates
- Decrypts `/LT` test-crypted development packages entirely on Linux
- Installs the latest verified MCBE-compatible GDK-Proton xuser engine
- Opens Microsoft device-code sign-in automatically when needed
- Launches through `umu`
- Keeps its profile separate from other Minecraft installations
- Installs XDG entries for the installer and Minecraft Bedrock

> [!IMPORTANT]
> This project does not include Minecraft files, credentials, licenses,
> decryption keys, or DRM bypasses. You must have authorized access to the
> build and Microsoft GDK.

## Requirements

### Command-line installation and launch

- x86_64 Linux
- An existing decrypted `Content` directory, or an authorized `/LT`
  test-crypted `.zip`, `.msixvc`, or `.msixv`
- Python 3 and `cryptography`
- `curl`, `tar`, `sha256sum`, and `flock`
- `unzip` and `7z` only when installing an encrypted package

Installation, Microsoft/Xbox device-code authentication, and game launching all
work from the terminal without GTK. The login command prints the sign-in URL and
code even when no desktop dialog helper is available.

### Optional desktop UI

The setup UI and the GUI-first bootstrap additionally require GTK4, Libadwaita,
and PyGObject. `qrencode` is optional and adds a QR code to the GUI sign-in
dialog. The distribution commands below install both the CLI and GUI
dependencies.

### Arch Linux

```bash
sudo pacman -S --needed \
  gtk4 libadwaita python python-gobject python-cryptography \
  qrencode curl tar unzip 7zip
```

### Fedora

```bash
sudo dnf install \
  gtk4 libadwaita python3 python3-gobject python3-cryptography \
  qrencode curl tar unzip p7zip p7zip-plugins
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install \
  python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  python3-cryptography qrencode curl tar unzip 7zip
```

## Install

### GUI bootstrap

The bootstrap script installs the GUI dependencies, verifies and downloads the
latest installer release to your user data directory, and opens the setup UI:

```bash
curl -fsSL https://raw.githubusercontent.com/veedy-dev/mcbe-gdk-installer/main/bootstrap.sh | bash
```

### Source checkout

```bash
git clone https://github.com/veedy-dev/mcbe-gdk-installer.git
cd mcbe-gdk-installer
```

Run the optional setup UI with:

```bash
./gui.sh
```

For a terminal-only setup, continue with one of the command-line installation
methods below instead.

## Use

Choose the authorized `.zip`, `.msixvc`, or `.msixv`, then click **Install**.
The installer selects the latest engine release, verifies its checksum, extracts
the public GDK test key locally, decrypts the package, and installs it.
The first run temporarily downloads the official Microsoft GDK archive.
Installing a newer build replaces only the game files; the isolated account,
worlds, and profile data are preserved.

In the UI, click **Sign in**. Scan the QR code or open the displayed URL, then
enter the Microsoft device code. Click **Launch** when the account is
connected.

When an installer or engine update is available, a banner appears above the
Package section. Select **Review** to read the release changelog, then choose
**Install updates** or **Later**. Minecraft, worlds, settings, and account data
are preserved.

The app is also available as **MCBE GDK Installer** in compatible
application launchers. Desktops that group XDG categories place it under
**Games**; launchers used with Hyprland usually expose it through search.

## Command-line install

### Encrypted package

The terminal installer performs the same native Linux setup:

```bash
./easy-install.sh "/path/to/Minecraft-package.msixvc"
```

### Existing decrypted files

If Minecraft is already extracted and decrypted, pass its `Content` directory
directly to the installer. The directory must contain `Minecraft.Windows.exe`:

```bash
./install.sh "/path/to/Minecraft for Windows/Content"
```

The version is optional metadata and can be supplied when known:

```bash
./install.sh "/path/to/Minecraft for Windows/Content" --version 1.26.32.2
```

`install.sh` uses the existing directory in place instead of copying it. Runtime
setup can patch game binaries and DLLs, so keep a backup if the original files
must remain unchanged. The script downloads and verifies the custom GDK-Proton
engine, configures `umu`, creates an isolated profile, and installs the terminal
commands under `~/.local/bin`.

After installation, sign in and launch without opening the setup UI:

```bash
mcbe-gdk-linux-login
mcbe-gdk-linux
```

Use `mcbe-gdk-linux-auth` to check account status and
`mcbe-gdk-linux-logout` to remove the saved account. If `~/.local/bin` is not in
`PATH`, invoke those commands with their full paths.

Rerun the same installation command after `git pull` to update an existing
installation.

Set `MCBE_GDK_ENGINE_RELEASE=vX.Y.Z` to install a specific engine release for
testing or rollback.

## Commands

| Purpose | Command |
| --- | --- |
| Open setup UI | `./gui.sh` or `mcbe-gdk-linux-gui` |
| Package-to-Linux setup | `./easy-install.sh /path/to/mcbe-gdk-build.msixvc` |
| Launch Minecraft | `mcbe-gdk-linux` |
| Check Xbox account | `mcbe-gdk-linux-auth` |
| Sign in | `mcbe-gdk-linux-login` |
| Sign out | `mcbe-gdk-linux-logout` |
| Remove launchers | `./uninstall.sh` |

## Documentation

- [Native `/LT` package extraction](docs/DECRYPTION.md)
- [Compatibility engine source](https://github.com/veedy-dev/mcbe-gdk-engine)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Engine source

The compatibility engine source, build workflow, and release provenance live in
[mcbe-gdk-engine](https://github.com/veedy-dev/mcbe-gdk-engine).
Authentication and prefix setup use a pinned, MIT-licensed subset of
[BedrockOnLinux](https://github.com/Wyze3306/BedrockOnLinux). Its launcher,
AppImage, GUI, and game-management code are not installed.

## License

The installer and documentation are MIT licensed. Vendored and runtime
components retain their upstream licenses. This project is unofficial and is
not affiliated with Microsoft or Mojang.
