"""Smoke test for the standalone runtime entry point."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RuntimeSmokeTest(unittest.TestCase):
    _PROTON_VARS = (
        "PROTON_NO_NTSYNC",
        "PROTON_ADD_CONFIG",
        "STEAM_COMPAT_CONFIG",
    )

    def _run_launch_case(
        self,
        *,
        inherited=None,
        wineserver=b"/dev/ntsync",
        wineserver_access="readable",
        grep_status=None,
        device_state="character-readable",
    ):
        repo = Path(__file__).resolve().parents[1]
        real_test = shutil.which("test")
        real_grep = shutil.which("grep")
        self.assertIsNotNone(real_test)
        self.assertIsNotNone(real_grep)

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            home = tmp / "home"
            xdg = tmp / "xdg"
            root = xdg / "mcbe-gdk-linux"
            profile = root / "profile"
            game = root / "game"
            engine = root / "engine" / "GDK-Proton-mcbe-gdk"
            wineserver_path = engine / "files" / "bin" / "wineserver"
            fake_bin = tmp / "bin"
            runtime_trace = tmp / "runtime-trace"
            umu_trace = tmp / "umu-trace"
            engine_trace = tmp / "engine-trace"
            notify_log = tmp / "notify.jsonl"
            child_env_path = tmp / "child-env.json"

            for directory in (
                home,
                game,
                wineserver_path.parent,
                fake_bin,
                root / "lib",
                profile / "umu",
            ):
                directory.mkdir(parents=True, exist_ok=True)

            (root / "game-dir").write_text(f"{game}\n", encoding="utf-8")
            (game / "Minecraft.Windows.exe").touch()

            def write_executable(path, content):
                path.write_text(content, encoding="utf-8")
                path.chmod(0o755)

            write_executable(
                engine / "proton",
                """#!/usr/bin/env bash
printf 'invoked\n' > "$NTSYNC_TEST_ENGINE_TRACE"
exit 99
""",
            )
            if wineserver is not None:
                wineserver_path.write_bytes(wineserver)
                wineserver_path.chmod(0o755)

            (root / "lib" / "runtime.py").write_text(
                """import os
import sys
from pathlib import Path

trace = Path(os.environ["NTSYNC_TEST_RUNTIME_TRACE"])
with trace.open("a", encoding="utf-8") as stream:
    stream.write(sys.argv[1] + "\\n")
if sys.argv[1] == "gpu-arm":
    print("a" * 32)
""",
                encoding="utf-8",
            )
            write_executable(
                profile / "umu" / "umu-run",
                """#!/usr/bin/env python3
import json
import os
from pathlib import Path

names = ("PROTON_NO_NTSYNC", "PROTON_ADD_CONFIG", "STEAM_COMPAT_CONFIG")
payload = {}
for name in names:
    key = os.fsencode(name)
    payload[name] = None if key not in os.environb else os.environb[key].hex()
Path(os.environ["NTSYNC_TEST_CHILD_ENV"]).write_text(
    json.dumps(payload), encoding="utf-8"
)
Path(os.environ["NTSYNC_TEST_UMU_TRACE"]).write_text("invoked\\n", encoding="utf-8")
""",
            )
            write_executable(
                fake_bin / "notify-send",
                """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["NTSYNC_TEST_NOTIFY_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
""",
            )
            write_executable(
                fake_bin / "test",
                """#!/usr/bin/env bash
if [[ "$#" -eq 2 && "$2" == "$NTSYNC_TEST_WINESERVER" ]]; then
  case "$1" in
    -f) [[ -f "$2" ]]; exit ;;
    -r) [[ "$NTSYNC_TEST_WINESERVER_ACCESS" == readable ]]; exit ;;
  esac
fi
if [[ "$#" -eq 2 && "$2" == /dev/ntsync ]]; then
  case "$1" in
    -e) [[ "$NTSYNC_TEST_DEVICE_STATE" != missing ]]; exit ;;
    -c) [[ "$NTSYNC_TEST_DEVICE_STATE" == character-* ]]; exit ;;
    -r) [[ "$NTSYNC_TEST_DEVICE_STATE" == character-readable ]]; exit ;;
  esac
