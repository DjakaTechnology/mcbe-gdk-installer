#!/usr/bin/env python3
"""Verified GitHub release discovery and installation."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

INSTALLER_REPO = "veedy-dev/mcbe-gdk-installer"
ENGINE_REPO = "veedy-dev/mcbe-gdk-engine"
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
API_VERSION = "2022-11-28"
MAX_RELEASE_JSON = 1_000_000
ProgressCallback = Callable[[str, int | None, int | None], None]


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    repo: str
    tag: str
    name: str
    body: str
    url: str
    assets: dict[str, str]


@dataclass(frozen=True)
class AvailableUpdates:
    installer: Release | None = None
    engine: Release | None = None

    def __bool__(self) -> bool:
        return bool(self.installer or self.engine)


def version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        raise UpdateError(f"Unsupported release version: {value!r}")
    return tuple(int(part) for part in match.groups())


def is_newer(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def _github_url(url: str, repo: str, *, download: bool = False) -> str:
    parsed = urlparse(url)
    expected = f"/{repo}/releases/"
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise UpdateError("GitHub returned an untrusted release URL.")
    if expected not in parsed.path:
        raise UpdateError("GitHub returned a release URL for another repository.")
    if download and "/download/" not in parsed.path:
        raise UpdateError("GitHub returned an invalid asset URL.")
    return url


def fetch_latest_release(repo: str, *, timeout: int = 10) -> Release:
    request = Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "mcbe-gdk-installer",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RELEASE_JSON + 1)
    except OSError as exc:
        raise UpdateError(f"Could not check {repo} releases: {exc}") from exc
    if len(raw) > MAX_RELEASE_JSON:
        raise UpdateError("GitHub returned an unexpectedly large release response.")
    try:
        data = json.loads(raw)
        tag = str(data["tag_name"])
        version_tuple(tag)
        assets = {
            str(asset["name"]): _github_url(
                str(asset["browser_download_url"]), repo, download=True
            )
            for asset in data.get("assets", [])
            if asset.get("state") == "uploaded"
        }
        return Release(
            repo=repo,
            tag=tag,
            name=str(data.get("name") or tag)[:200],
            body=str(data.get("body") or "")[:20_000],
            url=_github_url(str(data["html_url"]), repo),
            assets=assets,
        )
    except (KeyError, TypeError, ValueError, UpdateError) as exc:
        raise UpdateError("GitHub returned invalid release metadata.") from exc


def read_installer_version(tool_root: Path) -> str:
    try:
        value = (tool_root / "VERSION").read_text(encoding="utf-8").strip()
        version_tuple(value)
        return value
    except (OSError, UpdateError):
        return "v0.0.0"


def read_engine_version(root: Path) -> str | None:
    manifest = root / "engine/GDK-Proton-mcbe-gdk/engine-manifest.json"
    if not manifest.is_file():
        return None
    try:
        value = str(json.loads(manifest.read_text(encoding="utf-8"))["version"])
        version_tuple(value)
        return value
    except (OSError, KeyError, TypeError, ValueError, UpdateError):
        return "v0.0.0"


def check_for_updates(tool_root: Path, root: Path) -> AvailableUpdates:
    try:
        installer = fetch_latest_release(INSTALLER_REPO)
    except UpdateError:
        installer = None
    try:
        engine = fetch_latest_release(ENGINE_REPO)
    except UpdateError:
        engine = None
    current_engine = read_engine_version(root)
    return AvailableUpdates(
        installer=installer
        if installer and is_newer(installer.tag, read_installer_version(tool_root))
        else None,
        engine=engine
        if engine and current_engine and is_newer(engine.tag, current_engine)
        else None,
    )


def _download(
    url: str,
    destination: Path,
    max_size: int,
    progress: Callable[[int, int | None], None] | None = None,
) -> None:
    request = Request(url, headers={"User-Agent": "mcbe-gdk-installer"})
    try:
        with urlopen(request, timeout=30) as response, destination.open("wb") as output:
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > max_size:
                raise UpdateError("Release asset is unexpectedly large.")
            total = 0
            if progress:
                progress(0, declared or None)
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_size:
                    raise UpdateError("Release asset is unexpectedly large.")
                output.write(chunk)
                if progress:
                    progress(total, declared or None)
    except (OSError, ValueError) as exc:
        raise UpdateError(f"Could not download the release: {exc}") from exc


def _asset(release: Release, name: str) -> str:
    try:
        return release.assets[name]
    except KeyError as exc:
        raise UpdateError(f"{release.tag} is missing {name}.") from exc


def _verify_checksum(archive: Path, checksum: Path) -> None:
    try:
        line = checksum.read_text(encoding="ascii").strip()
        expected, filename = re.fullmatch(
            r"([0-9a-fA-F]{64})[ \t]+\*?(.+)", line
        ).groups()
    except (AttributeError, OSError, UnicodeError) as exc:
        raise UpdateError("Release checksum is invalid.") from exc
    if filename != archive.name:
        raise UpdateError("Release checksum names a different asset.")
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise UpdateError("Release checksum verification failed.")


def _download_verified(
    release: Release,
    archive_name: str,
    directory: Path,
    max_size: int,
    component: str,
    progress: ProgressCallback | None = None,
) -> Path:
    archive = directory / archive_name
    checksum = directory / f"{archive_name}.sha256"
    download_progress = None
    if progress:
        download_progress = lambda current, total: progress(
            f"{component}_download", current, total
        )
    _download(
        _asset(release, archive.name),
        archive,
        max_size,
        download_progress,
    )
    _download(_asset(release, checksum.name), checksum, 4096)
    if progress:
        progress(f"{component}_verify", None, None)
    _verify_checksum(archive, checksum)
    return archive


def _validate_archive(archive: Path, expected_root: str, *, links: bool) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise UpdateError("Release archive contains an unsafe path.")
            if path.parts[0] != expected_root:
                raise UpdateError("Release archive has an unexpected root directory.")
            if member.isdev() or member.isfifo():
                raise UpdateError("Release archive contains an unsupported file.")
            if member.issym() or member.islnk():
                if not links:
                    raise UpdateError("Installer archive contains an unexpected link.")
                base = path.parent if member.issym() else PurePosixPath(expected_root)
                target = posixpath.normpath(str(base / member.linkname))
                if target != expected_root and not target.startswith(expected_root + "/"):
                    raise UpdateError("Release archive contains an unsafe link.")


def _replace_directory(source: Path, destination: Path) -> Path:
    backup = destination.with_name(f"{destination.name}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    destination.rename(backup)
    try:
        source.rename(destination)
    except Exception:
        backup.rename(destination)
        raise
    return backup


def install_installer_update(
    release: Release,
    tool_root: Path,
    root: Path,
    progress: ProgressCallback | None = None,
) -> None:
    if not (tool_root / ".mcbe-managed-source").is_file():
        raise UpdateError("Open the release page to update a source checkout.")
    archive_name = f"mcbe-gdk-installer-{release.tag}.tar.gz"
    with tempfile.TemporaryDirectory(
        prefix=".installer-update.", dir=tool_root.parent
    ) as temporary:
        work = Path(temporary)
        archive = _download_verified(
            release, archive_name, work, 25_000_000, "installer", progress
        )
        if progress:
            progress("installer_install", None, None)
        _validate_archive(archive, "mcbe-gdk-installer", links=False)
        subprocess.run(["tar", "-xzf", archive, "-C", work], check=True)
        source = work / "mcbe-gdk-installer"
        if read_installer_version(source) != release.tag:
            raise UpdateError("Installer archive version does not match its release.")
        (source / ".mcbe-managed-source").touch()
        backup = _replace_directory(source, tool_root)
        try:
            subprocess.run(
                [str(tool_root / "scripts/install-launchers.sh"), str(root), str(tool_root)],
                check=True,
            )
        except Exception:
            shutil.rmtree(tool_root)
            backup.rename(tool_root)
            subprocess.run(
                [str(tool_root / "scripts/install-launchers.sh"), str(root), str(tool_root)],
                check=False,
            )
            raise
        shutil.rmtree(backup)
        if progress:
            progress("installer_done", None, None)


def install_engine_update(
    release: Release,
    root: Path,
    progress: ProgressCallback | None = None,
) -> None:
    archive_name = f"GDK-Proton-mcbe-gdk-{release.tag}.tar.gz"
    engine_parent = root / "engine"
    engine_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".engine-update.", dir=engine_parent
    ) as temporary:
        work = Path(temporary)
        archive = _download_verified(
            release, archive_name, work, 1_500_000_000, "engine", progress
        )
        if progress:
            progress("engine_install", None, None)
        _validate_archive(archive, "GDK-Proton-mcbe-gdk", links=True)
        subprocess.run(["tar", "-xzf", archive, "-C", work], check=True)
        source = work / "GDK-Proton-mcbe-gdk"
        try:
            manifest = json.loads(
                (source / "engine-manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise UpdateError("Engine release manifest is missing or invalid.") from exc
        if manifest.get("version") != release.tag:
            raise UpdateError("Engine manifest version does not match its release.")
        destination = engine_parent / "GDK-Proton-mcbe-gdk"
        backup = _replace_directory(source, destination)
        shutil.rmtree(backup)
        if progress:
            progress("engine_done", None, None)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "latest-tag":
        try:
            print(fetch_latest_release(argv[2]).tag)
            return 0
        except UpdateError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    print(f"Usage: {argv[0]} latest-tag OWNER/REPOSITORY", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
