#!/usr/bin/env python3
"""Modern GTK4 desktop UI for installation, authentication, and launching."""

from __future__ import annotations

import fcntl
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
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
from runtime import login, logout  # noqa: E402

APP_ID = "io.github.veedydev.MCBEGDKInstaller"
APP_NAME = "MCBE GDK Installer"


def package_button_state(installed: bool, selected: bool) -> tuple[str, bool]:
    if selected:
        return ("Update" if installed else "Install", False)
    return ("Uninstall", True) if installed else ("Install", False)


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


@contextmanager
def runtime_lock():
    path = ROOT / "profile" / ".desktop-launch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Minecraft or another setup action is running.") from exc
        yield


class Window(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(application=application, title=APP_NAME)
        self.set_default_size(780, 700)
        self.set_size_request(560, 560)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.package: Path | None = None
        self.signin_dialog: Adw.Dialog | None = None
        self.installing = False
        self.was_updating = False
        self.launch_process: subprocess.Popen | None = None

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
        launch_row = Adw.ActionRow(title="Minecraft")
        launch_row.add_prefix(
            Gtk.Image(icon_name="applications-games-symbolic", valign=Gtk.Align.CENTER)
        )
        self.launch_button = Gtk.Button(
            label="Launch", valign=Gtk.Align.CENTER
        )
        self.launch_button.add_css_class("suggested-action")
        self.launch_button.connect("clicked", self.launch)
        launch_row.add_suffix(self.launch_button)
        launch_group.add(launch_row)

        self.refresh_install()
        self.refresh_account()
        GLib.timeout_add(100, self.poll)

    def toast(self, message: str) -> None:
        self.overlay.add_toast(Adw.Toast.new(message))

    def error(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("close", "Close")
        dialog.present(self)

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
        self.launch_button.set_sensitive(installed)
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
            body="Game files will be removed. Worlds and account data will be kept.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("uninstall", "Uninstall")
        dialog.set_response_appearance(
            "uninstall", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.connect("response", self.uninstall_response)
        dialog.present(self)

    def uninstall_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response != "uninstall":
            return
        self.install_button.set_sensitive(False)
        self.install_row.set_title("Uninstalling…")

        def worker() -> None:
            try:
                with runtime_lock():
                    shutil.rmtree(ROOT / "game")
                self.events.put(("uninstall_done",))
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
        self.install_button.set_sensitive(False)
        self.install_row.set_title("Updating build…" if updating else "Installing build…")
        self.install_row.set_subtitle("Keep this window open. Large packages can take a while.")
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self.write(f"\nInstalling {package.name}…\n")
        GLib.timeout_add(120, self.pulse_progress)

        def worker() -> None:
            try:
                with runtime_lock():
                    process = subprocess.Popen(
                        [str(installer), str(package.resolve())],
                        cwd=TOOL_ROOT,
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
        if self.installing:
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
            else "Connect the account authorized for this build."
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
                with runtime_lock():
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
            with runtime_lock():
                logout()
            self.refresh_account()
            self.toast("Microsoft account disconnected")
        except Exception as exc:
            self.error("Sign out failed", str(exc))

    def launch(self, _button: Gtk.Button) -> None:
        launcher = shutil.which("mcbe-gdk-linux")
        if not launcher or not self.is_installed():
            self.error(APP_NAME, "Install the game first.")
            return
        self.launch_button.set_label("Starting…")
        self.launch_button.set_sensitive(False)
        self.launch_process = subprocess.Popen([launcher], start_new_session=True)
        GLib.timeout_add(500, self.poll_launch)

    def poll_launch(self) -> bool:
        if not self.launch_process:
            return GLib.SOURCE_REMOVE
        result = self.launch_process.poll()
        if result is None:
            self.launch_button.set_label("Running")
            return GLib.SOURCE_CONTINUE
        self.launch_process = None
        self.launch_button.set_label("Launch")
        self.launch_button.set_sensitive(self.is_installed())
        if result:
            self.error(
                "Minecraft did not start",
                f"Check {ROOT / 'profile/logs/desktop-launch.log'} for details.",
            )
        return GLib.SOURCE_REMOVE

    def poll(self) -> bool:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self.write(event[1])
                elif kind == "code":
                    self.show_code(event[1], event[2])
                elif kind == "install_done":
                    self.installing = False
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
                    self.toast("Minecraft uninstalled")
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
                elif kind == "error":
                    self.installing = False
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
    raise SystemExit(Application().run(sys.argv))


if __name__ == "__main__":
    assert package_button_state(False, False) == ("Install", False)
    assert package_button_state(False, True) == ("Install", False)
    assert package_button_state(True, False) == ("Uninstall", True)
    assert package_button_state(True, True) == ("Update", False)
    main()
