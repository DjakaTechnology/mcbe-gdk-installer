#!/usr/bin/env python3
"""Small desktop UI for setup, account authentication, and launching."""

from __future__ import annotations

import fcntl
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from contextlib import contextmanager
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:
    raise SystemExit(
        "Tk is required (Arch: sudo pacman -S tk; Debian: sudo apt install python3-tk)."
    ) from exc

ROOT = Path(os.environ["MCBE_GDK_ROOT"]).expanduser().resolve()
TOOL_ROOT = Path(os.environ.get("MCBE_GDK_TOOL_ROOT") or ".").expanduser().resolve()
for path in (ROOT / "lib", TOOL_ROOT):
    sys.path.insert(0, str(path))

from auth.auth import msa_gamertag, msa_signed_in  # noqa: E402
from runtime import login, logout  # noqa: E402


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


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue[tuple] = queue.Queue()
        self.qr_image = None
        self.package = tk.StringVar()
        self.account = tk.StringVar()

        root.title("MCBE GDK Linux")
        root.minsize(760, 620)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        header = ttk.Frame(root, padding=(20, 18, 20, 8))
        header.grid(sticky="ew")
        ttk.Label(
            header, text="MCBE GDK Linux", font=("", 20, "bold")
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="Install an authorized build, connect Xbox, and launch.",
        ).pack(anchor="w", pady=(4, 0))

        install = ttk.LabelFrame(root, text="Install", padding=14)
        install.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        install.columnconfigure(0, weight=1)
        ttk.Entry(install, textvariable=self.package).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(install, text="Choose package…", command=self.choose).grid(
            row=0, column=1, padx=(0, 8)
        )
        self.install_button = ttk.Button(
            install, text="Install", command=self.install
        )
        self.install_button.grid(row=0, column=2)
        ttk.Label(
            install,
            text="Accepts .zip, .msixvc, or .msixv. WinBoat and Microsoft GDK are required.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        body = ttk.Frame(root, padding=(20, 0, 20, 10))
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.log = tk.Text(body, height=14, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        account = ttk.LabelFrame(root, text="Microsoft / Xbox account", padding=14)
        account.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")
        account.columnconfigure(0, weight=1)
        ttk.Label(account, textvariable=self.account).grid(
            row=0, column=0, sticky="w"
        )
        self.login_button = ttk.Button(
            account, text="Sign in", command=self.sign_in
        )
        self.login_button.grid(row=0, column=1, padx=6)
        self.logout_button = ttk.Button(
            account, text="Sign out", command=self.sign_out
        )
        self.logout_button.grid(row=0, column=2)

        footer = ttk.Frame(root, padding=(20, 0, 20, 18))
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Launch Minecraft", command=self.launch).grid(
            row=0, column=1
        )

        self.refresh_account()
        self.root.after(100, self.poll)

    def write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose an authorized Minecraft package",
            filetypes=[
                ("Minecraft packages", "*.zip *.msixvc *.msixv"),
                ("All files", "*"),
            ],
        )
        if selected:
            self.package.set(selected)

    def install(self) -> None:
        package = Path(self.package.get()).expanduser()
        installer = TOOL_ROOT / "easy-install.sh"
        if not package.is_file():
            messagebox.showerror("MCBE GDK Linux", "Choose a package first.")
            return
        if package.suffix.lower() not in {".zip", ".msixvc", ".msixv"}:
            messagebox.showerror(
                "MCBE GDK Linux", "Choose a .zip, .msixvc, or .msixv package."
            )
            return
        if not installer.is_file():
            messagebox.showerror(
                "MCBE GDK Linux",
                "The source checkout is unavailable. Run the GUI from the repository.",
            )
            return
        self.install_button.configure(state="disabled")
        self.write(f"\nInstalling {package.name}…\n")

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

    def refresh_account(self) -> None:
        signed_in = msa_signed_in()
        gamertag = msa_gamertag() if signed_in else None
        self.account.set(
            f"Signed in: {gamertag or 'Microsoft account'}"
            if signed_in
            else "Not signed in"
        )
        self.login_button.configure(state="disabled" if signed_in else "normal")
        self.logout_button.configure(state="normal" if signed_in else "disabled")

    def sign_in(self) -> None:
        self.login_button.configure(state="disabled")

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
        dialog = tk.Toplevel(self.root)
        dialog.title("Microsoft sign-in")
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text="Sign in to Microsoft", font=("", 16, "bold")
        ).pack()
        ttk.Label(
            frame, text="Scan to open the page, then enter this code:"
        ).pack(pady=(6, 10))

        qrencode = shutil.which("qrencode")
        if qrencode:
            with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
                result = subprocess.run(
                    [qrencode, "-o", image_file.name, "-s", "6", "-m", "2", url],
                    check=False,
                )
                if result.returncode == 0:
                    try:
                        self.qr_image = tk.PhotoImage(file=image_file.name)
                        ttk.Label(frame, image=self.qr_image).pack()
                    except tk.TclError:
                        pass

        ttk.Label(frame, text=code, font=("monospace", 22, "bold")).pack(pady=12)
        entry = ttk.Entry(frame, width=48)
        entry.insert(0, url)
        entry.configure(state="readonly")
        entry.pack(fill="x")

        buttons = ttk.Frame(frame)
        buttons.pack(pady=(12, 0))
        ttk.Button(
            buttons, text="Open browser", command=lambda: webbrowser.open(url)
        ).pack(side="left", padx=4)
        ttk.Button(
            buttons,
            text="Copy code",
            command=lambda: (
                self.root.clipboard_clear(),
                self.root.clipboard_append(code),
            ),
        ).pack(side="left", padx=4)
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(
            side="left", padx=4
        )

    def sign_out(self) -> None:
        if not messagebox.askyesno(
            "MCBE GDK Linux", "Remove the isolated Microsoft/Xbox session?"
        ):
            return
        try:
            with runtime_lock():
                logout()
            self.refresh_account()
        except Exception as exc:
            messagebox.showerror("Sign out failed", str(exc))

    def launch(self) -> None:
        launcher = shutil.which("mcbe-gdk-linux")
        if not launcher:
            messagebox.showerror("MCBE GDK Linux", "Install the game first.")
            return
        subprocess.Popen([launcher], start_new_session=True)

    def poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self.write(event[1])
                elif kind == "code":
                    self.show_code(event[1], event[2])
                elif kind == "install_done":
                    self.install_button.configure(state="normal")
                    if event[1] == 0:
                        self.write("\nInstallation complete.\n")
                        self.refresh_account()
                    else:
                        messagebox.showerror(
                            "Installation failed", "Review the installation log."
                        )
                elif kind == "login_done":
                    self.refresh_account()
                    if not event[1]:
                        messagebox.showerror(
                            "Sign in failed", "Microsoft sign-in did not complete."
                        )
                elif kind == "error":
                    self.install_button.configure(state="normal")
                    self.refresh_account()
                    messagebox.showerror("MCBE GDK Linux", event[1])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
