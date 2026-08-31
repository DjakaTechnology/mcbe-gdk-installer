# Engine source

WineGDK source, attributed compatibility commits, pinned build inputs, release
manifests, and automated builds are maintained in
[veedy-dev/mcbe-gdk-engine](https://github.com/veedy-dev/mcbe-gdk-engine).

The host-side authentication and prefix setup use selected MIT-licensed
BedrockOnLinux modules pinned at commit
`27ade9259384828eb6d57d8dd6441720b2859f59`. They are included under
`auth/`; no BedrockOnLinux AppImage is installed.

## Custom engine archives

`mcbe-gdk-linux engine HTTPS_GITHUB_RELEASE_ASSET_URL` accepts `.tar.gz`
assets from GitHub releases. GitHub must publish a SHA-256 digest for the
asset. Archives are limited by compressed size, expanded size, member size,
member count, and path length, then extracted with Python's validated tar data
filter. The single archive root must contain executable `proton`,
`files/bin/wine`, and `files/bin/wineserver` files.

Custom URLs are exact, pinned selections and are not included in automatic
engine update checks. Selecting `latest` or a `vX.Y.Z` release returns to the
reviewed `veedy-dev/mcbe-gdk-engine` release stream.

Assets from the `LukasPAH/GDK-Proton-Custom` repository are assigned the Lukas
profile by repository name. Every selected asset still has its GitHub-published
SHA-256 digest verified before installation. Installer-owned capability
metadata determines runtime behavior; hashes of the transformed Proton, Wine,
wineserver, and available xgameruntime files detect later modification.

The Lukas profile:

- patches the engine's Gaming Services version gate during installation;
- transactionally creates or updates `MicrosoftGame.Config` with the required
  Android identity and keeps original files under `profile/engine-state/`;
- reversibly disables the incompatible Windows App Runtime bootstrap DLL;
- validates `login.json`, opens the browser, and displays a copyable sign-in
  code while a Python supervisor owns both the monitor and game process;
- uses a protected `profile/device-code.txt` fallback when no dialog,
  notification, or terminal presentation is available;
- applies or restores game changes during engine switching and again before
  launch for interrupted-operation recovery.

For custom engines, `mcbe-gdk-linux login`, `logout`, and `status` explain that
account control is engine-managed and return status 3 rather than reporting a
state they cannot observe. Other custom engines remain publisher-managed. The
launcher continues applying its XCurl payload and CA certificates to every
supported engine.
