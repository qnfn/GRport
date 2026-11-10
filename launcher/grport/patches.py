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
import hashlib
import re
import struct
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from . import respatch
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
DLC_UNLOCK = "Unlock All DLC"  # Gravity Rush 2: always on
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


def wanted(fps: int, key: str = "gr2", extras=(), resolution: str = "") -> list:
    """Name prefixes of the patches for a game, frame rate and optional choices. Gravity Rush 2:
    the crash fix and Unlock All DLC always, the FPS patch above 30. Gravity Rush Remastered:
    the gravity kick fix above 60."""
    known = [prefix for prefix, _, _, _ in OPTIONAL.get(key, ())]
    out = []
    if key == "gr2":
        if fps in FPS_CHOICES["gr2"] and fps != 30:
            out.append(f"{fps}fps v")
        out += [CRASH_FIX, DLC_UNLOCK]
    elif key == "gr1" and fps > 60:
        out.append(GR1_KICK_FIX)
    out += [prefix for prefix in known if prefix in extras]
    return out + ([resolution] if resolution else [])


_INTS = {"bytes16": "<H", "bytes32": "<I", "bytes64": "<Q"}
_FLOATS = {"float32": "<f", "float64": "<d"}


def _line_bytes(kind: "str | None", value: str) -> bytes:
    """The bytes a GoldHEN patch line writes, as shadPS4 and GoldHEN read its Type: hex for
    bytes, little-endian numbers for bytesNN/floatNN, a NUL-terminated string for utf8."""
    if kind == "bytes":
        return bytes.fromhex(value)
    if kind in _INTS:
        return struct.pack(_INTS[kind], int(value, 0))
    if kind in _FLOATS:
        return struct.pack(_FLOATS[kind], float(value))
    if kind == "utf8":
        return value.encode("utf-8") + b"\0"
    raise ValueError(f"unsupported patch line type {kind}")


def compile_patches(xml: Path, prefixes: list, app_version: str = APP_VERSIONS["gr2"]) -> bytes:
    root = ET.parse(xml).getroot()
    writes = []
    for prefix in prefixes:
        size = respatch.parse(prefix)
        if size is not None:  # a size made from the author's 16:10 patches
            writes += [(addr - GOLDHEN_BASE, data)
                       for addr, data in respatch.generate(root, app_version, *size)]
            continue
        metas = [m for m in root.iter("Metadata") if (m.get("Name") or "").startswith(prefix)
                 and m.get("AppVer") == app_version]
        if not metas:
            raise ValueError(f"the patch file has no '{prefix}' patch for version {app_version}")
        for line in metas[-1].iter("Line"):  # the newest of its versions
            writes.append((int(line.get("Address"), 16) - GOLDHEN_BASE,
                           _line_bytes(line.get("Type"), line.get("Value"))))
    blob = struct.pack("<8sQQ", b"BBPATCH2", GOLDHEN_BASE, len(writes))
    for offset, data in writes:
        blob += struct.pack("<QQ", offset, len(data)) + data
    return blob


def extra_dmem_mb(xml: Path, prefix: str, app_version: str) -> int:
    """The extra direct memory (MiB) a patch's notes ask for ("Needs Additional DMem Allocation
    N"): the bigger resolutions' render targets do not fit the PS4's 5056 MiB."""
    if not prefix:
        return 0
    size = respatch.parse(prefix)
    if size is not None:
        prefix = respatch.big_dmem_patch(size[0], size[1]) or ""
        if not prefix:
            return 0
    try:
        root = ET.parse(xml).getroot()
    except (OSError, ET.ParseError):
        return 0
    metas = [m for m in root.iter("Metadata") if (m.get("Name") or "").startswith(prefix)
             and m.get("AppVer") == app_version]
    found = re.search(r"DMem Allocation (\d+)", metas[-1].get("Note") or "") if metas else None
    return int(found.group(1)) if found else 0


def patch_file(paths: AppPaths, key: str) -> Path:
    return paths.root / "user" / key / "patches.bin"


def _mismatch_file(paths: AppPaths, key: str) -> Path:
    return paths.root / "user" / key / "patches-mismatch.txt"


def _stamp(info: GameFolder, blob: bytes) -> str:
    st = info.eboot.stat()
    return f"{info.eboot} {st.st_size} {st.st_mtime_ns} {hashlib.sha1(blob).hexdigest()}"


def mark_mismatch(paths: AppPaths, info: GameFolder) -> None:
    """The prepare step found the patches made for another build of this game: it runs
    unpatched (30 FPS) until its eboot or the chosen patches change."""
    path = _mismatch_file(paths, info.game.key)
    patch = patch_file(paths, info.game.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_stamp(info, patch.read_bytes() if patch.is_file() else b""), encoding="utf-8")
    patch.unlink(missing_ok=True)


def mismatched(paths: AppPaths, info: GameFolder, blob: bytes) -> bool:
    try:
        return _mismatch_file(paths, info.game.key).read_text(encoding="utf-8") == _stamp(info, blob)
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
    names = wanted(g.fps, key, extras(s, key), g.resolution)
    if key not in FILES or info.version != APP_VERSIONS[key] or not names:
        path.unlink(missing_ok=True)
        return None
    if names == [CRASH_FIX] and not source(paths, key).is_file():
        try:
            download(paths, key)
        except OSError:
            path.unlink(missing_ok=True)
            return None
    blob = compile_patches(download(paths, key), names, APP_VERSIONS[key])
    if mismatched(paths, info, blob):
        path.unlink(missing_ok=True)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != blob:
        path.write_bytes(blob)
    return path
