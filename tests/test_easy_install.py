"""Smoke test for the native /LT package path."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class NativePackageInstallTest(unittest.TestCase):
    def test_install_restores_windows_app_runtime_bootstrap(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = root / "Content"
            content.mkdir()
            (content / "Minecraft.Windows.exe").write_bytes(b"MZ")
            bootstrap = content / "Microsoft.WindowsAppRuntime.Bootstrap.dll"
            disabled = Path(f"{bootstrap}.disabled")
            disabled.write_bytes(b"required")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            for command, body in {
                "curl": 'while [ "$#" -gt 0 ]; do [ "$1" = -o ] && { shift; : > "$1"; }; shift; done',
                "python3": "exit 0",
                "sha256sum": "exit 0",
                "tar": "exit 0",
            }.items():
                executable = fake_bin / command
                executable.write_text(f"#!/bin/sh\n{body}\n")
                executable.chmod(0o755)

            subprocess.run(
                [repo / "install.sh", content],
                cwd=repo,
                env={
                    **os.environ,
                    "HOME": str(root),
                    "XDG_DATA_HOME": str(root / "share"),
                    "MCBE_GDK_ENGINE_RELEASE": "v0.1.2",
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                },
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(bootstrap.read_bytes(), b"required")
            self.assertFalse(disabled.exists())

    def test_test_crypted_msixvc_is_extracted_and_installed(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "build.msixvc"
            package.write_bytes(b"raw-msixvc")
            xvd = root / "xvd"
            xvd.mkdir()
            tool = xvd / "XVDTool"
            tool.write_text(
                """#!/bin/sh
case " $* " in
  *" -i "*) echo "Test-crypted (/LT)"; echo "Encryption Key 0 GUID: 33ec8436-5a0e-4f0d-b1ce-3f29c3955039" ;;
  *" -eu "*) for last; do :; done; while [ "$1" != "-o" ]; do shift; done; cp "$last" "$2" ;;
  *" -xf "*) mkdir -p "$3"; printf MZ > "$3/Minecraft.Windows.exe" ;;
esac
"""
            )
            key_extractor = xvd / "DurangoKeyExtractor"
            key_extractor.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o755)
            key_extractor.chmod(0o755)
            dotnet = root / "dotnet"
            hostfxr = dotnet / "host" / "fxr" / "8.0.29"
            hostfxr.mkdir(parents=True)
            (hostfxr / "libhostfxr.so").touch()
            cik = root / "test.cik"
            cik.write_bytes(b"test-key")
            installer = root / "install"
            installer.write_text(
                '#!/bin/sh\n[ -f "$1/Minecraft.Windows.exe" ] && printf "%s" "$3" > "$HOME/version"\n'
            )
            installer.chmod(0o755)
            installed = root / ".local/share/mcbe-gdk-linux"
            game = installed / "game"
            game.mkdir(parents=True)
            (game / "Minecraft.Windows.exe").write_bytes(b"old")
            world = installed / "profile/worlds/keep-me"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(b"user-data")

            subprocess.run(
                [repo / "easy-install.sh", package],
                cwd=repo,
                env={
                    **os.environ,
                    "HOME": str(root),
                    "XDG_DATA_HOME": str(root / ".local/share"),
                    "MCBE_GDK_ROOT": str(root / "runtime"),
                    "MCBE_GDK_XVD_DIR": str(xvd),
                    "MCBE_GDK_DOTNET_ROOT": str(dotnet),
                    "MCBE_GDK_CIK_FILE": str(cik),
                    "MCBE_GDK_INSTALLER": str(installer),
                },
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                (root / ".local/share/mcbe-gdk-linux/game/Minecraft.Windows.exe").read_bytes(),
                b"MZ",
            )
            self.assertEqual((world / "level.dat").read_bytes(), b"user-data")
            self.assertEqual((root / "version").read_text(), "local")


if __name__ == "__main__":
    unittest.main()
