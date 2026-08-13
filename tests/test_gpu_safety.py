"""Regression tests for Gamescope session recognition in GPU safety."""
# SPDX-License-Identifier: MIT

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from auth import gpu_safety


class _Result:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class _CleanJournal:
    def __call__(self, *_args, **_kwargs):
        return _Result(returncode=1)


class GamescopeSessionTests(unittest.TestCase):
    def _problem(self, env, *, atom_probe=None):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "marker.json"
            with mock.patch.object(
                    gpu_safety, "GPU_LAUNCH_MARKER", marker):
                return gpu_safety.graphics_safety_problem(
                    environ=env,
                    xrandr_runner=lambda *_a, **_k: _Result("Providers: number : 0\n"),
                    journal_runner=_CleanJournal(),
                    atom_probe=atom_probe,
                )

    def test_sandboxed_gamescope_is_recognised_without_its_variables(self):
        # A Flatpak/Game Mode sandbox drops the GAMESCOPE_* environment, so
        # in Steam Deck Game Mode the launcher saw a plain X11 session with
        # zero RandR providers and refused to start. The root-window atoms
        # still identify Gamescope even when the variables are gone.
        self.assertIsNone(self._problem(
            {"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11"},
            atom_probe=lambda _env: True,
        ))

    def test_root_atoms_are_not_probed_when_the_environment_already_says_so(self):
        def must_not_run(_env):
            self.fail("root atoms must not be probed when GAMESCOPE_* is set")
        self.assertIsNone(self._problem(
            {"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11",
             "GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0"},
            atom_probe=must_not_run,
        ))

    def test_root_atom_probe_needs_a_display(self):
        self.assertFalse(gpu_safety._gamescope_root_atoms({}))
        self.assertFalse(gpu_safety._gamescope_root_atoms({"DISPLAY": "  "}))


if __name__ == "__main__":
    unittest.main()
