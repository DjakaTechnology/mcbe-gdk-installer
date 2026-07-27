# Native `/LT` package extraction

`easy-install.sh` handles authorized GDK development packages created with
`makepkg /LT` entirely on Linux:

1. It verifies that XVDTool reports `Test-crypted (/LT)`.
2. It downloads pinned XVDTool, .NET runtime, and official Microsoft GDK files.
3. It extracts the matching public development CIK from Gaming Services.
4. It decrypts and extracts the MSIXVC, then runs the normal installer.

Downloads are checksum-verified and cached. No game files, credentials, or keys
are included in this repository.

Retail, stable-key, and account-licensed MSIXVC packages are intentionally
rejected. Their licensing flow is different and this installer does not bypass
it.

References:

- [Microsoft GDK test-package documentation](https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/title-packaging-streaming-install-testing)
- [Microsoft GDK releases](https://github.com/microsoft/GDK/releases)
- [XVDTool](https://github.com/emoose/xvdtool)
