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

Engine-specific setup remains the publisher's responsibility. The launcher
continues installing its XCurl payload and CA certificates, but the built-in
`mcbe-gdk-linux login` preauthentication contract is only guaranteed for the
reviewed engine.
