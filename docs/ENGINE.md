# Engine provenance

The `v0.1.0` compatibility engine is built entirely from open-source WineGDK
components. It does not contain Minecraft game files or user credentials.

Pinned inputs:

- BedrockOnLinux v2.1.1: commit `ec961ba9024c0d62bf2b793cc2ebba2958147627`
- [BedrockOnLinux WineGDK source](https://github.com/Wyze3306/WineGDK/tree/75637b674e1f191e65753663c4c0c32bea05ba6e):
  commit `75637b674e1f191e65753663c4c0c32bea05ba6e`
- [LukasPAH/WineGDK GameCore implementation](https://github.com/LukasPAH/WineGDK/tree/ffb5ffe9d67878afe546dae1232fca77fa7cefcc):
  commit `ffb5ffe9d67878afe546dae1232fca77fa7cefcc`
- Build target: Debian Bullseye, glibc ceiling 2.31, WoW64 x86_64/i386

GameCore compatibility additions:

- CLSID `95fd18d2-74dd-4d7c-aa1b-0b51827665d6`
- IID `026b010c-06c3-4cdd-bbcb-43f229db1cff`

Upstreams:

- https://github.com/Wyze3306/BedrockOnLinux
- https://github.com/Wyze3306/WineGDK
- https://github.com/LukasPAH/WineGDK
- https://github.com/LukasPAH/GDK-Proton-Custom
- https://github.com/Open-Wine-Components/umu-launcher

The engine archive includes the applicable Wine/WineGDK license and patent
notices. The account authorization and Xbox token flow remain Microsoft's; the
engine only supplies the Windows APIs expected by the client.

The host-side authentication and prefix setup use selected MIT-licensed
BedrockOnLinux modules pinned at commit
`27ade9259384828eb6d57d8dd6441720b2859f59`. They are included under
`auth/`; no BedrockOnLinux AppImage is installed.
