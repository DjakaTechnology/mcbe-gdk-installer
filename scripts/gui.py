#!/usr/bin/env python3
"""Modern GTK4 desktop UI for installation, authentication, and launching."""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk
except (ImportError, ValueError) as exc:
    raise SystemExit(
        "GTK4 and Libadwaita are required "
        "(Arch: sudo pacman -S gtk4 libadwaita python-gobject)."
    ) from exc

ROOT = Path(os.environ["MCBE_GDK_ROOT"]).expanduser().resolve()
TOOL_ROOT = Path(os.environ.get("MCBE_GDK_TOOL_ROOT") or ".").expanduser().resolve()
os.environ["BOL_HOME"] = str(ROOT / "profile")
for path in (ROOT / "lib", TOOL_ROOT / "scripts", TOOL_ROOT):
    sys.path.insert(0, str(path))

from auth.auth import msa_gamertag, msa_signed_in  # noqa: E402
from removal import (  # noqa: E402
    minecraft_launcher_pid,
    remove_minecraft,
    runtime_lock,
    stop_minecraft,
)
from runtime import login, logout  # noqa: E402
from updates import (  # noqa: E402
    AvailableUpdates,
    UpdateError,
    check_for_updates,
    install_available_updates,
)

APP_ID = "io.github.veedydev.MCBEGDKInstaller"
APP_NAME = "MCBE GDK Installer"


def package_button_state(installed: bool, selected: bool) -> tuple[str, bool]:
    if selected:
        return ("Update" if installed else "Install", False)
    return ("Uninstall", True) if installed else ("Install", False)


def launch_button_state(
    installed: bool,
    busy: bool,
    running: bool,
    starting: bool,
    stopping: bool,
) -> tuple[str, bool, bool, bool]:
    if busy:
        return ("Launch", False, False, False)
    if running:
        return ("Stopping…" if stopping else "Stop", not stopping, stopping, True)
    if starting:
        return ("Starting…", False, True, False)
    return ("Launch", installed, False, False)


def installation_status(line: str) -> tuple[str, str] | None:
    stages = (
        ("Reading the package", ("Reading package…", "Inspecting the selected build.")),
        ("Downloading XVDTool", ("Downloading extraction tools…", "One-time setup download.")),
        ("Downloading dotnet-runtime", ("Downloading .NET runtime…", "One-time setup download.")),
        ("Downloading GDK_", ("Downloading Microsoft GDK files…", "One-time setup download.")),
        ("Extracting the public GDK test key", ("Preparing package key…", "Using the public GDK test key.")),
        ("Decrypting the test package", ("Decrypting package…", "Preparing the authorized game files.")),
        ("Extracting game content", ("Extracting game files…", "Large packages can take several minutes.")),
        (
            "Downloading the MCBE GDK compatibility engine",
            (
                "Downloading compatibility engine…",
                "0% of about 800 MB downloaded.",
            ),
        ),
        (
            "Verifying the MCBE GDK compatibility engine",
            ("Verifying compatibility engine…", "Checking the release checksum."),
        ),
        (
            "Installing the MCBE GDK compatibility engine",
            ("Installing compatibility engine…", "Verifying and extracting the runtime."),
        ),
        ("Downloading umu-launcher", ("Downloading launcher runtime…", "Preparing the Linux launcher.")),
        ("Installed successfully", ("Finishing installation…", "Saving launchers and settings.")),
    )
    return next((status for marker, status in stages if marker in line), None)


def curl_progress_percent(line: str) -> int | None:
    match = re.match(r"\s*\d{1,3}\s+\S+\s+(\d{1,3})\s+\S+", line)
    if not match:
        return None
    percent = int(match.group(1))
    return percent if 0 <= percent <= 100 else None