fi
exec "$NTSYNC_TEST_REAL_TEST" "$@"
""",
            )
            write_executable(
                fake_bin / "grep",
                """#!/usr/bin/env bash
last="${!#}"
if [[ "$last" == "$NTSYNC_TEST_WINESERVER" &&
      -n "${NTSYNC_TEST_GREP_STATUS+x}" ]]; then
  exit "$NTSYNC_TEST_GREP_STATUS"
fi
exec "$NTSYNC_TEST_REAL_GREP" "$@"
""",
            )
            bash_env = tmp / "bash-env"
            bash_env.write_text("enable -n test\n", encoding="utf-8")

            fixtures = {
                profile / "msa" / "token.json": (b'{"refresh_token":"secret"}\n', 0o600),
                profile / "winegdk-preauth" / "device.json": (
                    b'{"xbl_gamertag":"player"}\n',
                    0o600,
                ),
                profile / "compatdata" / "pfx" / "system.reg": (
                    b"WINE REGISTRY Version 2\n# machine secret\n",
                    0o600,
                ),
                profile / "compatdata" / "pfx" / "user.reg": (
                    b"WINE REGISTRY Version 2\n# user state\n",
                    0o640,
                ),
            }
            for path, (content, mode) in fixtures.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                path.chmod(mode)

            def fixture_snapshot():
                return {
                    str(path.relative_to(profile)): {
                        "bytes": path.read_bytes(),
                        "mode": stat.S_IMODE(path.stat().st_mode),
                    }
                    for path in fixtures
                }

            before = fixture_snapshot()
            env = os.environ.copy()
            for name in self._PROTON_VARS:
                env.pop(name, None)
            for name, value in (inherited or {}).items():
                self.assertIn(name, self._PROTON_VARS)
                env[name] = value
            env.update({
                "HOME": str(home),
                "XDG_DATA_HOME": str(xdg),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "BASH_ENV": str(bash_env),
                "NTSYNC_TEST_WINESERVER": str(wineserver_path),
                "NTSYNC_TEST_WINESERVER_ACCESS": wineserver_access,
                "NTSYNC_TEST_DEVICE_STATE": device_state,
                "NTSYNC_TEST_REAL_TEST": real_test,
                "NTSYNC_TEST_REAL_GREP": real_grep,
                "NTSYNC_TEST_RUNTIME_TRACE": str(runtime_trace),
                "NTSYNC_TEST_UMU_TRACE": str(umu_trace),
                "NTSYNC_TEST_ENGINE_TRACE": str(engine_trace),
                "NTSYNC_TEST_NOTIFY_LOG": str(notify_log),
                "NTSYNC_TEST_CHILD_ENV": str(child_env_path),
            })
            if grep_status is None:
                env.pop("NTSYNC_TEST_GREP_STATUS", None)
            else:
                env["NTSYNC_TEST_GREP_STATUS"] = str(grep_status)

            result = subprocess.run(
                ["bash", repo / "scripts" / "launch.sh"],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            log_path = profile / "logs" / "desktop-launch.log"
            notifications = []
            if notify_log.exists():
                notifications = [
                    json.loads(line)
                    for line in notify_log.read_text(encoding="utf-8").splitlines()
                ]
            child_env = {}
            if child_env_path.exists():
                child_env = json.loads(child_env_path.read_text(encoding="utf-8"))
            commands = []
            if runtime_trace.exists():
                commands = runtime_trace.read_text(encoding="utf-8").splitlines()

            return {
                "result": result,
                "log": log_path.read_text(encoding="utf-8") if log_path.exists() else "",
                "notifications": notifications,
                "child_env": child_env,
                "runtime_trace": {
                    "commands": commands,
                    "umu": umu_trace.exists(),
                    "engine": engine_trace.exists(),
                },
                "fixture_state": {
                    "before": before,
                    "after": fixture_snapshot(),
                },
            }

    def test_login_code_opens_browser_and_uses_copyable_dialog(self):
        repo = Path(__file__).resolve().parents[1]
        code = """
