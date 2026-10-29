# SPDX-License-Identifier: GPL-2.0-or-later
"""Both games' patches for GRport's runtime, by Junmin Lee: Gravity Rush 2's frame rate patches
and crash fix, and the optional ones the SETUP page offers (motion blur off, fixes, skip intro,
cheats and unlocks), compiled into the runtime's BBPATCH2 file.

GRport does not ship the patches: the first PLAY that needs them downloads the game's patch
file from its author's repository (REPO) into the GRport folder's patches/ and uses it from
there. They are GoldHEN-style byte writes at the game's image offset + 0x400000. The same
compiled file goes to the prepare step (its writes keep their bytes) and to the runtime
(--patches).
"""
import struct
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .games import GameFolder
from .paths import AppPaths
from .settings import FPS_CHOICES, LauncherSettings

REPO = "https://raw.githubusercontent.com/junminlee2004/GR2fork_GoldHEN_Patch_Repository/main/patches/xml/"
FILES = {"gr1": "GravityRushRemastered-Orbis.xml", "gr2": "GravityDaze2-Orbis.xml"}
APP_VERSIONS = {"gr1": "01.00", "gr2": "01.11"}
PATCH_URL = REPO + FILES["gr2"]
CRASH_FIX = "30 fps Crash fix"  # name prefixes: the author's versions change
# Gravity Rush Remastered above 60 FPS: the camera rolls past level after a gravity kick.
GR1_KICK_FIX = "Gravity kick camera leveling"
GOLDHEN_BASE = 0x400000

# The optional patches: (name prefix in the author's file, label, on by default, note).
OPTIONAL = {
    "gr1": (
        ("Skip intro", "Skip intro", False, "Skips the logos and the intro movie at boot."),
    ),
    "gr2": (
        ("Disable motion blur", "Motion blur off", True, "Removes the camera motion blur."),
        ("SSAO ghost trail fix", "Ambient occlusion trail fix", True,
         "Moving characters no longer leave dark copies of themselves in the shading."),
        ("Auto-exposure fix", "Auto-exposure fix", True,
         "Auto-exposure measures the whole frame (the picture was washed out at low resolutions)."),
        ("Skip Intro", "Skip intro", False, "Skips the logos and the intro movie at boot."),
        ("Swap Confirm/Cancel", "Cross confirms", False,
         "Western button layout: Cross confirms, Circle cancels."),
        ("Invincible Player", "Cheat: invincible", False, ""),
        ("Infinite Gravity Energy", "Cheat: infinite gravity", False, ""),
        ("Infinite Special Attck", "Cheat: infinite special attack", False, ""),
        ("Infinite Precious Gems", "Cheat: infinite precious gems", False, ""),
        ("Raise Stasis Field Limit", "Stasis field holds 15 objects", False, ""),
        ("Unlock All Costumes", "Unlock all costumes", False, ""),
        ("Unlock All Gestures", "Unlock all gestures", False, ""),
        ("Unlock All Photo Items", "Unlock all photo items", False, ""),
        ("Unlock all Dusty Token", "Unlock all Dusty Token rewards", False, ""),
        ("Unlock All DLC", "Unlock all DLC", False, ""),
        ("Remove DLC Requirement", "Load saves made with DLC", False,
         "Loads save data that needs DLC you do not have."),
    ),
}


def default_extras(key: str) -> list:
    return [prefix for prefix, _, on, _ in OPTIONAL.get(key, ()) if on]


def extras(s: LauncherSettings, key: str) -> list:
    """The optional patches chosen for a game (the defaults until SETUP changes them)."""
    chosen = s.games[key].extras
    return default_extras(key) if chosen is None else list(chosen)


def source(paths: AppPaths, key: str = "gr2") -> Path:
    return paths.root / "patches" / FILES[key]


