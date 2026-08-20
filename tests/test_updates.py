import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("MCBE_GDK_ROOT", "/tmp/mcbe-gdk-update-tests")

from updates import (  # noqa: E402
    ENGINE_REPO,
    INSTALLER_REPO,
    AvailableUpdates,
    Release,
    UpdateError,
    _download_verified,
    _engine_cli,
    _install_updates_cli,
    _validate_archive,
    _verify_checksum,
    check_for_updates,
    fetch_latest_release,
    fetch_release,
    is_newer,
    normalize_engine_selection,
)


class Response:
    def __init__(self, data: bytes):
        self.data = data
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _size=-1):
        data, self.data = self.data, b""
        return data


def release(repo: str, tag: str) -> Release:
    archive = (
        f"mcbe-gdk-installer-{tag}.tar.gz"
        if repo == INSTALLER_REPO
        else f"GDK-Proton-mcbe-gdk-{tag}.tar.gz"
    )
    base = f"https://github.com/{repo}/releases/download/{tag}"
    return Release(
        repo=repo,
        tag=tag,
        name=tag,
        body="Changes",
        url=f"https://github.com/{repo}/releases/tag/{tag}",
        assets={
            archive: f"{base}/{archive}",
            f"{archive}.sha256": f"{base}/{archive}.sha256",
        },
    )


