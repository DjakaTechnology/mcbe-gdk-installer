#!/usr/bin/env python3
"""Standalone Microsoft/Xbox authentication and WineGDK preparation."""

from __future__ import annotations

from collections.abc import Mapping

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(os.environ["MCBE_GDK_ROOT"]).expanduser().resolve()
os.environ["BOL_HOME"] = str(ROOT / "profile")
_LIB = str(ROOT / "lib")
if _LIB not in sys.path:
    sys.path.append(_LIB)

LUKAS_ENGINE_PROFILE = "lukas-remote-connect-v1"
CUSTOM_ENGINE_METADATA = ".mcbe-gdk-engine.json"
REMOTE_LOGIN_MAX_BYTES = 4096
REMOTE_LOGIN_HOSTS = {"aka.ms", "microsoft.com", "www.microsoft.com"}

from auth.auth import (  # noqa: E402
    NativeAuth,
    MsaRefreshRejected,
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
from auth.config import WINEGDK_REG  # noqa: E402
from auth.deps import ensure_login_deps  # noqa: E402
from auth.fixups import (  # noqa: E402
    _install_cryptbase_in_prefix,
    bump_stack_reserve,
    fix_curl_ssl,
    install_gdk_xbox_dlls,
)
from auth.gameinput import install_gameinput  # noqa: E402
from auth.gpu_safety import (  # noqa: E402
    acknowledge_gpu_safety_incident,
    arm_gpu_launch,
    disarm_gpu_launch,
    require_safe_graphics_session,
)
from auth.log import BolError, ok  # noqa: E402
from auth.prefix import active_prefix, boot_prefix, ensure_umu, prefix_ready  # noqa: E402
from auth.wine_registry import (  # noqa: E402
    purge_registry_staging,
    reg_delete,
    update_prefix_registry,
)


def _show_code(url: str, code: str, *, emit: bool = True) -> bool:
    message = f"Open {url}\n\nEnter code: {code}"
    prompt = (
        "Your browser should open automatically.\n\n"
        "Copy this code and complete sign-in, then click Continue.\n"
        f"If it does not open, visit {url}."
    )
    keep_waiting = True
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    if not opened:
        opener = shutil.which("xdg-open")
        command = [opener, url] if opener else None
        if not command and (opener := shutil.which("gio")):
            command = [opener, "open", url]
        if command:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    if shutil.which("kdialog"):
        result = subprocess.run(
            [
                "kdialog",
                "--title",
                "MCBE GDK Installer",
                "--inputbox",
                prompt,
                code,
                "--ok-label",
                "Continue",
                "--cancel-label",
                "Cancel",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
        )
        keep_waiting = result.returncode == 0
    elif shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--entry",
                "--title=MCBE GDK Installer",
                f"--text={prompt}",
                f"--entry-text={code}",
                "--ok-label=Continue",
                "--cancel-label=Cancel",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
        )
        keep_waiting = result.returncode == 0
    elif shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "MCBE GDK Installer sign-in", message],
            check=False,
        )
    if emit:
        print(message, flush=True)
    return keep_waiting


def active_engine_profile(root: Path = ROOT) -> str | None:
    metadata = (
        root
        / "engine"
        / "GDK-Proton-mcbe-gdk"
        / CUSTOM_ENGINE_METADATA
    )
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    profile = data.get("profile")
    return profile if isinstance(profile, str) and profile else None


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _first_element(root: ET.Element, name: str) -> ET.Element | None:
    return next(
        (element for element in root.iter() if _local_name(element) == name),
        None,
    )


