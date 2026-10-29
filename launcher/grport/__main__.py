# SPDX-License-Identifier: GPL-2.0-or-later
import sys


def _taskbar_identity() -> None:
    """Group the window under GRport's own taskbar icon (not python.exe's)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GRport.Launcher")
    except (AttributeError, OSError):
        pass


def _restart_if_borrowed() -> bool:
    """A built launcher started by another GRport.exe (GRport 0.1.2's self-update restart)
    inherits that one's unpacked files, which it deletes when it closes; they also carry its
    version stamp (assets/version.txt, written by build.sh). Start again with our own files.
    True when a fresh copy was started and this one should end."""
    import os
    import subprocess
    from pathlib import Path
    from grport import __version__
    unpacked = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or not unpacked or os.environ.get("GRPORT_FRESH") == "1":
        return False
    try:
        stamp = (Path(unpacked) / "assets" / "version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        stamp = ""
    if stamp == __version__:
        return False
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1", GRPORT_FRESH="1")
    subprocess.Popen([sys.executable] + sys.argv[1:], env=env, close_fds=True)
    return True


def main(argv: list) -> int:
    if _restart_if_borrowed():
        return 0
    from grport.paths import AppPaths
    paths = AppPaths.current()
    _taskbar_identity()
    from grport.ui.app import App
    App(paths).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
