"""Declarative compatibility behavior for reviewed engine repositories."""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CUSTOM_ENGINE_METADATA = ".mcbe-gdk-engine.json"
LUKAS_ENGINE_PROFILE_ID = "lukas-remote-connect-v1"


@dataclass(frozen=True)
class EngineProfile:
    identifier: str
    repository: str
    authentication: str
    msa_app_id: str | None = None
    title_id: str | None = None
    disable_app_runtime_bootstrap: bool = False
    login_request_parent_levels: int = 0

    patch_gaming_services_gate: bool = False
    def capabilities(self) -> dict[str, Any]:
        return {
            "authentication": self.authentication,
            "disable_app_runtime_bootstrap": self.disable_app_runtime_bootstrap,
            "login_request_parent_levels": self.login_request_parent_levels,
            "msa_app_id": self.msa_app_id,
            "title_id": self.title_id,
            "patch_gaming_services_gate": self.patch_gaming_services_gate,
        }


LUKAS_ENGINE_PROFILE = EngineProfile(
    identifier=LUKAS_ENGINE_PROFILE_ID,
    repository="LukasPAH/GDK-Proton-Custom",
    authentication="remote-connect-json",
    msa_app_id="0000000048183522",
    title_id="67b57dac",
    disable_app_runtime_bootstrap=True,
    login_request_parent_levels=1,
    patch_gaming_services_gate=True,
)

_PROFILES_BY_REPOSITORY = {
    LUKAS_ENGINE_PROFILE.repository.casefold(): LUKAS_ENGINE_PROFILE,
}
_PROFILES_BY_ID = {
    LUKAS_ENGINE_PROFILE.identifier: LUKAS_ENGINE_PROFILE,
}


def profile_for_repository(repository: str) -> EngineProfile | None:
    return _PROFILES_BY_REPOSITORY.get(repository.casefold())


def read_custom_engine_metadata(root: Path) -> dict[str, Any] | None:
    path = (
        Path(root)
        / "engine"
        / "GDK-Proton-mcbe-gdk"
        / CUSTOM_ENGINE_METADATA
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    required = ("repository", "tag", "asset", "url", "sha256")
    if data.get("schema") not in (1, 2) or any(
        not isinstance(data.get(key), str) or not data[key] for key in required
    ):
        return None
    return data


def installed_engine_profile(root: Path) -> EngineProfile | None:
    metadata = read_custom_engine_metadata(root)
    if not metadata:
        return None
    profile = profile_for_repository(metadata["repository"])
    if not profile or metadata.get("profile") != profile.identifier:
        return None
    if (
        metadata.get("schema") != 2
        or metadata.get("capabilities") != profile.capabilities()
    ):
        return None
    return profile
