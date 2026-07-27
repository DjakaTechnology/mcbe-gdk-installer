#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STAGE="${MCBE_GDK_SETUP_DIR:-$HOME/MCBEGDKLinuxSetup}"

usage() {
  cat <<USAGE
Usage: $0 /path/to/Minecraft-mcbe-gdk-build.zip

Stages the authorized MSIXVC for a WinBoat guest, generates the Windows export
helper, waits for the decrypted Content directory, then installs the Linux
runtime. WinBoat must already be configured with the Linux home directory shared
and the Microsoft GDK installed in its Windows guest.
USAGE
}

[[ $# -eq 1 ]] || { usage; exit 2; }
ZIP="$(realpath "$1")"
[[ -f "$ZIP" ]] || { echo "Build archive not found: $ZIP" >&2; exit 1; }
for command in unzip grep sed find python3; do
  command -v "$command" >/dev/null || { echo "$command is required." >&2; exit 1; }
done
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/games/mcbe-gdk-linux"
MCBE_GDK_ROOT="$ROOT" BOL_HOME="$ROOT/profile" \
PYTHONPATH="$SCRIPT_DIR/third_party/bedrock-on-linux${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$SCRIPT_DIR/scripts/runtime.py" ensure-deps || {
    echo "Install python-cryptography with your distribution package manager." >&2
    exit 1
  }

if [[ -e "$STAGE" ]]; then
  echo "Setup directory already exists: $STAGE" >&2
  echo "Move or remove it after preserving anything you need, then rerun." >&2
  exit 1
fi
mkdir -p "$STAGE/input" "$STAGE/output"

mapfile -t MSIX_LIST < <(unzip -Z1 "$ZIP" | grep -Ei '\.msixvc$' || true)
mapfile -t MANIFEST_LIST < <(unzip -Z1 "$ZIP" | grep -Ei 'appxmanifest\.xml$' || true)
[[ ${#MSIX_LIST[@]} -eq 1 ]] || {
  echo "Expected exactly one .msixvc in the archive; found ${#MSIX_LIST[@]}." >&2; exit 1;
}
[[ ${#MANIFEST_LIST[@]} -ge 1 ]] || {
  echo "No AppxManifest XML was found in the archive." >&2; exit 1;
}

echo "Extracting the authorized package into the WinBoat exchange directory..."
unzip -p "$ZIP" "${MSIX_LIST[0]}" > "$STAGE/input/MCBEGDK.msixvc"
unzip -p "$ZIP" "${MANIFEST_LIST[0]}" > "$STAGE/input/AppxManifest.xml"

MANIFEST_VERSION="$(grep -ioE '<Identity[^>]+Version="[^"]+"' "$STAGE/input/AppxManifest.xml" | head -1 | sed -E 's/.*Version="([^"]+)"/\1/' || true)"
VERSION="${MANIFEST_VERSION:-local}"
# Minecraft encodes 1.26.32.2 as 1.26.3202.0 in the package manifest.
if [[ "$VERSION" =~ ^([0-9]+)\.([0-9]+)\.([0-9]{2})([0-9]{2})\.0$ ]]; then
  patch="${BASH_REMATCH[4]}"; patch="$((10#$patch))"
  VERSION="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.$((10#${BASH_REMATCH[3]})).${patch}"
fi
printf '%s\n' "$VERSION" > "$STAGE/version.txt"

cat > "$STAGE/Run-MCBE-GDK-Setup.cmd" <<'CMD'
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0MCBEGDKExport.ps1"
echo.
echo Press any key to close this window.
pause >nul
CMD

cat > "$STAGE/MCBEGDKExport.ps1" <<'POWERSHELL'
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Log = Join-Path $Root "mcbe-gdk-export.log"
Start-Transcript -Path $Log -Force | Out-Null

function Fail([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    throw $Message
}

try {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "Requesting Administrator privileges..."
        Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $PSCommandPath + '"')
        )
        exit
    }

    $Msix = Get-ChildItem (Join-Path $Root "input") -Filter *.msixvc | Select-Object -First 1
    $ManifestFile = Join-Path $Root "input\AppxManifest.xml"
    if (-not $Msix) { Fail "The staged MSIXVC file is missing." }
    if (-not (Test-Path $ManifestFile)) { Fail "AppxManifest.xml is missing." }

    [xml]$Manifest = Get-Content $ManifestFile
    $IdentityName = [string]$Manifest.Package.Identity.Name
    $AppNode = @($Manifest.Package.Applications.Application) | Select-Object -First 1
    $AppId = [string]$AppNode.Id
    if (-not $IdentityName) { Fail "Could not read the package identity from AppxManifest.xml." }
    if (-not $AppId) { $AppId = "Game" }

    $WdApp = Get-Command wdapp.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
    if (-not $WdApp) {
        $Roots = @("${env:ProgramFiles(x86)}\Microsoft GDK", "$env:ProgramFiles\Microsoft GDK")
        foreach ($SearchRoot in $Roots) {
            if (Test-Path $SearchRoot) {
                $WdApp = Get-ChildItem $SearchRoot -Filter wdapp.exe -File -Recurse -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty FullName -First 1
                if ($WdApp) { break }
            }
        }
    }
    if (-not $WdApp) {
        Fail "wdapp.exe was not found. Install the Microsoft GDK in this authorized WinBoat guest."
    }

    $DevModeKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock"
    New-Item $DevModeKey -Force | Out-Null
    New-ItemProperty $DevModeKey -Name AllowDevelopmentWithoutDevLicense -PropertyType DWord -Value 1 -Force | Out-Null

    $LocalRoot = "C:\MCBEGDKLinuxSetup"
    New-Item -ItemType Directory -Path $LocalRoot -Force | Out-Null
    $LocalMsix = Join-Path $LocalRoot "MCBEGDK.msixvc"
    Write-Host "Copying the package to the guest's local drive..." -ForegroundColor Cyan
    Copy-Item $Msix.FullName $LocalMsix -Force

    Write-Host "Installing the authorized MSIXVC with wdapp..." -ForegroundColor Cyan
    & $WdApp install $LocalMsix
    if ($LASTEXITCODE -ne 0) { Fail "wdapp install failed with exit code $LASTEXITCODE." }

    $Package = Get-AppxPackage -Name $IdentityName -ErrorAction SilentlyContinue |
        Sort-Object Version -Descending | Select-Object -First 1
    if (-not $Package) {
        $Package = Get-AppxPackage -AllUsers -Name $IdentityName -ErrorAction SilentlyContinue |
            Sort-Object Version -Descending | Select-Object -First 1
    }
    if (-not $Package) { Fail "The installed package identity was not visible to Get-AppxPackage." }

    $Candidates = @()
    if ($Package.InstallLocation) { $Candidates += $Package.InstallLocation }
    foreach ($Drive in Get-PSDrive -PSProvider FileSystem) {
        $XboxGames = Join-Path $Drive.Root "XboxGames"
        if (Test-Path $XboxGames) {
            $Candidates += Get-ChildItem $XboxGames -Filter Minecraft.Windows.exe -File -Recurse -ErrorAction SilentlyContinue |
                ForEach-Object { Split-Path (Split-Path $_.FullName -Parent) -Parent }
        }
    }
    $GameDir = $Candidates | Where-Object {
        Test-Path (Join-Path $_ "Content\Minecraft.Windows.exe")
    } | Select-Object -First 1
    if (-not $GameDir) { Fail "Could not locate the installed Content directory under the guest's XboxGames drives." }

    $SourceContent = Join-Path $GameDir "Content"
    $LocalExport = Join-Path $LocalRoot "Export"
    New-Item -ItemType Directory -Path $LocalExport -Force | Out-Null
    Set-Location $LocalExport

    $SourceExe = Join-Path $SourceContent "Minecraft.Windows.exe"
    $DecryptedExe = Join-Path $LocalExport "Minecraft.Windows.exe"
    $EscapedSource = $SourceExe.Replace("'", "''")
    $EscapedDest = $DecryptedExe.Replace("'", "''")

    Write-Host "Exporting Minecraft.Windows.exe through the package identity..." -ForegroundColor Cyan
    Invoke-CommandInDesktopPackage `
        -PackageFamilyName $Package.PackageFamilyName `
        -App $AppId `
        -Command "powershell.exe" `
        -Args "-NoProfile -Command Copy-Item '$EscapedSource' '$EscapedDest' -Force"
    if (-not (Test-Path $DecryptedExe)) { Fail "The package-context executable export did not produce a file." }

    $OutputContent = Join-Path $Root "output\Content"
    if (Test-Path $OutputContent) { Remove-Item $OutputContent -Recurse -Force }
    Write-Host "Copying the complete Content tree back to Linux..." -ForegroundColor Cyan
    Copy-Item $SourceContent $OutputContent -Recurse -Force
    Copy-Item $DecryptedExe (Join-Path $OutputContent "Minecraft.Windows.exe") -Force

    $Ready = @{
        packageFamily = $Package.PackageFamilyName
        appId = $AppId
        version = [string]$Package.Version
        content = "output/Content"
    } | ConvertTo-Json
    Set-Content (Join-Path $Root "export-ready.json") $Ready -Encoding UTF8
    Write-Host "Export complete. Return to the Linux terminal." -ForegroundColor Green
}
catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
}
finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}
POWERSHELL

cat <<INSTRUCTIONS

Build staged at:
  $STAGE

One WinBoat action is required because Microsoft licenses MSIXVC decryption to
the Windows package identity:

  1. Open the WinBoat Windows desktop.
  2. In File Explorer, open Network > host.lan > MCBEGDKLinuxSetup.
  3. Double-click Run-MCBE-GDK-Setup.cmd and approve the Administrator prompt.

The helper installs the MSIXVC with wdapp, exports the executable through the
registered package identity, and copies the complete Content tree back here.
This Linux process will continue automatically when the export completes.
INSTRUCTIONS

printf '\nWaiting for WinBoat export'
while [[ ! -f "$STAGE/export-ready.json" ]]; do
  printf '.'
  sleep 3
done
printf ' ready.\n\n'

[[ -f "$STAGE/output/Content/Minecraft.Windows.exe" ]] || {
  echo "WinBoat reported completion, but Minecraft.Windows.exe is missing." >&2; exit 1;
}
"$SCRIPT_DIR/install.sh" "$STAGE/output/Content" --version "$VERSION"

echo
echo "End-to-end setup complete. The staged package remains at: $STAGE"
echo "After verifying the game, you may remove that directory to reclaim space."