def _new_lukas_game_config(appx_manifest: Path) -> ET.Element:
    try:
        package = ET.parse(appx_manifest).getroot()
    except (OSError, ET.ParseError) as exc:
        raise BolError(
            "MicrosoftGame.Config is missing and appxmanifest.xml is invalid."
        ) from exc
    identity = _first_element(package, "Identity")
    application = _first_element(package, "Application")
    properties = _first_element(package, "Properties")
    visuals = _first_element(package, "VisualElements")
    splash = _first_element(package, "SplashScreen")
    required_identity = ("Name", "Publisher", "Version")
    if (
        identity is None
        or application is None
        or any(not identity.get(name) for name in required_identity)
    ):
        raise BolError("appxmanifest.xml is missing the Minecraft identity.")

    game = ET.Element("Game", {"configVersion": "1"})
    ET.SubElement(
        game,
        "Identity",
        {name: identity.get(name, "") for name in required_identity},
    )
    executables = ET.SubElement(game, "ExecutableList")
    ET.SubElement(
        executables,
        "Executable",
        {
            "Name": application.get("Executable", "Minecraft.Windows.exe"),
            "Id": application.get("Id", "Game"),
        },
    )

    def property_text(name: str, fallback: str) -> str:
        element = (
            next(
                (
                    child
                    for child in properties
                    if _local_name(child) == name
                ),
                None,
            )
            if properties is not None
            else None
        )
        return (element.text or fallback) if element is not None else fallback

    visual = visuals.attrib if visuals is not None else {}
    ET.SubElement(
        game,
        "ShellVisuals",
        {
            "DefaultDisplayName": visual.get(
                "DisplayName", property_text("DisplayName", "Minecraft")
            ),
            "PublisherDisplayName": property_text(
                "PublisherDisplayName", "Microsoft Studios"
            ),
            "Square150x150Logo": visual.get("Square150x150Logo", "Logo.png"),
            "Square44x44Logo": visual.get("Square44x44Logo", "SmallLogo.png"),
            "StoreLogo": property_text("Logo", "StoreLogo.png"),
            "Description": visual.get(
                "Description", property_text("Description", "Minecraft")
            ),
            "ForegroundText": visual.get("ForegroundText", "light"),
            "BackgroundColor": visual.get("BackgroundColor", "transparent"),
            "SplashScreenImage": (
                splash.get("Image", "MCSplashScreen.png")
                if splash is not None
                else "MCSplashScreen.png"
            ),
        },
    )
    return game


def _write_xml(root: ET.Element, destination: Path) -> None:
    temporary = destination.with_name(
        f".{destination.name}.mcbe-{os.getpid()}"
    )
    try:
        ET.indent(root, space="  ")
        ET.ElementTree(root).write(
            temporary,
            encoding="utf-8",
            xml_declaration=True,
        )
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _apply_lukas_game_fixups(game_dir: Path) -> None:
    config = game_dir / "MicrosoftGame.Config"
    backup = game_dir / "MicrosoftGame.Config.mcbe-original"
    generated = game_dir / ".mcbe-lukas-config-generated"
    if backup.exists() and generated.exists():
        raise BolError("Minecraft identity backup state is inconsistent.")
    if config.exists() and not backup.exists() and not generated.exists():
        shutil.copy2(config, backup)

    if config.exists():
        try:
            root = ET.parse(config).getroot()
        except ET.ParseError as exc:
            raise BolError("MicrosoftGame.Config is invalid.") from exc
        if _local_name(root) != "Game":
            raise BolError("MicrosoftGame.Config has an unexpected root.")
    else:
        root = _new_lukas_game_config(game_dir / "appxmanifest.xml")
        generated.touch()

    for name, value in (
        ("MSAAppId", "0000000048183522"),
        ("TitleId", "67b57dac"),
    ):
        element = _first_element(root, name)
        if element is None:
            element = ET.SubElement(root, name)
        element.text = value
    _write_xml(root, config)

    bootstrap = game_dir / "Microsoft.WindowsAppRuntime.Bootstrap.dll"
    disabled = game_dir / "Microsoft.WindowsAppRuntime.Bootstrap.dll.mcbe-lukas-disabled"
    if bootstrap.exists() and disabled.exists():
        raise BolError("Windows App Runtime bootstrap backup state is inconsistent.")
    if bootstrap.exists():
        bootstrap.rename(disabled)


def _restore_lukas_game_fixups(game_dir: Path) -> None:
    config = game_dir / "MicrosoftGame.Config"
    backup = game_dir / "MicrosoftGame.Config.mcbe-original"
    generated = game_dir / ".mcbe-lukas-config-generated"
    if backup.exists():
        config.unlink(missing_ok=True)
        backup.rename(config)
    elif generated.exists():
        config.unlink(missing_ok=True)
    generated.unlink(missing_ok=True)

    bootstrap = game_dir / "Microsoft.WindowsAppRuntime.Bootstrap.dll"
    disabled = game_dir / "Microsoft.WindowsAppRuntime.Bootstrap.dll.mcbe-lukas-disabled"
    if bootstrap.exists() and disabled.exists():
        raise BolError("Windows App Runtime bootstrap backup state is inconsistent.")
    if disabled.exists():
        disabled.rename(bootstrap)