class UpdateTests(unittest.TestCase):
    def test_semantic_versions_do_not_use_lexical_order(self):
        self.assertTrue(is_newer("v0.1.10", "v0.1.9"))
        self.assertFalse(is_newer("v0.1.2", "v0.1.2"))
        with self.assertRaises(UpdateError):
            is_newer("latest", "v0.1.2")

    def test_engine_selection_accepts_cli_versions(self):
        self.assertEqual(normalize_engine_selection("0.1.5"), "v0.1.5")
        self.assertEqual(normalize_engine_selection("v0.1.5"), "v0.1.5")
        self.assertEqual(normalize_engine_selection("latest"), "latest")
        with self.assertRaises(UpdateError):
            normalize_engine_selection("main")

    def test_latest_release_metadata_is_validated(self):
        repo = INSTALLER_REPO
        data = {
            "tag_name": "v0.1.3",
            "name": "MCBE GDK Installer v0.1.3",
            "body": "Automatic updates",
            "html_url": f"https://github.com/{repo}/releases/tag/v0.1.3",
            "assets": [
                {
                    "name": "mcbe-gdk-installer-v0.1.3.tar.gz",
                    "state": "uploaded",
                    "browser_download_url": (
                        f"https://github.com/{repo}/releases/download/v0.1.3/"
                        "mcbe-gdk-installer-v0.1.3.tar.gz"
                    ),
                }
            ],
        }
        with patch("updates.urlopen", return_value=Response(json.dumps(data).encode())):
            latest = fetch_latest_release(repo)
        self.assertEqual(latest.tag, "v0.1.3")
        self.assertIn("mcbe-gdk-installer-v0.1.3.tar.gz", latest.assets)

        data["html_url"] = "https://example.com/update"
        with patch("updates.urlopen", return_value=Response(json.dumps(data).encode())):
            with self.assertRaises(UpdateError):
                fetch_latest_release(repo)

    def test_checks_installer_and_engine_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = root / "source"
            tool.mkdir()
            (tool / "VERSION").write_text("v0.1.2\n")
            engine = root / "engine/GDK-Proton-mcbe-gdk"
            engine.mkdir(parents=True)
            (engine / "engine-manifest.json").write_text(
                json.dumps({"version": "v0.1.2"})
            )
            with patch(
                "updates.fetch_latest_release",
                return_value=release(INSTALLER_REPO, "v0.1.3"),
            ), patch(
                "updates.fetch_release", side_effect=UpdateError("offline")
            ) as fetch:
                available = check_for_updates(tool, root)
            self.assertEqual(available.installer.tag, "v0.1.3")
            self.assertIsNone(available.engine)
            fetch.assert_called_once_with(ENGINE_REPO, "latest")

            with patch(
                "updates.fetch_latest_release", side_effect=UpdateError("offline")
            ), patch(
                "updates.fetch_release", side_effect=UpdateError("offline")
            ):
                with self.assertRaises(UpdateError):
                    check_for_updates(tool, root, raise_if_unavailable=True)

    def test_selected_engine_release_can_downgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = root / "source"
            tool.mkdir()
            (tool / "VERSION").write_text("v0.1.3\n")
            (root / "engine-release").write_text("v0.1.5\n")
            engine = root / "engine/GDK-Proton-mcbe-gdk"
            engine.mkdir(parents=True)
            (engine / "engine-manifest.json").write_text(
                json.dumps({"version": "v0.1.7"})
            )
            selected = release(ENGINE_REPO, "v0.1.5")
            with patch(
                "updates.fetch_latest_release",
                return_value=release(INSTALLER_REPO, "v0.1.3"),
            ), patch("updates.fetch_release", return_value=selected) as fetch:
                available = check_for_updates(tool, root)
            self.assertEqual(available.engine, selected)
            fetch.assert_called_once_with(ENGINE_REPO, "v0.1.5")

    def test_engine_cli_switches_and_persists_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = root / "engine/GDK-Proton-mcbe-gdk"
            engine.mkdir(parents=True)
            (engine / "engine-manifest.json").write_text(
                json.dumps({"version": "v0.1.7"})
            )
            selected = release(ENGINE_REPO, "v0.1.5")
            output = io.StringIO()
            with patch("updates.fetch_release", return_value=selected) as fetch, patch(
                "updates.install_engine_update"
            ) as install, redirect_stdout(output):
                result = _engine_cli(root, "0.1.5")
            self.assertEqual(result, 0)
            self.assertEqual((root / "engine-release").read_text(), "v0.1.5\n")
            fetch.assert_called_once_with(ENGINE_REPO, "v0.1.5")
            install.assert_called_once()
            self.assertIn("Switched compatibility engine to v0.1.5.", output.getvalue())

    def test_checksum_and_archive_paths_are_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            archive.write_bytes(b"release")
            digest = hashlib.sha256(b"release").hexdigest()
            checksum = root / "source.tar.gz.sha256"
            checksum.write_text(f"{digest}  source.tar.gz\n")
            _verify_checksum(archive, checksum)
            checksum.write_text(f"{'0' * 64}  source.tar.gz\n")
            with self.assertRaises(UpdateError):
                _verify_checksum(archive, checksum)

            unsafe = root / "unsafe.tar.gz"
            with tarfile.open(unsafe, "w:gz") as bundle:
                info = tarfile.TarInfo("../outside")
                info.size = 1
                bundle.addfile(info, io.BytesIO(b"x"))
            with self.assertRaises(UpdateError):
                _validate_archive(unsafe, "mcbe-gdk-installer", links=False)

    def test_verified_download_reports_progress_and_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            latest = release(INSTALLER_REPO, "v0.1.3")
            name = "mcbe-gdk-installer-v0.1.3.tar.gz"
            data = b"verified release"
            checksum = f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode()
            events = []
            with patch(
                "updates.urlopen",
                side_effect=[Response(data), Response(checksum)],
            ):
                _download_verified(
                    latest,
                    name,
                    root,
                    1024,
                    "installer",
                    lambda *event: events.append(event),
                )
            self.assertEqual(
                events,
                [
                    ("installer_download", 0, len(data)),
                    ("installer_download", len(data), len(data)),
                    ("installer_verify", None, None),
                ],
            )

    def test_cli_update_reports_component_progress(self):
        installer = release(INSTALLER_REPO, "v0.1.3")
        engine = release(ENGINE_REPO, "v0.1.4")
        output = io.StringIO()

        def install(updates, tool_root, root, progress):
            self.assertEqual(updates.installer, installer)
            progress("engine_download", 50 * 1024**2, 100 * 1024**2)
            progress("engine_verify", None, None)
            progress("engine_install", None, None)
            progress("engine_done", None, None)
            progress("installer_done", None, None)

        with patch(
            "updates.check_for_updates",
            return_value=AvailableUpdates(installer=installer, engine=engine),
        ), patch("updates.install_available_updates", side_effect=install):
            with redirect_stdout(output):
                result = _install_updates_cli(Path("/tool"), Path("/root"))

        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn("Downloading compatibility engine: 50%", text)
        self.assertIn("Verifying compatibility engine…", text)
        self.assertIn("MCBE GDK Installer updated…", text)
        self.assertIn("Updates installed.", text)


if __name__ == "__main__":
    unittest.main()
