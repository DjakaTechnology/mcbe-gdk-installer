# Authentication runtime

Selected MIT-licensed authentication and WineGDK runtime modules from
[Wyze3306/BedrockOnLinux](https://github.com/Wyze3306/BedrockOnLinux), pinned
at commit `27ade9259384828eb6d57d8dd6441720b2859f59`.

`auth/config.py` uses the `mcbe-gdk-linux` application name, the unused
`relocation` import is removed from `auth/__init__.py`, and the dependency error
mentions Arch Linux's package name. Runtime/recovery messages use this
project's command names. Managed-engine and legacy-data migration code is
omitted because this project supplies fixed engine and profile paths. The
original license is included here.
