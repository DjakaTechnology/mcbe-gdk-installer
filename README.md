# MCBE GDK Linux

Run an authorized Minecraft Bedrock GDK build on Linux with Xbox
authentication and Regolith/rgl addon exports.

## What it does

- Accepts the original authorized build `.zip`
- Stages and exports its licensed MSIXVC content through WinBoat
- Installs an MCBE-compatible GDK-Proton xuser engine
- Handles Microsoft/Xbox device-code sign-in without another launcher
- Keeps its profile separate from other Minecraft installations
- Installs a standard XDG desktop entry for desktop environments and app launchers
- Provides the correct `COM_MOJANG` path for Regolith and rgl

> [!IMPORTANT]
> This project does not include Minecraft files, credentials, licenses,
> decryption keys, or DRM bypasses. You must have authorized access to the
> build and Microsoft GDK.

Requires x86_64 Linux, Python 3 with `cryptography`, `curl`, `tar`,
`sha256sum`, and `flock`. The installer attempts a user-local Python package
install when `cryptography` is missing.

## Setup

### 1. Prepare WinBoat once

Install [WinBoat](https://github.com/TibixDev/winboat), create its Windows guest,
and:

- share your Linux home directory with the guest;
- install the Microsoft GDK inside the guest.

See [WinBoat/MSIXVC setup](docs/DECRYPTION.md) if this is not already configured.

### 2. Run the installer

```bash
git clone https://github.com/veedy-dev/mcbe-gdk-linux.git
cd mcbe-gdk-linux

./easy-install.sh "/path/to/Minecraft-release_Bedrock_GameCore_x64_Desktop.zip"
```

The script extracts and stages the package, then waits for WinBoat.

### 3. Complete the WinBoat step

In the WinBoat Windows desktop:

1. Open **Network → host.lan → MCBEGDKLinuxSetup**.
2. Double-click **Run-MCBE-GDK-Setup.cmd**.
3. Approve the Administrator prompt.
4. Wait for the export to finish.

Return to the Linux terminal. Installation continues automatically.

### 4. Launch

```bash
mcbe-gdk-linux
```

The first launch opens Microsoft device-code sign-in automatically. Use the
Microsoft account authorized for the build.

The game is also available as **MCBE GDK Linux** in compatible
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

If you already have a decrypted `Content` directory:

```bash
./install.sh "/path/to/decrypted/Content" --version 1.26.32.2
```

## Commands

| Purpose | Command |
| --- | --- |
| ZIP-to-Linux setup | `./easy-install.sh /path/to/mcbe-gdk-build.zip` |
| Launch Minecraft | `mcbe-gdk-linux` |
| Check Xbox account | `mcbe-gdk-linux-auth` |
| Sign in again | `mcbe-gdk-linux-login` |
| Sign out | `mcbe-gdk-linux-logout` |
| Set Regolith/rgl path | `mcbe-gdk-linux-regolith-env` |
| Remove launchers | `./uninstall.sh` |

## Documentation

- [WinBoat and authorized MSIXVC export](docs/DECRYPTION.md)
- [Engine sources and provenance](docs/ENGINE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Engine source

This repository contains the Linux setup tooling. The compatibility engine is
built from public WineGDK sources pinned in
[Engine sources and provenance](docs/ENGINE.md). The standalone authentication
runtime vendors a pinned, MIT-licensed subset of
[BedrockOnLinux](https://github.com/Wyze3306/BedrockOnLinux); it does not install
or run the BedrockOnLinux launcher.

## License

The installer and documentation are MIT licensed. Vendored and runtime
components retain their upstream licenses. This project is unofficial and is
not affiliated with Microsoft or Mojang.
