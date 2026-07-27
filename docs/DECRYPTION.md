# Decrypt an authorized MSIXVC from Linux

The recommended workflow stays on the Linux desktop. WinBoat runs a temporary
Windows guest because MSIXVC decryption depends on Microsoft's Gaming Services,
GDK deployment tools, package identity, and the account's package license. A
native Linux archive/decryption utility cannot request that licensed view.

## 1. Prepare WinBoat

1. Install [WinBoat](https://github.com/TibixDev/winboat) and complete its guest
   setup.
2. Enable a shared Linux directory in WinBoat. It appears inside Windows under
   **Network → host.lan**.
3. Install the Microsoft GDK inside the guest using your authorized developer
   access.
4. Enable Windows **Developer Mode**.

WinBoat itself documents KVM, Docker/Podman, FreeRDP 3, at least 4 GB RAM, two
CPU threads, and 32 GB free space as its baseline requirements.

## 2. Deploy the package locally in the guest

Copy the authorized `.msixvc` from the shared folder to a local Windows path. UNC
shares are not accepted by `wdapp install`.

From an elevated GDK command prompt:

```cmd
mkdir C:\MCBEGDK
copy "<shared-folder>\Microsoft.MinecraftUWP_....msixvc" C:\MCBEGDK\
wdapp install "C:\MCBEGDK\Microsoft.MinecraftUWP_....msixvc"
wdapp list
```

Official references:

- [Utilizing GDK tools to install and launch a PC title](https://learn.microsoft.com/en-us/gaming/gdk/docs/tools/tools-pc/launching-on-pc)
- [Testing packages on a development PC](https://learn.microsoft.com/en-us/xbox/gdk/docs/features/common/packaging/packaging-testing-pc-install)

Recent GDK installs normally use a flat-file location under `C:\XboxGames`.
Always confirm the directory and identity with `wdapp list` and the installed
manifest rather than assuming a fixed name.

## 3. Obtain the package-context executable

In elevated PowerShell:

```powershell
New-Item -ItemType Directory -Force C:\MCBEGDKExport | Out-Null
Set-Location C:\MCBEGDKExport

Invoke-CommandInDesktopPackage `
  -PackageFamilyName "Microsoft.MinecraftUWP_8wekyb3d8bbwe" `
  -app Game `
  -Command "powershell.exe" `
  -Args "-Command Copy-Item '<game-directory>\Content\Minecraft.Windows.exe' .\Minecraft.Windows.exe -Force"
```

Use the package family/application ID from the package manifest if it
differs from the example. This command is not a license bypass: it succeeds only
inside the registered package identity available to the authorized guest.

## 4. Export to Linux

Copy the full installed `Content` tree into the WinBoat shared folder. Replace
its encrypted `Minecraft.Windows.exe` with
`C:\MCBEGDKExport\Minecraft.Windows.exe`, then return to Linux and run:

```bash
./install.sh "$HOME/MCBEGDKExchange/Minecraft/Content" \
  --version 1.26.32.2
```

The full tree is required. Do not upload the package, decrypted executable,
private build links, EKB/license material, or account data to this repository.
