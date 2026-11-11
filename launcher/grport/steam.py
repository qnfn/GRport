# SPDX-License-Identifier: GPL-2.0-or-later
"""Per-game Steam shortcuts, with backups and atomic replacement of the current account's VDF."""
import os
import re
import subprocess
import tempfile
import zlib
from pathlib import Path

from . import steam_vdf
from .games import GAMES
from .shortcuts import target


def steam_folder() -> Path:
    candidates = []
    if os.environ.get("GRPORT_STEAM_DIR"):
        candidates.append(Path(os.environ["GRPORT_STEAM_DIR"]))
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                candidates.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
    else:
        candidates += [Path.home() / suffix for suffix in (
            ".steam/steam", ".local/share/Steam", ".var/app/com.valvesoftware.Steam/.local/share/Steam")]
    for folder in candidates:
        if (folder / "userdata").is_dir():
            return folder
    raise OSError("Steam installation not found.")


def current_config(folder: Path) -> Path:
    accounts = [p / "config" for p in (folder / "userdata").iterdir()
                if p.is_dir() and p.name.isdigit() and p.name != "0"]
    if len(accounts) == 1:
        return accounts[0]
    try:
        login = (folder / "config/loginusers.vdf").read_text(encoding="utf-8")
        for steam_id, fields in re.findall(r'"(\d{17})"\s*\{([^{}]*)\}', login):
            if re.search(r'"MostRecent"\s*"1"', fields, re.IGNORECASE):
                active = folder / "userdata" / str(int(steam_id) & 0xffffffff) / "config"
                if active in accounts:
                    return active
    except OSError:
        pass
    raise OSError("Sign in to Steam once so GRport can identify your account, then exit Steam.")


def is_running() -> bool:
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
                                capture_output=True, timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise OSError("Could not check whether Steam is running.")
        return b"steam.exe" in result.stdout.lower()
    proc = Path("/proc")
    for process in proc.iterdir():
        if process.name.isdigit():
            try:
                if (process / "comm").read_text().strip() == "steam":
                    return True
            except OSError:
                pass
    return False


def write_shortcut(path: Path, name: str, exe: str, options: str, icon: str = "") -> None:
    """Keep unrelated shortcuts, tags, playtime, and all unknown fields intact."""
    old_bytes = path.read_bytes() if path.exists() else b""
    root = steam_vdf.load(old_bytes) if old_bytes else {"shortcuts": {}}
    shortcuts = root.setdefault("shortcuts", {})
    if not isinstance(shortcuts, dict):
        raise ValueError("Steam shortcut list is invalid; the original file was kept.")
    quoted = f'"{exe}"'
    matching = next((key for key, value in shortcuts.items() if isinstance(value, dict)
                     and value.get("Exe") == quoted and value.get("LaunchOptions", "") == options), None)
    entry = shortcuts[matching] if matching is not None else {}
    entry.update({"appid": zlib.crc32((quoted + name).encode("utf-8")) | 0x80000000,
                  "AppName": name, "Exe": quoted, "StartDir": f'"{Path(exe).parent}"',
                  "icon": icon, "LaunchOptions": options})
    for key, value in {"ShortcutPath": "", "IsHidden": 0, "AllowDesktopConfig": 1,
                       "AllowOverlay": 1, "OpenVR": 0, "Devkit": 0, "DevkitGameID": "",
                       "DevkitOverrideAppID": 0, "LastPlayTime": 0, "FlatpakAppID": "",
                       "tags": {}}.items():
        entry.setdefault(key, value)
    if matching is None:
        index = 0
        while str(index) in shortcuts:
            index += 1
        shortcuts[str(index)] = entry
    output = steam_vdf.dump(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if old_bytes:
        path.with_suffix(path.suffix + ".bak").write_bytes(old_bytes)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="grport-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def add_game(paths, key: str) -> None:
    if key not in GAMES:
        raise ValueError("Unknown game")
    exe = Path(os.environ["APPIMAGE"]) if os.name != "nt" and os.environ.get("APPIMAGE") else target(paths)
    if not exe.is_file():
        raise OSError("Use the built GRport executable or AppImage to create Steam shortcuts.")
    if is_running():
        raise OSError("Exit Steam first. Steam overwrites shortcut changes while it is running.")
    config = current_config(steam_folder())
    write_shortcut(config / "shortcuts.vdf", GAMES[key].title, str(exe), f"--{key}")
