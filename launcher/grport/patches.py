# SPDX-License-Identifier: GPL-2.0-or-later
"""Gravity Rush 2's patches for GRport's runtime: Junmin Lee's frame rate patches and crash
fix, compiled into the runtime's BBPATCH2 file.

GRport does not ship the patches: the first PLAY that needs them downloads the patch file from
its author's repository (PATCH_URL) into the GRport folder's patches/ and uses it from there.
They are GoldHEN-style byte writes at the game's image offset + 0x400000. The same compiled
file goes to the prepare step (its writes keep their bytes) and to the runtime (--patches).
"""
import struct
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .games import GameFolder
from .paths import AppPaths
from .settings import LauncherSettings

PATCH_URL = ("https://raw.githubusercontent.com/junminlee2004/GR2fork_GoldHEN_Patch_Repository/"
             "main/patches/xml/GravityDaze2-Orbis.xml")
FPS_CHOICES = (30, 60, 90, 120)
CRASH_FIX = "30 fps Crash fix"  # name prefixes: the author's versions change
APP_VERSION = "01.11"
GOLDHEN_BASE = 0x400000


def source(paths: AppPaths) -> Path:
    return paths.root / "patches" / "GravityDaze2-Orbis.xml"


def download(paths: AppPaths) -> Path:
    """The author's patch file, downloaded once."""
    path = source(paths)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(PATCH_URL, timeout=30) as r:
            data = r.read()
        try:
            ET.fromstring(data)  # a patch file, not an error page
        except ET.ParseError:
            raise ValueError("the download is not a patch file") from None
        path.write_bytes(data)
    return path


def wanted(fps: int) -> list:
    """Name prefixes of the patches for a frame rate: the crash fix always, the FPS patch above
    30."""
    out = [CRASH_FIX]
    if fps in FPS_CHOICES and fps != 30:
        out.insert(0, f"{fps}fps v")
    return out


def compile_patches(xml: Path, prefixes: list) -> bytes:
    root = ET.parse(xml).getroot()
    writes = []
    for prefix in prefixes:
        metas = [m for m in root.iter("Metadata") if (m.get("Name") or "").startswith(prefix)
                 and m.get("AppVer") == APP_VERSION]
        if not metas:
            raise ValueError(f"the patch file has no '{prefix}' patch for version {APP_VERSION}")
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
    """Gravity Rush 2 (version 01.11): writes user/gr2/patches.bin for the chosen frame rate
    and returns it; None for other games and versions. At 30 FPS without the patch file (no
    download yet, no connection) the game runs unpatched."""
    if info.game.key != "gr2" or info.version != APP_VERSION or mismatched(paths, info):
        return None
    fps = s.games[info.game.key].fps
    if fps == 30 and not source(paths).is_file():
        try:
            download(paths)
        except OSError:
            return None
    xml = download(paths)
    blob = compile_patches(xml, wanted(fps))
    path = patch_file(paths, info.game.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != blob:
        path.write_bytes(blob)
    return path
