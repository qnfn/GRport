# SPDX-License-Identifier: GPL-2.0-or-later
"""Shortcuts to the launcher: on the Desktop and in the Start menu (Windows .lnk), or on the
desktop and in the applications menu (Linux .desktop, pointing at the AppImage)."""
import ctypes
import os
import subprocess
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

from .paths import AppPaths

FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
FOLDERID_PROGRAMS = "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}"  # the user's Start menu programs
NAME = "GRport.lnk"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# WScript.Shell writes the .lnk; the paths come in through the environment (no quoting).
_LNK_PS = (
    "$ErrorActionPreference = 'Stop'; "
    "$s = New-Object -ComObject WScript.Shell; "
    "$l = $s.CreateShortcut($env:GRPORT_LNK); "
    "$l.TargetPath = $env:GRPORT_TARGET; "
    "$l.WorkingDirectory = $env:GRPORT_WORKDIR; "
    "$l.IconLocation = $env:GRPORT_ICON; "
    "$l.Description = 'Gravity Rush Remastered and Gravity Rush 2'; "
    "$l.Save()"
)


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _known_folder(folder_id: str) -> Path:
    """SHGetKnownFolderPath: where Windows really keeps a folder (OneDrive may move it)."""
    shell32, ole32 = ctypes.WinDLL("shell32"), ctypes.WinDLL("ole32")
    get = shell32.SHGetKnownFolderPath
    get.argtypes = [ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
                    ctypes.POINTER(ctypes.c_void_p)]
    get.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    guid = _GUID.from_buffer_copy(uuid.UUID(folder_id).bytes_le)
    buf = ctypes.c_void_p()
    try:
        if get(ctypes.byref(guid), 0, None, ctypes.byref(buf)) != 0:
            raise OSError("SHGetKnownFolderPath failed")
        return Path(ctypes.wstring_at(buf.value))
    finally:
        ole32.CoTaskMemFree(buf)


def desktop_dir() -> Path:
    if os.name != "nt":
        try:
            found = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True,
                                   timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            found = ""
        return Path(found) if found else Path.home() / "Desktop"
    try:
        return _known_folder(FOLDERID_DESKTOP)
    except (AttributeError, OSError):
        return Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop"


def start_menu_dir() -> Path:
    if os.name != "nt":
        data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(data) / "applications"
    try:
        return _known_folder(FOLDERID_PROGRAMS)
    except (AttributeError, OSError):
        return (Path(os.environ.get("APPDATA") or Path.home()) /
                "Microsoft" / "Windows" / "Start Menu" / "Programs")


def target(paths: AppPaths) -> Path:
    """GRport.exe in the GRport folder (also when the launcher runs from its sources)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return paths.root / "GRport.exe"


def _create_desktop_entry(paths: AppPaths, folder: Path) -> Path:
    """Linux: folder/GRport.desktop starting the AppImage (its icon copied next to the data)."""
    appimage = os.environ.get("APPIMAGE")
    if not appimage:
        raise OSError("shortcuts need GRport's AppImage (this is a source run)")
    icon = paths.root / "grport.png"
    try:
        from .ui.theme import assets_dir
        icon.write_bytes((assets_dir() / "grport.png").read_bytes())
    except OSError:
        icon = Path("grport.png")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    entry = folder / "GRport.desktop"
    entry.write_text("[Desktop Entry]\nType=Application\nName=GRport\n"
                     "Comment=Gravity Rush Remastered and Gravity Rush 2\n"
                     f'Exec="{appimage}"\nIcon={icon}\nTerminal=false\nCategories=Game;\n',
                     encoding="utf-8")
    entry.chmod(0o755)
    return entry


def create(paths: AppPaths, folder: Path) -> Path:
    """Writes folder/GRport.lnk to the launcher, replacing an older one."""
    if os.name != "nt":
        return _create_desktop_entry(paths, folder)
    exe = target(paths)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lnk = folder / NAME
    lnk.unlink(missing_ok=True)
    env = dict(os.environ, GRPORT_LNK=str(lnk), GRPORT_TARGET=str(exe),
               GRPORT_WORKDIR=str(exe.parent), GRPORT_ICON=f"{exe},0")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-Command", _LNK_PS], env=env, capture_output=True, text=True,
                       creationflags=_NO_WINDOW)
    if r.returncode != 0 or not lnk.exists():
        raise OSError(r.stderr.strip() or "Could not create the shortcut")
    return lnk