from unittest.mock import patch

from scripts import runtime

url = "https://www.microsoft.com/link"
device_code = "ABCD1234"

def which(name):
    return f"/usr/bin/{name}" if name in {"xdg-open", "kdialog"} else None

with patch.object(runtime.webbrowser, "open", return_value=False) as browser, \\
     patch.object(runtime.shutil, "which", side_effect=which), \\
     patch.object(runtime.subprocess, "Popen") as popen, \\
     patch.object(runtime.subprocess, "run") as run:
    run.return_value.returncode = 0
    assert runtime._show_code(url, device_code)

browser.assert_called_once_with(url)
assert popen.call_args.args[0] == ["/usr/bin/xdg-open", url]
dialog = run.call_args.args[0]
assert "--inputbox" in dialog
prompt_index = dialog.index("--inputbox")
assert url in dialog[prompt_index + 1]
assert dialog[prompt_index + 2] == device_code
assert "Continue" in dialog

with patch.object(runtime, "login", side_effect=KeyboardInterrupt):
    assert runtime.main(["runtime.py", "login"]) == 130
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo,
            env={**os.environ, "MCBE_GDK_ROOT": str(repo)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("Sign-in cancelled.", result.stderr)

    def test_gui_uses_the_installed_profile_for_auth(self):
        gui = (
            Path(__file__).resolve().parents[1] / "scripts" / "gui.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            gui.index('os.environ["BOL_HOME"] = str(ROOT / "profile")'),
            gui.index("from auth.auth import"),
        )

    def test_launcher_does_not_override_system_tls_policy(self):
        launch = (
            Path(__file__).resolve().parents[1] / "scripts" / "launch.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("GNUTLS_SYSTEM_PRIORITY_FILE", launch)
        self.assertNotIn("gnutls-no-tls13", launch)

    def test_launcher_ntsync_legacy_proton_flags_do_not_change_status(self):
        expected = "NTSync preflight: static prerequisites present."
        cases = (
            ("absent", {}),
            ("direct", {"PROTON_NO_NTSYNC": "1"}),
            ("add config", {"PROTON_ADD_CONFIG": "foo,nontsync"}),
            ("steam config", {"STEAM_COMPAT_CONFIG": "foo,nontsync"}),
            (
                "combined",
                {
                    "PROTON_NO_NTSYNC": "false",
                    "PROTON_ADD_CONFIG": "foo,nontsync",
                    "STEAM_COMPAT_CONFIG": r"cmdlineappend:--foo\,bar,nontsync",
                },
            ),
        )
        for name, inherited in cases:
            with self.subTest(name=name):
                case = self._run_launch_case(inherited=inherited)
                lines = [
                    line for line in case["log"].splitlines()
                    if line.startswith("NTSync preflight:")
                ]
                self.assertEqual(lines, [expected])
                self.assertEqual(
                    case["child_env"],
                    {
                        key: (
                            None if key not in inherited
                            else os.fsencode(inherited[key]).hex()
                        )
                        for key in self._PROTON_VARS
                    },
                )
                notifications = [
                    item for item in case["notifications"]
                    if len(item) >= 2
                    and item[-2] == "NTSync performance path unavailable"
                ]
                self.assertEqual(notifications, [])

    def test_launcher_ntsync_classifies_static_prerequisites(self):
        cases = (
            (
                "wineserver missing",
                {"wineserver": None},
                "NTSync preflight: engine wineserver is missing or unreadable; "
                "update or reinstall the engine.",
            ),
            (
                "wineserver unreadable",
                {"wineserver_access": "unreadable"},
                "NTSync preflight: engine wineserver is missing or unreadable; "
                "update or reinstall the engine.",
            ),
            (
                "marker absent",
                {"grep_status": 1},
                "NTSync preflight: engine wineserver lacks /dev/ntsync support; "
                "update or reinstall the engine.",
            ),
            (
                "marker error",
                {"grep_status": 2},
                "NTSync preflight: could not inspect engine wineserver; "
                "update or reinstall the engine.",
            ),
            (
                "device missing",
                {"device_state": "missing"},
                "NTSync preflight: /dev/ntsync is missing; use Linux 6.14+ or "
                "a distribution NTSync backport and load the module.",
            ),
            (
                "device regular",
                {"device_state": "regular-readable"},
                "NTSync preflight: /dev/ntsync is not a character device; "
                "repair the distribution device node.",
            ),
            (
                "device unreadable",
                {"device_state": "character-unreadable"},
                "NTSync preflight: /dev/ntsync is unreadable; repair the "
                "distribution device permissions.",
            ),
            (
                "static success",
                {"device_state": "character-readable"},
                "NTSync preflight: static prerequisites present.",
            ),
        )
        for name, options, expected in cases:
            with self.subTest(name=name):
                case = self._run_launch_case(**options)
                lines = [
                    line for line in case["log"].splitlines()
                    if line.startswith("NTSync preflight:")
                ]
                self.assertEqual(case["result"].returncode, 0, case["result"].stderr)
                self.assertEqual(lines, [expected])
                notifications = [
                    item for item in case["notifications"]
                    if len(item) >= 2
                    and item[-2] == "NTSync performance path unavailable"
                ]
                self.assertEqual(len(notifications), 0 if name == "static success" else 1)

    def test_launcher_ntsync_is_advisory_and_preserves_auth_state(self):
        cases = (
            ("success", {}, {}),
            (
                "legacy override ignored",
                {"inherited": {"PROTON_NO_NTSYNC": "private-direct-value"}},
                {"PROTON_NO_NTSYNC": "private-direct-value"},
            ),
            (
                "engine failure",
                {
                    "inherited": {
                        "PROTON_NO_NTSYNC": "0",
                        "PROTON_ADD_CONFIG": "private-add-value",
                        "STEAM_COMPAT_CONFIG": "private-steam-value",
                    },
                    "wineserver": None,
                },
                {
                    "PROTON_NO_NTSYNC": "0",
                    "PROTON_ADD_CONFIG": "private-add-value",
                    "STEAM_COMPAT_CONFIG": "private-steam-value",
                },
            ),
            (
                "device failure",
                {
                    "inherited": {
                        "PROTON_NO_NTSYNC": "",
                        "PROTON_ADD_CONFIG": "private-add-value",
                        "STEAM_COMPAT_CONFIG": "nontsync",
                    },
                    "device_state": "missing",
                },
                {
                    "PROTON_NO_NTSYNC": "",
                    "PROTON_ADD_CONFIG": "private-add-value",
                    "STEAM_COMPAT_CONFIG": "nontsync",
                },
            ),
        )
        for name, options, expected_env in cases:
            with self.subTest(name=name):
                case = self._run_launch_case(**options)
                result = case["result"]
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    case["runtime_trace"]["commands"],
                    ["prepare", "gpu-arm", "gpu-disarm"],
                )
                self.assertTrue(case["runtime_trace"]["umu"])
                self.assertFalse(case["runtime_trace"]["engine"])
                self.assertEqual(
                    case["fixture_state"]["before"],
                    case["fixture_state"]["after"],
                )
                expected_child = {
                    key: (
                        None if key not in expected_env
                        else os.fsencode(expected_env[key]).hex()
                    )
                    for key in self._PROTON_VARS
                }
                self.assertEqual(case["child_env"], expected_child)
                rendered = (
                    case["log"]
                    + result.stdout
                    + result.stderr
                    + json.dumps(case["notifications"])
                )
                for value in expected_env.values():
                    if value.startswith("private-"):
                        self.assertNotIn(value, rendered)


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