def display_size(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.1f} GB"
    if size >= 1024**2:
        return f"{size / 1024**2:.0f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def update_progress_status(
    stage: str,
    current: int | None,
    total: int | None,
) -> tuple[str, str, float | None]:
    title, subtitle = {
        "engine_download": (
            "Downloading compatibility engine…",
            "This is the largest part of the update.",
        ),
        "engine_verify": (
            "Verifying compatibility engine…",
            "Checking the release checksum.",
        ),
        "engine_install": (
            "Installing compatibility engine…",
            "Extracting and replacing the runtime files.",
        ),
        "engine_done": (
            "Compatibility engine updated",
            "Finishing the remaining updates.",
        ),
        "installer_download": (
            "Downloading MCBE GDK Installer…",
            "Fetching the verified installer release.",
        ),
        "installer_verify": (
            "Verifying MCBE GDK Installer…",
            "Checking the release checksum.",
        ),
        "installer_install": (
            "Installing MCBE GDK Installer…",
            "Replacing the installer and refreshing launchers.",
        ),
        "installer_done": (
            "MCBE GDK Installer updated",
            "The update is complete.",
        ),
    }.get(stage, ("Installing updates…", "Working on the selected updates."))
    if not stage.endswith("_download") or current is None:
        return title, subtitle, None
    if not total:
        return title, f"{display_size(current)} downloaded.", None
    fraction = min(current / total, 1)
    percent = round(fraction * 100)
    return (
        title,
        f"{percent}% · {display_size(current)} of {display_size(total)} downloaded.",
        fraction,
    )


def configure_color_scheme() -> None:
    Gtk.init()
    settings = Gtk.Settings.get_default()
    if not settings:
        return
    prefer_dark = settings.get_property("gtk-application-prefer-dark-theme")
    settings.set_property("gtk-application-prefer-dark-theme", False)
    if prefer_dark:
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.PREFER_DARK
        )