def apply_engine_game_profile(game_dir: Path, profile: str | None) -> None:
    if profile == LUKAS_ENGINE_PROFILE:
        _apply_lukas_game_fixups(game_dir)
    else:
        _restore_lukas_game_fixups(game_dir)


def clear_remote_login_request(path: Path) -> None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(status.st_mode)
        or status.st_uid != os.getuid()
    ):
        raise BolError("The remote login request path is unsafe.")
    path.unlink()


def read_remote_login_request(path: Path) -> tuple[str, str] | None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BolError("Could not safely open the remote login request.") from exc
    try:
        status = os.fstat(descriptor)
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_size > REMOTE_LOGIN_MAX_BYTES
        ):
            raise BolError("The remote login request is unsafe.")
        try:
            os.fchmod(descriptor, 0o600)
        except OSError as exc:
            raise BolError("Could not protect the remote login request.") from exc
        payload = os.read(descriptor, REMOTE_LOGIN_MAX_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(payload) > REMOTE_LOGIN_MAX_BYTES:
        raise BolError("The remote login request is unexpectedly large.")
    try:
        data = json.loads(payload)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(data, Mapping):
        raise BolError("The remote login request is invalid.")
    url = data.get("verification_uri") or data.get("verification_url")
    code = data.get("user_code")
    if not isinstance(url, str) or not isinstance(code, str):
        return None
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in REMOTE_LOGIN_HOSTS
        or parsed.username
        or parsed.password
    ):
        raise BolError("The remote login request has an untrusted URL.")
    code = code.strip()
    if not re.fullmatch(r"[A-Za-z0-9-]{4,32}", code):
        raise BolError("The remote login request has an invalid device code.")
    return url, code


def monitor_remote_login(
    path: Path,
    on_code,
    *,
    timeout: float | None = None,
    poll_interval: float = 0.25,
) -> bool:
    started = time.monotonic()
    seen: set[tuple[str, str]] = set()
    while timeout is None or time.monotonic() - started < timeout:
        request = read_remote_login_request(path)
        if request and request not in seen:
            seen.add(request)
            on_code(*request)
        time.sleep(poll_interval)
    return bool(seen)


def login(on_code=None) -> bool:
    if msa_signed_in():
        print(f"Already signed in{': ' + msa_gamertag() if msa_gamertag() else ''}.")
        return True
    auth = NativeAuth()

    def default_callback(url: str, code: str) -> None:
        if not _show_code(url, code):
            auth.stop()

    auth._flow(on_code or default_callback, None)  # Synchronous device-code flow.
    if auth._stop and not msa_signed_in():
        print("Sign-in cancelled.")
    return msa_signed_in()


def logout() -> None:
    prefix = active_prefix()
    try:
        if prefix_ready(prefix):
            purge_registry_staging(prefix)
            update_prefix_registry(
                prefix,
                machine=[reg_delete(WINEGDK_REG, "RefreshToken")],
            )
    except Exception as exc:
        raise BolError(
            "Could not safely clear the Microsoft token from the Wine prefix."
        ) from exc
    msa_logout()
    ok("Microsoft/Xbox account removed")


def recover_gpu() -> None:
    status = acknowledge_gpu_safety_incident()
    ok(status.message)


def performance_advisories(
    root: Path = ROOT,
    *,
    meminfo_path: Path = Path("/proc/meminfo"),
    environ: Mapping[str, str] = os.environ,
) -> list[str]:
    warnings: list[str] = []
    try:
        available_kib = next(
            int(line.split()[1])
            for line in meminfo_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("MemAvailable:")
        )
        if available_kib < 3 * 1024**2:
            warnings.append(
                f"Only {available_kib // 1024} MiB memory is available; "
                "3072 MiB or more is recommended."
            )
    except (OSError, StopIteration, ValueError):
        pass

    try:
        free_mib = shutil.disk_usage(root).free // 1024**2
        if free_mib < 5 * 1024:
            warnings.append(
                f"Only {free_mib} MiB disk space is free; "
                "5120 MiB or more is recommended."
            )
    except OSError:
        pass

    max_viewdistance = 0
    windowed_vsync = False
    options_root = root / "profile/compatdata"
    for path in options_root.rglob("options.txt") if options_root.is_dir() else ():
        try:
            options = dict(
                line.split(":", 1)
                for line in path.read_text(encoding="utf-8").splitlines()
                if ":" in line
            )
            max_viewdistance = max(
                max_viewdistance, int(options.get("gfx_viewdistance", "0"))
            )
            windowed_vsync |= (
                options.get("gfx_vsync") == "1"
                and options.get("gfx_fullscreen") == "0"
            )
        except (OSError, ValueError):
            continue

    render_chunks = max_viewdistance // 16
    if render_chunks > 32:
        warnings.append(
            f"Render distance is {render_chunks} chunks; "
            "32 chunks or lower is recommended for consistent server time."
        )
    wayland = bool(environ.get("WAYLAND_DISPLAY")) or (
        environ.get("XDG_SESSION_TYPE", "").casefold() == "wayland"
    )
    if wayland and windowed_vsync:
        warnings.append(
            "In-game VSync is enabled in a window on Wayland; "
            "fullscreen or disabling in-game VSync may reduce compositor latency."
        )
    return warnings


