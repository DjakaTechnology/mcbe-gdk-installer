"""Smoke test for staging a raw MSIXVC package."""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


class RawPackageStagingTest(unittest.TestCase):
    def test_raw_msixvc_is_staged_without_manifest(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "build.msixvc"
            package.write_bytes(b"raw-msixvc")
            stage = root / "stage"
            process = subprocess.Popen(
                [repo / "easy-install.sh", package],
                cwd=repo,
                env={
                    **os.environ,
                    "MCBE_GDK_SETUP_DIR": str(stage),
                    "MCBE_GDK_ROOT": str(root / "runtime"),
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                helper = stage / "MCBEGDKExport.ps1"
                for _ in range(100):
                    if helper.exists():
                        break
                    if process.poll() is not None:
                        self.fail("easy-install.sh exited before staging")
                    time.sleep(0.05)
                else:
                    self.fail("easy-install.sh did not finish staging")

                self.assertEqual(
                    (stage / "input" / "MCBEGDK.msixvc").read_bytes(),
                    package.read_bytes(),
                )
                self.assertFalse((stage / "input" / "AppxManifest.xml").exists())
                self.assertIn("Microsoft.MinecraftUWP", helper.read_text())
            finally:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    unittest.main()
