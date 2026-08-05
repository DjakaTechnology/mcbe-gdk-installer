import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class CliTest(unittest.TestCase):
    def test_installs_one_dispatcher_with_update_command(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            data = Path(temporary) / "data"
            bin_dir = home / ".local/bin"
            root = data / "mcbe-gdk-linux"
            bin_dir.mkdir(parents=True)
            for name in (
                "mcbe-gdk-linux-gui",
                "mcbe-gdk-linux-auth",
                "mcbe-gdk-linux-login",
                "mcbe-gdk-linux-logout",
                "mcbe-gdk-linux-config",
                "mcbe-gdk-linux-recover",
                "mcbe-gdk-linux-regolith-env",
                "mcbe-gdk-linux-rgl-env",
            ):
                (bin_dir / name).touch()
            env = {
                **os.environ,
                "HOME": str(home),
                "XDG_DATA_HOME": str(data),
            }
            result = subprocess.run(
                [repo / "scripts/install-launchers.sh", root, repo],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [path.name for path in bin_dir.glob("mcbe-gdk-linux*")],
                ["mcbe-gdk-linux"],
            )

            command = bin_dir / "mcbe-gdk-linux"
            help_result = subprocess.run(
                [command, "help"], env=env, capture_output=True, text=True
            )
            self.assertIn("update", help_result.stdout)
            self.assertIn("setup-env", help_result.stdout)

            (root / "lib/updates.py").write_text(
                "import sys\nprint('|'.join(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            update_result = subprocess.run(
                [command, "update"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(update_result.returncode, 0, update_result.stderr)
            self.assertEqual(
                update_result.stdout.strip(),
                f"install|{repo}|{root}",
            )

            installer_entry = (
                data / "applications/io.github.veedydev.MCBEGDKInstaller.desktop"
            ).read_text(encoding="utf-8")
            game_entry = (
                data / "applications/io.github.veedydev.MinecraftBedrock.desktop"
            ).read_text(encoding="utf-8")
            self.assertIn(f"Exec={command} gui", installer_entry)
            self.assertIn(f"Exec={command} launch", game_entry)


if __name__ == "__main__":
    unittest.main()
