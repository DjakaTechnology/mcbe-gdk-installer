"""Smoke test for the standalone runtime entry point."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RuntimeSmokeTest(unittest.TestCase):
    def test_fresh_profile_is_signed_out(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "lib").mkdir()
            (root / "lib" / "bol").symlink_to(
                repo / "third_party" / "bedrock-on-linux" / "bol",
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


if __name__ == "__main__":
    unittest.main()
