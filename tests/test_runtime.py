"""Smoke test for the standalone runtime entry point."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RuntimeSmokeTest(unittest.TestCase):
    def test_gui_uses_the_installed_profile_for_auth(self):
        gui = (
            Path(__file__).resolve().parents[1] / "scripts" / "gui.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            gui.index('os.environ["BOL_HOME"] = str(ROOT / "profile")'),
            gui.index("from auth.auth import"),
        )

    def test_fresh_profile_is_signed_out(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "lib").mkdir()
            (root / "lib" / "auth").symlink_to(
                repo / "auth",
                target_is_directory=True,
            )
            result = subprocess.run(
                [sys.executable, repo / "scripts" / "runtime.py", "status"],
                env={**os.environ, "MCBE_GDK_ROOT": str(root)},
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "Not signed in.")

    def test_prepare_does_not_require_sign_in(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            (game / "Minecraft.Windows.exe").touch()
            code = """
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import runtime

game = Path(__import__("os").environ["MCBE_GDK_ROOT"]) / "game"
prefix = game.parent / "profile" / "compatdata" / "pfx"
prefix.mkdir(parents=True)
patches = {
    "msa_signed_in": patch.object(runtime, "msa_signed_in", return_value=False),
    "ensure_login_deps": patch.object(runtime, "ensure_login_deps"),
    "login": patch.object(runtime, "login"),
    "install_gdk_xbox_dlls": patch.object(runtime, "install_gdk_xbox_dlls"),
    "fix_curl_ssl": patch.object(runtime, "fix_curl_ssl"),
    "ensure_umu": patch.object(runtime, "ensure_umu"),
    "boot_prefix": patch.object(runtime, "boot_prefix", return_value=True),
    "_install_cryptbase_in_prefix": patch.object(runtime, "_install_cryptbase_in_prefix"),
    "active_prefix": patch.object(runtime, "active_prefix", return_value=prefix),
    "install_gameinput": patch.object(runtime, "install_gameinput"),
    "wine_apply_winegdk_prereqs": patch.object(runtime, "wine_apply_winegdk_prereqs"),
    "update_prefix_registry": patch.object(runtime, "update_prefix_registry"),
    "msa_session_snapshot": patch.object(runtime, "msa_session_snapshot"),
    "bump_stack_reserve": patch.object(runtime, "bump_stack_reserve"),
}
with ExitStack() as stack:
    mocks = {name: stack.enter_context(item) for name, item in patches.items()}
    runtime.prepare(game)
    mocks["ensure_login_deps"].assert_not_called()
    mocks["login"].assert_not_called()
    mocks["msa_session_snapshot"].assert_not_called()
    mocks["update_prefix_registry"].assert_called_once()
    mocks["bump_stack_reserve"].assert_called_once()
"""
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=repo,
                env={**os.environ, "MCBE_GDK_ROOT": str(root)},
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
