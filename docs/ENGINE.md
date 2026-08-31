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
asset. The archive must have one root directory containing executable
`proton`, `files/bin/wine`, and `files/bin/wineserver` files.

Custom URLs are exact, pinned selections and are not included in automatic
engine update checks. Selecting `latest` or a `vX.Y.Z` release returns to the
reviewed `veedy-dev/mcbe-gdk-engine` release stream.

Assets from the `LukasPAH/GDK-Proton-Custom` repository are assigned the Lukas
profile by repository name. Every selected asset still has its GitHub-published
SHA-256 digest verified before installation. The profile:

- patches the engine's Gaming Services version gate during installation;
- creates or updates `MicrosoftGame.Config` with the required Android identity;
- reversibly disables the incompatible Windows App Runtime bootstrap DLL;
- watches the engine's `login.json`, validates its Microsoft URL and device
  code, opens the browser, and displays a copyable sign-in prompt;
- restores game files when switching back to the reviewed mcbe engine.

`mcbe-gdk-linux login`, `logout`, and `status` direct Lukas-profile account
management to Minecraft because that engine persists its own in-game session.
Other custom engines remain publisher-managed. The launcher continues applying
its XCurl payload and CA certificates to every supported engine.
