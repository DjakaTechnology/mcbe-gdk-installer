# Troubleshooting

## `Llama (0x80004001)` during sign-in

Confirm that the installed engine is `GDK-Proton-mcbe-gdk`, not generic
Wine, stock Proton, or the older non-xuser GDK-Proton build. Reset the isolated
account, then launch again:

```bash
mcbe-gdk-linux logout
mcbe-gdk-linux launch
```

## Native assertion at roughly 65% loading

The launcher changes only these user options before startup:

```text
dev_assertions_debug_break:0
dev_assertions_show_dialog:0
```

This suppresses a startup assertion dialog/debug break. It does **not** disable
addon, script, content-log, or debugger functionality.

## Launcher icon is clicked repeatedly before a window appears

Runtime preparation runs before Minecraft creates its window. The launcher
uses a single-instance lock, so click it once and wait for the game window. A
second click reports that the client is already starting or running instead of
launching another Wine session.

Startup failures are recorded in:

```text
~/.local/share/mcbe-gdk-linux/profile/logs/desktop-launch.log
```

If a previous GPU session was interrupted, the launcher deliberately blocks
another launch during the same boot. Reboot once, then acknowledge the
previous-boot marker:

```bash
mcbe-gdk-linux recover
```

## Slow loading or stutter

Advanced Proton/Wine diagnostics are disabled by default because their
synchronous D3D12 and GameCore traces can significantly reduce performance.
The launcher also gives the custom engine persistent VKD3D, DXVK, and NVIDIA
shader-cache directories.
Before launch, one advisory notification is emitted when available memory is
below 3072 MiB, free installation-disk space is below 5120 MiB, render
distance exceeds 32 chunks, or windowed VSync is enabled on Wayland. These are
warnings only; details are written to `profile/logs/desktop-launch.log`.

The bundled engine includes NTSync and selects its in-process synchronization
path when it can open `/dev/ntsync`. Legacy GE-Proton switches such as
`PROTON_NO_NTSYNC` and exact `nontsync` compatibility tokens only change
`WINENTSYNC`; this WineGDK runtime has no `WINENTSYNC` gate, so the launcher
does not report those variables as disable switches.

Each launch records one `NTSync preflight:` line in
`profile/logs/desktop-launch.log`. An engine state means updating or
reinstalling the engine. A `/dev/ntsync` state means using Linux 6.14 or a
distribution backport, loading the NTSync module, and repairing the device node
or its permissions as named. `static prerequisites present` only confirms the
launcher-side checks—it does not prove live use or promise a particular FPS
gain.

To disable unused DirectX Raytracing support and reduce its VRAM overhead for
one launch, keep the required raw-CBV compatibility flag and add `nodxr` with:

```bash
MCBE_GDK_DISABLE_DXR=1 mcbe-gdk-linux launch
```

Some GDK builds contain additional validation and debugging code, so world
creation and addon loading can remain slower than a stable retail client. To
capture a diagnostic launch temporarily, run:

```bash
BOL_DIAG=1 BOL_XCURL_LOG=1 mcbe-gdk-linux launch
```

## Game does not appear in the application launcher

The installer creates the standard XDG entry:

```text
~/.local/share/applications/io.github.veedydev.MCBEGDKInstaller.desktop
```

It is not KDE-specific. KDE/GNOME can group it under **Games**; Hyprland is a
compositor and relies on the user's launcher (such as a freedesktop-aware
Walker, Wofi, or Rofi configuration), where the entry normally appears through
search.

Refresh the desktop database when the command is available:

```bash
update-desktop-database ~/.local/share/applications
```

Then restart the application launcher or log out and back in. The entry uses
the standard `Categories=Game;` category rather than a KDE-only menu format.
