# Use existing game files

You do not need to install from a package if you already have the Minecraft
game files.

Find the folder that contains `Minecraft.Windows.exe`, then run this command
from the installer source folder:

```bash
./install.sh "/path/to/Minecraft for Windows/Content"
```

If you know the game version, you can include it:

```bash
./install.sh "/path/to/Minecraft for Windows/Content" --version 1.26.32.2
```

The installer uses the files where they are instead of making another copy.
Back them up first because setup changes some game files. The first setup also
downloads the required runtime and may take a while.

After installation, sign in and launch:

```bash
mcbe-gdk-linux-login
mcbe-gdk-linux
```

Other account commands:

```bash
mcbe-gdk-linux-auth    # Check sign-in status
mcbe-gdk-linux-logout  # Remove the saved account
```

If your terminal reports that a command was not found, run it from
`~/.local/bin` instead.