def prepare(game_dir: Path) -> None:
    game_dir = game_dir.resolve()
    exe = game_dir / "Minecraft.Windows.exe"
    if not exe.is_file():
        raise BolError(f"Missing game executable: {exe}")
    profile = active_engine_profile()
    apply_engine_game_profile(game_dir, profile)
    signed_in = profile != LUKAS_ENGINE_PROFILE and msa_signed_in()
    if signed_in and ensure_login_deps():
        raise BolError("Python package 'cryptography' is required for Xbox sign-in.")

    install_gdk_xbox_dlls(game_dir)
    fix_curl_ssl(game_dir)
    ensure_umu()
    if not boot_prefix():
        raise BolError("Could not initialise the Wine prefix.")
    prefix = active_prefix()
    try:
        purge_registry_staging(prefix)
    except OSError as exc:
        raise BolError("Could not clear stale Wine registry token files.") from exc
    _install_cryptbase_in_prefix()
    install_gameinput(prefix, game_dir)
    wine_apply_winegdk_prereqs()

    if profile == LUKAS_ENGINE_PROFILE:
        update_prefix_registry(
            prefix,
            machine=[reg_delete(WINEGDK_REG, "RefreshToken")],
        )
        bump_stack_reserve(exe)
        return

    if not signed_in:
        update_prefix_registry(
            prefix,
            machine=[reg_delete(WINEGDK_REG, "RefreshToken")],
        )
        bump_stack_reserve(exe)
        return

    account, epoch = msa_session_snapshot()
    refresh_token = account.get("refresh_token")
    if not refresh_token:
        raise BolError("The Microsoft session has no refresh token; sign in again.")
    try:
        fresh = msa_refresh(refresh_token)
    except MsaRefreshRejected as exc:
        msa_logout()
        update_prefix_registry(
            prefix,
            machine=[reg_delete(WINEGDK_REG, "RefreshToken")],
        )
        raise BolError(
            "The Microsoft session expired or was revoked; sign in again."
        ) from exc
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
        profile = active_engine_profile()
        if command == "engine-profile":
            if profile:
                print(profile)
            return 0
        if command == "login-monitor" and len(argv) == 3:
            if profile != LUKAS_ENGINE_PROFILE:
                return 0
            request = Path(argv[2]).expanduser().resolve()
            clear_remote_login_request(request)
            monitor_remote_login(
                request,
                lambda url, code: _show_code(url, code, emit=False),
            )
            return 0
        if command == "login":
            if profile == LUKAS_ENGINE_PROFILE:
                print(
                    "Launch Minecraft and select Sign In; "
                    "the Microsoft device code will open automatically."
                )
                return 0
            return 0 if login() else 1
        if command == "logout":
            if profile == LUKAS_ENGINE_PROFILE:
                print("Sign out from the Profile screen inside Minecraft.")
                return 0
            logout()
            return 0
        if command == "status":
            if profile == LUKAS_ENGINE_PROFILE:
                print("Account status is managed inside Minecraft.")
                return 0
            if not msa_signed_in():
                print("Not signed in.")
                return 1
            print(f"Signed in{': ' + msa_gamertag() if msa_gamertag() else ''}.")
            return 0
        if command == "performance":
            for warning in performance_advisories():
                print(f"Performance advisory: {warning}")
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
            "engine-profile|login-monitor REQUEST|ensure-umu|ensure-deps|"
            "gpu-arm|gpu-disarm TOKEN|gpu-recover"
        )
        return 2
    except BolError as exc:
        if not getattr(exc, "reported", False):
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "\nSign-in cancelled." if command == "login" else "\nCancelled.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