class Window(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(application=application, title=APP_NAME)
        self.set_default_size(780, 700)
        self.set_size_request(560, 560)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.package: Path | None = None
        self.signin_dialog: Adw.Dialog | None = None
        self.installing = False
        self.engine_downloading = False
        self.was_updating = False
        self.available_updates: AvailableUpdates | None = None
        self.updating = False
        self.update_pulsing = False
        self.update_stage: str | None = None
        self.update_log_bucket = -1
        self.launch_process: subprocess.Popen | None = None
        self.stopping = False

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        self.overlay = Adw.ToastOverlay()
        toolbar.set_content(self.overlay)
        self.set_content(toolbar)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        self.overlay.set_child(scroller)
        clamp = Adw.Clamp(maximum_size=720, tightening_threshold=560)
        scroller.set_child(clamp)
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            margin_top=30,
            margin_bottom=30,
            margin_start=24,
            margin_end=24,
        )
        clamp.set_child(content)

        self.update_group = Adw.PreferencesGroup(visible=False)
        self.update_row = Adw.ActionRow(
            title="Update available",
            subtitle="Review changes before installing.",
        )
        self.update_row.add_prefix(
            Gtk.Image(
                icon_name="software-update-available-symbolic",
                valign=Gtk.Align.CENTER,
            )
        )
        self.update_button = Gtk.Button(label="Update", valign=Gtk.Align.CENTER)
        self.update_button.add_css_class("suggested-action")
        self.update_button.connect("clicked", self.review_update)
        self.update_spinner = Gtk.Spinner(visible=False, valign=Gtk.Align.CENTER)
        self.update_row.add_suffix(self.update_spinner)
        self.update_row.add_suffix(self.update_button)
        self.update_group.add(self.update_row)
        self.update_progress = Gtk.ProgressBar(
            visible=False,
            margin_top=8,
            margin_bottom=4,
        )
        self.update_group.add(self.update_progress)
        self.update_details = Gtk.Expander(label="Update details", visible=False)
        update_log_scroll = Gtk.ScrolledWindow(
            min_content_height=120,
            max_content_height=200,
            propagate_natural_height=True,
        )
        self.update_log = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=10,
            right_margin=10,
            top_margin=10,
            bottom_margin=10,
        )
        update_log_scroll.set_child(self.update_log)
        self.update_details.set_child(update_log_scroll)
        self.update_group.add(self.update_details)
        content.append(self.update_group)

        install_group = Adw.PreferencesGroup(title="Package")
        content.append(install_group)
        self.package_row = Adw.ActionRow(
            title="Select a package", subtitle="ZIP, MSIXVC, or MSIXV"
        )
        choose_button = Gtk.Button(label="Select…", valign=Gtk.Align.CENTER)
        choose_button.connect("clicked", self.choose)
        self.package_row.add_suffix(choose_button)
        self.package_row.set_activatable_widget(choose_button)
        install_group.add(self.package_row)

        self.install_row = Adw.ActionRow(
            title="Not installed",
        )
        self.install_icon = Gtk.Image(
            icon_name="folder-download-symbolic", valign=Gtk.Align.CENTER
        )
        self.install_button = Gtk.Button(label="Install", valign=Gtk.Align.CENTER)
        self.install_button.add_css_class("suggested-action")
        self.install_button.connect("clicked", self.package_action)
        self.install_row.add_prefix(self.install_icon)
        self.install_row.add_suffix(self.install_button)
        install_group.add(self.install_row)

        self.progress = Gtk.ProgressBar(visible=False, margin_top=8, margin_bottom=4)
        install_group.add(self.progress)

        details = Gtk.Expander(label="Installation details")
        log_scroll = Gtk.ScrolledWindow(
            min_content_height=190, max_content_height=280, propagate_natural_height=True
        )
        self.log = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=10,
            right_margin=10,
            top_margin=10,
            bottom_margin=10,
        )
        log_scroll.set_child(self.log)
        details.set_child(log_scroll)
        install_group.add(details)

        account_group = Adw.PreferencesGroup(title="Account")
        content.append(account_group)
        self.account_row = Adw.ActionRow(title="Not connected")
        self.account_icon = Gtk.Image(
            icon_name="avatar-default-symbolic", valign=Gtk.Align.CENTER
        )
        self.login_button = Gtk.Button(label="Sign in", valign=Gtk.Align.CENTER)
        self.login_button.add_css_class("suggested-action")
        self.login_button.connect("clicked", self.sign_in)
        self.logout_button = Gtk.Button(label="Sign out", valign=Gtk.Align.CENTER)
        self.logout_button.connect("clicked", self.sign_out)
        self.account_row.add_prefix(self.account_icon)
        self.account_row.add_suffix(self.login_button)
        self.account_row.add_suffix(self.logout_button)
        account_group.add(self.account_row)

        launch_group = Adw.PreferencesGroup()
        content.append(launch_group)
        launch_row = Adw.ActionRow(title="Minecraft Bedrock")
        launch_row.add_prefix(
            Gtk.Image(icon_name="applications-games-symbolic", valign=Gtk.Align.CENTER)
        )
        launch_content = Gtk.Box(spacing=8)
        self.launch_spinner = Gtk.Spinner(visible=False)
        self.launch_label = Gtk.Label(label="Launch")
        launch_content.append(self.launch_spinner)
        launch_content.append(self.launch_label)
        self.launch_button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.launch_button.set_child(launch_content)
        self.launch_button.add_css_class("suggested-action")
        self.launch_button.connect("clicked", self.launch_action)
        launch_row.add_suffix(self.launch_button)
        launch_group.add(launch_row)

        self.refresh_install()
        self.refresh_account()
        GLib.timeout_add(100, self.poll)
        GLib.timeout_add(500, self.refresh_launch_state)
        self.check_updates()

    def toast(self, message: str) -> None:
        self.overlay.add_toast(Adw.Toast.new(message))

    def set_launch_button(self, label: str, loading: bool) -> None:
        self.launch_label.set_label(label)
        self.launch_spinner.set_visible(loading)
        if loading:
            self.launch_spinner.start()
        else:
            self.launch_spinner.stop()

    def error(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("close", "Close")
        dialog.present(self)

    def check_updates(self) -> None:
        def worker() -> None:
            try:
                updates = check_for_updates(TOOL_ROOT, ROOT)
            except UpdateError:
                return
            if updates:
                self.events.put(("updates_available", updates))

        threading.Thread(target=worker, daemon=True).start()

    def show_updates(self, updates: AvailableUpdates) -> None:
        self.available_updates = updates
        if updates.installer and updates.engine:
            title = "Installer and engine updates are available"
            subtitle = (
                f"Installer {updates.installer.tag} · "
                f"Compatibility engine {updates.engine.tag}"
            )
        elif updates.installer:
            title = f"MCBE GDK Installer {updates.installer.tag} is available"
            subtitle = "Review changes before installing."
        else:
            assert updates.engine
            title = f"Compatibility engine {updates.engine.tag} is available"
            subtitle = "Review changes before installing."
        self.update_row.set_title(title)
        self.update_row.set_subtitle(subtitle)
        self.update_button.set_label("Update")
        self.update_button.set_visible(True)
        self.update_spinner.set_visible(False)
        self.update_progress.set_visible(False)
        self.update_details.set_visible(False)
        self.update_group.set_visible(True)

    def review_update(self, _button: Gtk.Button) -> None:
        updates = self.available_updates
        if not updates or self.updating:
            return
        dialog = Adw.AlertDialog(
            heading="Install available updates?",
            body="Review what changed. Minecraft, worlds, and account data are preserved.",
        )
        changelog = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_top=4,
            margin_end=8,
        )
        releases = [
            ("MCBE GDK Installer", updates.installer),
            ("Compatibility engine", updates.engine),
        ]
        shown = 0
        for component, release in releases:
            if not release:
                continue
            if shown:
                changelog.append(Gtk.Separator())
            heading = Gtk.Label(
                label=f"{component} · {release.tag}",
                xalign=0,
            )
            heading.add_css_class("heading")
            changelog.append(heading)
            notes = Gtk.Label(
                label=release.body.strip() or "Maintenance and compatibility improvements.",
                xalign=0,
                wrap=True,
                selectable=True,
                max_width_chars=52,
            )
            notes.add_css_class("dim-label")
            changelog.append(notes)
            shown += 1
        scroll = Gtk.ScrolledWindow(
            min_content_height=110,
            max_content_height=220,
            propagate_natural_height=True,
        )
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(changelog)
        dialog.set_extra_child(scroll)
        dialog.add_response("later", "Later")
        dialog.add_response("update", "Install updates")
        dialog.set_default_response("later")
        dialog.set_close_response("later")
        dialog.set_response_appearance(
            "update", Adw.ResponseAppearance.SUGGESTED
        )
        dialog.connect("response", self.update_response)
        dialog.present(self)

    def update_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        updates = self.available_updates
        if response != "update" or not updates:
            return
        if minecraft_launcher_pid(ROOT):
            self.error(
                "Close Minecraft before updating",
                "Installer files cannot be replaced while Minecraft is running.",
            )
            return
        self.updating = True
        self.update_pulsing = True
        self.update_stage = None
        self.update_log_bucket = -1
        self.update_row.set_title("Preparing updates…")
        self.update_row.set_subtitle("Starting the verified update.")
        self.update_button.set_visible(False)
        self.update_spinner.set_visible(True)
        self.update_spinner.start()
        self.update_progress.set_visible(True)
        self.update_progress.set_fraction(0)
        self.update_progress.pulse()
        self.update_details.set_visible(True)
        self.update_log.get_buffer().set_text("Preparing selected updates…\n")
        GLib.timeout_add(120, self.pulse_update_progress)
        self.install_button.set_sensitive(False)
        self.login_button.set_sensitive(False)
        self.logout_button.set_sensitive(False)
        self.refresh_launch_state()

        def worker() -> None:
            try:
                def progress(
                    stage: str,
                    current: int | None,
                    total: int | None,
                ) -> None:
                    self.events.put(("update_progress", stage, current, total))

                with runtime_lock(ROOT):
                    restart = install_available_updates(
                        updates, TOOL_ROOT, ROOT, progress
                    )
                self.events.put(("updates_done", restart))
            except Exception as exc:
                self.events.put(("update_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def pulse_update_progress(self) -> bool:
        if self.updating and self.update_pulsing:
            self.update_progress.pulse()
        return self.updating

    def write_update_detail(self, text: str) -> None:
        buffer = self.update_log.get_buffer()
        buffer.insert(buffer.get_end_iter(), text)
        self.update_log.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 1)

    def show_update_progress(
        self,
        stage: str,
        current: int | None,
        total: int | None,
    ) -> None:
        title, subtitle, fraction = update_progress_status(stage, current, total)
        self.update_row.set_title(title)
        self.update_row.set_subtitle(subtitle)
        self.update_pulsing = fraction is None
        if fraction is None:
            self.update_progress.pulse()
        else:
            self.update_progress.set_fraction(fraction)

        if stage != self.update_stage:
            self.update_stage = stage
            self.update_log_bucket = -1
            self.write_update_detail(f"\n{title}\n")
            if not stage.endswith("_download"):
                self.write_update_detail(f"  {subtitle}\n")
        if fraction is not None:
            percent = round(fraction * 100)
            bucket = percent // 10
            if bucket > self.update_log_bucket:
                self.update_log_bucket = bucket
                self.write_update_detail(f"  {subtitle}\n")

    def prompt_restart(self) -> None:
        dialog = Adw.AlertDialog(
            heading="Update installed",
            body="Restart MCBE GDK Installer to finish using the new version.",
        )
        dialog.add_response("later", "Later")
        dialog.add_response("restart", "Restart now")
        dialog.set_default_response("restart")
        dialog.set_close_response("later")
        dialog.set_response_appearance(
            "restart", Adw.ResponseAppearance.SUGGESTED
        )
        dialog.connect("response", self.restart_response)
        dialog.present(self)

    def restart_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response != "restart":
            return
        try:
            os.execv(
                sys.executable,
                [sys.executable, str(ROOT / "lib/gui.py")],
            )
        except OSError as exc:
            self.error("Could not restart the installer", str(exc))

    def open_url(self, url: str) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except GLib.Error as exc:
            self.error("Could not open the browser", str(exc))

    def write(self, text: str) -> None:
        buffer = self.log.get_buffer()
        buffer.insert(buffer.get_end_iter(), text)
        self.log.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 1)

    def choose(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Choose an authorized Minecraft package")
        file_filter = Gtk.FileFilter(name="Minecraft packages")
        for suffix in ("*.zip", "*.msixvc", "*.msixv"):
            file_filter.add_pattern(suffix)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)
        dialog.open(self, None, self.choose_done)

    def choose_done(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            selected = dialog.open_finish(result)
        except GLib.Error:
            return
        path = selected.get_path()
        if path:
            self.package = Path(path)
            self.package_row.set_title(self.package.name)
            self.package_row.set_subtitle(str(self.package.parent))
            self.refresh_install()

    def is_installed(self) -> bool:
        return (ROOT / "game" / "Minecraft.Windows.exe").is_file()

    def refresh_install(self) -> None:
        installed = self.is_installed()
        selected = bool(self.package)
        label, destructive = package_button_state(installed, selected)
        self.install_button.remove_css_class("suggested-action")
        self.install_button.remove_css_class("destructive-action")
        self.install_button.set_label(label)
        if destructive:
            self.install_button.add_css_class("destructive-action")
        else:
            self.install_button.add_css_class("suggested-action")
        self.install_button.set_sensitive(selected or installed)
        self.refresh_launch_state()
        if installed:
            self.install_row.set_title("Installed")
            self.install_row.set_subtitle("Worlds and account data are kept.")
            self.install_icon.set_from_icon_name("emblem-ok-symbolic")
            self.install_icon.add_css_class("success")
        else:
            self.install_row.set_title("Not installed")
            self.install_row.set_subtitle("")
            self.install_icon.set_from_icon_name("folder-download-symbolic")
            self.install_icon.remove_css_class("success")

    def package_action(self, button: Gtk.Button) -> None:
        if self.is_installed() and not self.package:
            self.confirm_uninstall()
        else:
            self.install(button)

    def confirm_uninstall(self) -> None:
        dialog = Adw.AlertDialog(
            heading="Uninstall Minecraft?",
            body="Game files will be removed.",
        )
        reset = Gtk.CheckButton(label="Remove user data")
        extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        extra.append(reset)
        detail = Gtk.Label(
            label="Worlds, settings, and Microsoft/Xbox session",
            xalign=0,
        )
        detail.add_css_class("dim-label")
        extra.append(detail)
        dialog.set_extra_child(extra)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("uninstall", "Uninstall")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance(
            "uninstall", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.connect("response", self.uninstall_response, reset)
        dialog.present(self)

    def uninstall_response(
        self,
        _dialog: Adw.AlertDialog,
        response: str,
        reset: Gtk.CheckButton,
    ) -> None:
        if response != "uninstall":
            return
        remove_user_data = reset.get_active()
        self.install_button.set_sensitive(False)
        self.install_row.set_title("Uninstalling…")

        def worker() -> None:
            try:
                with runtime_lock(ROOT):
                    remove_minecraft(ROOT, remove_user_data)
                self.events.put(("uninstall_done", remove_user_data))
            except Exception as exc:
                self.events.put(("error", f"Uninstall failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def install(self, _button: Gtk.Button) -> None:
        package = self.package
        installer = TOOL_ROOT / "easy-install.sh"
        if not package or not package.is_file():
            self.error(APP_NAME, "Choose a package first.")
            return
        if package.suffix.lower() not in {".zip", ".msixvc", ".msixv"}:
            self.error(APP_NAME, "Choose a ZIP, MSIXVC, or MSIXV package.")
            return
        if not installer.is_file():
            self.error(APP_NAME, "Run the installer UI from the source repository.")
            return
        updating = self.is_installed()
        self.was_updating = updating
        self.installing = True
        self.engine_downloading = False
        self.install_button.set_sensitive(False)
        self.install_row.set_title("Preparing update…" if updating else "Preparing installation…")
        self.install_row.set_subtitle("Reading the selected package.")
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self.write(f"\nInstalling {package.name}…\n")
        self.refresh_launch_state()
        GLib.timeout_add(120, self.pulse_progress)

        def worker() -> None:
            try:
                with runtime_lock(ROOT):
                    process = subprocess.Popen(
                        [str(installer), str(package.resolve())],
                        cwd=TOOL_ROOT,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )
                    assert process.stdout is not None
                    for line in process.stdout:
                        self.events.put(("log", line))
                    self.events.put(("install_done", process.wait()))
            except Exception as exc:
                self.events.put(("error", f"Installation failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def pulse_progress(self) -> bool:
        if self.installing and not self.engine_downloading:
            self.progress.pulse()
        return self.installing

    def refresh_account(self) -> None:
        signed_in = msa_signed_in()
        gamertag = msa_gamertag() if signed_in else None
        self.account_row.set_title(
            f"Connected as {gamertag}" if gamertag else
            "Microsoft account connected" if signed_in else "Not connected"
        )
        self.account_row.set_subtitle(
            "Xbox authentication is ready."
            if signed_in
            else "Optional. Connect for Xbox services and multiplayer."
        )
        self.account_icon.set_from_icon_name(
            "emblem-ok-symbolic" if signed_in else "avatar-default-symbolic"
        )
        self.login_button.set_visible(not signed_in)
        self.logout_button.set_visible(signed_in)

    def sign_in(self, _button: Gtk.Button) -> None:
        self.login_button.set_sensitive(False)

        def on_code(url: str, code: str) -> None:
            self.events.put(("code", url, code))

        def worker() -> None:
            try:
                result = login(on_code)
                self.events.put(("login_done", result))
            except Exception as exc:
                self.events.put(("error", f"Sign in failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def show_code(self, url: str, code: str) -> None:
        if self.signin_dialog:
            self.signin_dialog.close()
        dialog = Adw.Dialog(title="Microsoft sign-in", content_width=430)
        self.signin_dialog = dialog
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )
        heading = Gtk.Label(label="Connect your Microsoft account")
        heading.add_css_class("title-2")
        box.append(heading)
        instruction = Gtk.Label(
            label="Scan the QR code or open the page, then enter this code.",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        instruction.add_css_class("dim-label")
        box.append(instruction)

        if shutil.which("qrencode"):
            with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
                result = subprocess.run(
                    ["qrencode", "-o", image_file.name, "-s", "7", "-m", "2", url],
                    check=False,
                )
                if result.returncode == 0:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_file.name)
                    image = Gtk.Image.new_from_paintable(
                        Gdk.Texture.new_for_pixbuf(pixbuf)
                    )
                    image.set_pixel_size(220)
                    box.append(image)

        code_label = Gtk.Label(label=code, selectable=True)
        code_label.add_css_class("title-1")
        box.append(code_label)
        buttons = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.CENTER,
        )
        open_button = Gtk.Button(label="Open browser")
        open_button.add_css_class("suggested-action")
        open_button.connect("clicked", lambda _b: self.open_url(url))
        copy_button = Gtk.Button(label="Copy code")
        copy_button.connect(
            "clicked",
            lambda _b: (
                Gdk.Display.get_default().get_clipboard().set(code),
                self.toast("Sign-in code copied"),
            ),
        )
        buttons.append(open_button)
        buttons.append(copy_button)
        box.append(buttons)
        waiting = Gtk.Label(label="Waiting for Microsoft…")
        waiting.add_css_class("dim-label")
        box.append(waiting)
        dialog.set_child(box)
        dialog.present(self)

    def sign_out(self, _button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(
            heading="Sign out?",
            body="This removes the Microsoft/Xbox session from the isolated profile.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("signout", "Sign out")
        dialog.set_response_appearance("signout", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.sign_out_response)
        dialog.present(self)

    def sign_out_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response != "signout":
            return
        try:
            with runtime_lock(ROOT):
                logout()
            self.refresh_account()
            self.toast("Microsoft account disconnected")
        except Exception as exc:
            self.error("Sign out failed", str(exc))

    def launch_action(self, _button: Gtk.Button) -> None:
        if minecraft_launcher_pid(ROOT):
            self.stopping = True
            self.refresh_launch_state()

            def worker() -> None:
                try:
                    stop_minecraft(ROOT)
                except Exception as exc:
                    self.events.put(("error", f"Could not stop Minecraft: {exc}"))

            threading.Thread(target=worker, daemon=True).start()
            return

        launcher = shutil.which("mcbe-gdk-linux")
        if not launcher or not self.is_installed():
            self.error(APP_NAME, "Install the game first.")
            return
        self.set_launch_button("Starting…", True)
        self.launch_button.set_sensitive(False)
        self.launch_process = subprocess.Popen([launcher], start_new_session=True)

    def refresh_launch_state(self) -> bool:
        running = minecraft_launcher_pid(ROOT) is not None
        result = self.launch_process.poll() if self.launch_process else None
        if self.launch_process and result is not None:
            self.launch_process = None
            if result and not self.stopping and not running:
                self.error(
                    "Minecraft did not start",
                    f"Check {ROOT / 'profile/logs/desktop-launch.log'} for details.",
                )

        if not running:
            self.stopping = False
        busy = self.installing or self.updating
        label, sensitive, loading, destructive = launch_button_state(
            self.is_installed(),
            busy,
            running,
            self.launch_process is not None,
            self.stopping,
        )
        self.set_launch_button(label, loading)
        self.launch_button.remove_css_class("suggested-action")
        self.launch_button.remove_css_class("destructive-action")
        self.launch_button.add_css_class(
            "destructive-action" if destructive else "suggested-action"
        )
        self.launch_button.set_sensitive(sensitive)
        return GLib.SOURCE_CONTINUE

    def poll(self) -> bool:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    line = event[1]
                    self.write(line)
                    status = installation_status(line)
                    if status:
                        self.install_row.set_title(status[0])
                        self.install_row.set_subtitle(status[1])
                        self.engine_downloading = (
                            status[0] == "Downloading compatibility engine…"
                        )
                        self.progress.set_fraction(0)
                    elif self.engine_downloading:
                        percent = curl_progress_percent(line)
                        if percent is not None:
                            self.progress.set_fraction(percent / 100)
                            self.install_row.set_subtitle(
                                f"{percent}% of about 800 MB downloaded."
                            )
                elif kind == "code":
                    self.show_code(event[1], event[2])
                elif kind == "install_done":
                    self.installing = False
                    self.engine_downloading = False
                    self.progress.set_visible(False)
                    if event[1] == 0:
                        self.write("\nInstallation complete.\n")
                        self.package = None
                        self.package_row.set_title("Select a package")
                        self.package_row.set_subtitle("ZIP, MSIXVC, or MSIXV")
                        self.refresh_install()
                        self.toast(
                            "Minecraft updated successfully"
                            if self.was_updating
                            else "Minecraft installed successfully"
                        )
                    else:
                        self.install_row.set_title("Installation failed")
                        self.install_row.set_subtitle(
                            "Open Installation details for the error."
                        )
                        self.install_button.set_sensitive(True)
                        self.error("Installation failed", "Review the installation details.")
                elif kind == "uninstall_done":
                    self.refresh_install()
                    self.refresh_account()
                    self.toast(
                        "Minecraft and user data removed"
                        if event[1]
                        else "Minecraft uninstalled"
                    )
                elif kind == "login_done":
                    if self.signin_dialog:
                        self.signin_dialog.close()
                        self.signin_dialog = None
                    self.login_button.set_sensitive(True)
                    self.refresh_account()
                    if event[1]:
                        self.toast("Microsoft account connected")
                    else:
                        self.error("Sign in failed", "Microsoft sign-in did not complete.")
                elif kind == "updates_available":
                    self.show_updates(event[1])
                elif kind == "update_progress":
                    self.show_update_progress(event[1], event[2], event[3])
                elif kind == "updates_done":
                    self.updating = False
                    self.update_pulsing = False
                    self.update_spinner.stop()
                    self.update_spinner.set_visible(False)
                    self.update_progress.set_visible(False)
                    self.available_updates = None
                    self.update_group.set_visible(False)
                    self.refresh_install()
                    self.refresh_account()
                    if event[1]:
                        self.prompt_restart()
                    else:
                        self.toast("Compatibility engine updated")
                elif kind == "update_error":
                    self.updating = False
                    self.update_pulsing = False
                    self.update_spinner.stop()
                    self.update_spinner.set_visible(False)
                    self.update_progress.set_visible(False)
                    self.update_row.set_title("Update failed")
                    self.update_row.set_subtitle(
                        "Open Update details for the error, then try again."
                    )
                    self.update_button.set_label("Try again")
                    self.update_button.set_visible(True)
                    self.update_details.set_visible(True)
                    self.write_update_detail(f"\nError: {event[1]}\n")
                    self.install_button.set_sensitive(True)
                    self.login_button.set_sensitive(not msa_signed_in())
                    self.logout_button.set_sensitive(msa_signed_in())
                    self.refresh_launch_state()
                    self.error("Update failed", event[1])
                elif kind == "error":
                    self.installing = False
                    self.engine_downloading = False
                    self.stopping = False
                    self.progress.set_visible(False)
                    if self.signin_dialog:
                        self.signin_dialog.close()
                        self.signin_dialog = None
                    self.login_button.set_sensitive(True)
                    self.refresh_install()
                    self.refresh_account()
                    self.error(APP_NAME, event[1])
        except queue.Empty:
            pass
        return GLib.SOURCE_CONTINUE


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window or Window(self)
        window.present()


def main() -> None:
    configure_color_scheme()
    try:
        status = Application().run(sys.argv)
    except KeyboardInterrupt:
        status = 130
    raise SystemExit(status)


if __name__ == "__main__":
    assert package_button_state(False, False) == ("Install", False)
    assert package_button_state(False, True) == ("Install", False)
    assert package_button_state(True, False) == ("Uninstall", True)
    assert package_button_state(True, True) == ("Update", False)
    assert launch_button_state(True, True, False, False, False) == (
        "Launch", False, False, False
    )
    assert launch_button_state(True, False, True, False, False) == (
        "Stop", True, False, True
    )
    assert installation_status("Downloading the MCBE GDK compatibility engine...") == (
        "Downloading compatibility engine…",
        "0% of about 800 MB downloaded.",
    )
    assert curl_progress_percent(" 88 798.7M 88 706.0M 0 0 34.62M") == 88
    assert curl_progress_percent("  % Total  % Received") is None
    assert update_progress_status("engine_download", 419_430_400, 838_860_800) == (
        "Downloading compatibility engine…",
        "50% · 400 MB of 800 MB downloaded.",
        0.5,
    )
    main()
