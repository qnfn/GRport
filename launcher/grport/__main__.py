# SPDX-License-Identifier: GPL-2.0-or-later
import sys


def _taskbar_identity() -> None:
    """Group the window under GRport's own taskbar icon (not python.exe's)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GRport.Launcher")
    except (AttributeError, OSError):
        pass


def main(argv: list) -> int:
    from grport.paths import AppPaths
    paths = AppPaths.current()
    _taskbar_identity()
    from grport.ui.app import App
    App(paths).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
