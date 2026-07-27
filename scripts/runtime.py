#!/usr/bin/env python3
"""Standalone Microsoft/Xbox authentication and WineGDK preparation."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(os.environ["MCBE_GDK_ROOT"]).expanduser().resolve()
os.environ["BOL_HOME"] = str(ROOT / "profile")
sys.path.insert(0, str(ROOT / "lib"))

from bol.auth import (  # noqa: E402
    NativeAuth,
    msa_gamertag,
    msa_logout,
    msa_refresh,
    msa_save_for_account_epoch,
    msa_session_snapshot,
    msa_signed_in,
    wine_apply_winegdk_prereqs,
    wine_reg_set_refresh_token,
    xbl_preauth,
    xbl_preauth_error_message,
)
from bol.config import WINEGDK_REG  # noqa: E402
from bol.deps import ensure_login_deps  # noqa: E402
from bol.fixups import (  # noqa: E402
    _install_cryptbase_in_prefix,
    bump_stack_reserve,
    fix_curl_ssl,
    install_gdk_xbox_dlls,
)
from bol.gameinput import install_gameinput  # noqa: E402
from bol.gpu_safety import (  # noqa: E402
    acknowledge_gpu_safety_incident,
    arm_gpu_launch,
    disarm_gpu_launch,
    require_safe_graphics_session,
)
from bol.log import BolError, ok  # noqa: E402
from bol.prefix import active_prefix, boot_prefix, ensure_umu, prefix_ready  # noqa: E402
from bol.wine_registry import reg_delete, update_prefix_registry  # noqa: E402


def _show_code(url: str, code: str) -> None:
    message = f"Open {url}\n\nEnter code: {code}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    if shutil.which("kdialog"):
        subprocess.run(
            ["kdialog", "--title", "MCBE GDK Linux", "--msgbox", message],
            check=False,
        )
    elif shutil.which("zenity"):
        subprocess.run(
            ["zenity", "--info", "--title=MCBE GDK Linux", f"--text={message}"],
            check=False,
        )
    elif shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "MCBE GDK Linux sign-in", message],
            check=False,
        )
    print(message, flush=True)


def login() -> bool:
    if msa_signed_in():
        print(f"Already signed in{': ' + msa_gamertag() if msa_gamertag() else ''}.")
        return True
    auth = NativeAuth()
    auth._flow(_show_code, None)  # Upstream synchronous device-code flow.
    return msa_signed_in()


def logout() -> None:
    prefix = active_prefix()
    if prefix_ready(prefix):
        update_prefix_registry(
            prefix,
            machine=[reg_delete(WINEGDK_REG, "RefreshToken")],
        )
    msa_logout()
    ok("Microsoft/Xbox account removed")


def recover_gpu() -> None:
    status = acknowledge_gpu_safety_incident()
    ok(status.message)


def prepare(game_dir: Path) -> None:
    game_dir = game_dir.resolve()
    exe = game_dir / "Minecraft.Windows.exe"
    if not exe.is_file():
        raise BolError(f"Missing game executable: {exe}")
    if ensure_login_deps():
        raise BolError("Python package 'cryptography' is required for Xbox sign-in.")
    if not msa_signed_in() and not login():
        raise BolError("Microsoft sign-in did not complete.")

    install_gdk_xbox_dlls(game_dir)
    fix_curl_ssl(game_dir)
    ensure_umu()
    if not boot_prefix():
        raise BolError("Could not initialise the Wine prefix.")
    _install_cryptbase_in_prefix()
    install_gameinput(active_prefix(), game_dir)
    wine_apply_winegdk_prereqs()

    account, epoch = msa_session_snapshot()
    refresh_token = account.get("refresh_token")
    if not refresh_token:
        raise BolError("The Microsoft session has no refresh token; sign in again.")
    try:
        fresh = msa_refresh(refresh_token)
    except Exception:
        fresh = None
    if fresh:
        if not msa_save_for_account_epoch(
            {
                "refresh_token": fresh["refresh_token"],
                "obtained": int(time.time()),
            },
            epoch,
        ):
            raise BolError("The Microsoft account changed during sign-in.")
        refresh_token = fresh["refresh_token"]
    if not wine_reg_set_refresh_token(refresh_token):
        raise BolError("Could not store the Microsoft token in the Wine prefix.")
    if not xbl_preauth((fresh or {}).get("access_token", ""), epoch):
        raise BolError(
            xbl_preauth_error_message()
            or "Could not prepare the Xbox Live session."
        )
    bump_stack_reserve(exe)


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "status"
    try:
        if command == "login":
            return 0 if login() else 1
        if command == "logout":
            logout()
            return 0
        if command == "status":
            if not msa_signed_in():
                print("Not signed in.")
                return 1
            print(f"Signed in{': ' + msa_gamertag() if msa_gamertag() else ''}.")
            return 0
        if command == "prepare" and len(argv) == 3:
            prepare(Path(argv[2]))
            return 0
        if command == "ensure-umu":
            ensure_umu()
            return 0
        if command == "ensure-deps":
            return 1 if ensure_login_deps() else 0
        if command == "gpu-arm":
            require_safe_graphics_session()
            print(arm_gpu_launch())
            return 0
        if command == "gpu-disarm" and len(argv) == 3:
            return 0 if disarm_gpu_launch(argv[2]) else 1
        if command == "gpu-recover":
            recover_gpu()
            return 0
        print(
            f"Usage: {argv[0]} login|logout|status|prepare GAME_DIR|"
            "ensure-umu|ensure-deps|gpu-arm|gpu-disarm TOKEN|gpu-recover"
        )
        return 2
    except BolError as exc:
        if not getattr(exc, "reported", False):
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
