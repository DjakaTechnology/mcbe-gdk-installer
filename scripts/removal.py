"""Filesystem operations shared by the uninstall UI and tests."""

from __future__ import annotations

import fcntl
import shutil
from contextlib import contextmanager
from pathlib import Path

LOCK_NAME = ".desktop-launch.lock"


@contextmanager
def runtime_lock(root: Path):
    path = root / "profile" / LOCK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Minecraft or another setup action is running."
            ) from exc
        yield


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def remove_minecraft(root: Path, remove_user_data: bool = False) -> None:
    _remove(root / "game")
    _remove(root / "game-dir")
    _remove(root / "game-path")
    _remove(root / "profile" / "content")

    if remove_user_data:
        profile = root / "profile"
        if profile.is_dir():
            for entry in profile.iterdir():
                if entry.name != LOCK_NAME:
                    _remove(entry)