def download(paths: AppPaths, key: str = "gr2") -> Path:
    """The author's patch file for a game, downloaded once."""
    path = source(paths, key)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(REPO + FILES[key], timeout=30) as r:
            data = r.read()
        try:
            ET.fromstring(data)  # a patch file, not an error page
        except ET.ParseError:
            raise ValueError("the download is not a patch file") from None
        path.write_bytes(data)
    return path


def wanted(fps: int, key: str = "gr2", extras=()) -> list:
    """Name prefixes of the patches for a game, frame rate and optional choices. Gravity Rush 2:
    the crash fix always, the FPS patch above 30. Gravity Rush Remastered: the gravity kick fix
    above 60."""
    known = [prefix for prefix, _, _, _ in OPTIONAL.get(key, ())]
    out = []
    if key == "gr2":
        if fps in FPS_CHOICES["gr2"] and fps != 30:
            out.append(f"{fps}fps v")
        out.append(CRASH_FIX)
    elif key == "gr1" and fps > 60:
        out.append(GR1_KICK_FIX)
    return out + [prefix for prefix in known if prefix in extras]


def compile_patches(xml: Path, prefixes: list, app_version: str = APP_VERSIONS["gr2"]) -> bytes:
    root = ET.parse(xml).getroot()
    writes = []
    for prefix in prefixes:
        metas = [m for m in root.iter("Metadata") if (m.get("Name") or "").startswith(prefix)
                 and m.get("AppVer") == app_version]
        if not metas:
            raise ValueError(f"the patch file has no '{prefix}' patch for version {app_version}")
        for line in metas[-1].iter("Line"):  # the newest of its versions
            if line.get("Type") != "bytes":
                raise ValueError(f"unsupported patch line type {line.get('Type')}")
            writes.append((int(line.get("Address"), 16) - GOLDHEN_BASE,
                           bytes.fromhex(line.get("Value"))))
    blob = struct.pack("<8sQQ", b"BBPATCH2", GOLDHEN_BASE, len(writes))
    for offset, data in writes:
        blob += struct.pack("<QQ", offset, len(data)) + data
    return blob


def patch_file(paths: AppPaths, key: str) -> Path:
    return paths.root / "user" / key / "patches.bin"


def _mismatch_file(paths: AppPaths, key: str) -> Path:
    return paths.root / "user" / key / "patches-mismatch.txt"


def _eboot_stamp(info: GameFolder) -> str:
    st = info.eboot.stat()
    return f"{info.eboot} {st.st_size} {st.st_mtime_ns}"


def mark_mismatch(paths: AppPaths, info: GameFolder) -> None:
    """The prepare step found the patches made for another build of this game: it runs
    unpatched (30 FPS) until its eboot changes."""
    path = _mismatch_file(paths, info.game.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_eboot_stamp(info), encoding="utf-8")
    patch_file(paths, info.game.key).unlink(missing_ok=True)


def mismatched(paths: AppPaths, info: GameFolder) -> bool:
    try:
        return _mismatch_file(paths, info.game.key).read_text(encoding="utf-8") == _eboot_stamp(info)
    except OSError:
        return False


def write(paths: AppPaths, s: LauncherSettings, info: GameFolder) -> "Path | None":
    """Writes user/<game>/patches.bin for the chosen frame rate and optional patches and returns
    it; None (and no file) when the game needs none, is another version, or its patches did not
    fit this build. Gravity Rush 2 at 30 FPS without the patch file (no download yet, no
    connection) runs unpatched."""
    key = info.game.key
    path = patch_file(paths, key)
    g = s.games[key]
    names = wanted(g.fps, key, extras(s, key))
    if (key not in FILES or info.version != APP_VERSIONS[key] or mismatched(paths, info)
            or not names):
        path.unlink(missing_ok=True)
        return None
    if names == [CRASH_FIX] and not source(paths, key).is_file():
        try:
            download(paths, key)
        except OSError:
            path.unlink(missing_ok=True)
            return None
    blob = compile_patches(download(paths, key), names, APP_VERSIONS[key])
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != blob:
        path.write_bytes(blob)
    return path
