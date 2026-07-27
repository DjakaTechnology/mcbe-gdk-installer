"""Compatibility-engine path used by the vendored runtime."""
# SPDX-License-Identifier: MIT

from pathlib import Path

from .util import load_settings


def proton_path():
    path = load_settings().get("proton")
    return Path(path) if path else None
