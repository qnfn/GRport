# SPDX-License-Identifier: GPL-2.0-or-later
"""Import saves from other PS4 emulators/launchers, decrypted PS4 exports and other GRport folders.

GRport's runtime keeps a save as (runtime_savedata.c):
    user/<game>/savedata/1/<serial>/<dir>/             the game's files
    user/<game>/savedata/1/<serial>/<dir>.sce_sys/     param.bin (OrbisSaveDataParam), icon0.png
    user/<game>/savedata/1/<serial>.memory/memory.dat  SaveDataMemory
shadPS4-based emulators and decrypted PS4 exports (Apollo Save Tool) keep <dir>/ with the game's
files plus <dir>/sce_sys/param.sfo; their SaveDataMemory is <serial>/sce_sdmemory/memory.dat.
A PS4's own USB backup (sdimg_* files) is encrypted with the console's keys and can't be read."""
import shutil
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from grport import games

PARAM_SIZE = 1328  # title[128] subtitle[128] detail[1024] user_param u32, pad, mtime i64, reserved[32]
MEMORY_DIR = "sce_sdmemory"
MAX_DEPTH = 8


@dataclass(frozen=True)
class FoundSave:
    name: str            # the save's directory name (data0000, system0020, ...)
    serial: str          # the title ID it belongs to
    files: Path          # folder with the game's files
    param: bytes         # param.bin contents for GRport
    icon: "Path | None"
    memory: bool = False  # SaveDataMemory (files holds memory.dat)


@dataclass
class Scan:
    saves: list
    encrypted: bool = False  # PS4 USB backup files found
    other_games: set = None  # title IDs of saves for other games


def param_from_sfo(sfo: dict) -> bytes:
    def text(key: str, size: int) -> bytes:
        return str(sfo.get(key, "")).encode("utf-8")[:size - 1].ljust(size, b"\0")
    user_param = sfo.get("SAVEDATA_LIST_PARAM", 0)
    user_param = user_param if isinstance(user_param, int) else 0
    out = (text("MAINTITLE", 128) + text("SUBTITLE", 128) + text("DETAIL", 1024)
           + struct.pack("<IiQ", user_param & 0xFFFFFFFF, 0, 0) + bytes(32))
    assert len(out) == PARAM_SIZE
    return out


def _valid_name(name: str) -> bool:
    return 0 < len(name) < 32 and "/" not in name and "\\" not in name and ".." not in name \
        and not name.startswith(".")


def scan(source: Path, game: games.Game) -> Scan:
    """Every save of `game` (any region) under `source`."""
    result = Scan(saves=[], other_games=set())
    seen = set()

    def add(save: FoundSave) -> None:
        if save.serial not in game.regions:
            if save.serial:
                result.other_games.add(save.serial)
            return
        if (save.name, save.memory) not in seen:
            seen.add((save.name, save.memory))
            result.saves.append(save)

    def visit(child: Path, depth: int) -> None:
        name, folder = child.name, child.parent
        if name.startswith("sce_bu_") or name == "sce_sys" or name.endswith(".sce_sys"):
            return
        sfo_path = child / "sce_sys" / "param.sfo"
        grport_param = folder / f"{name}.sce_sys" / "param.bin"
        if name == MEMORY_DIR and (child / "memory.dat").is_file():
            add(FoundSave(name, folder.name, child, b"", None, memory=True))
        elif name.endswith(".memory") and (child / "memory.dat").is_file():
            add(FoundSave(name, name[:-len(".memory")], child, b"", None, memory=True))
        elif sfo_path.is_file():
            try:
                sfo = games.read_sfo(sfo_path)
            except (OSError, ValueError, struct.error):
                return
            dir_name = str(sfo.get("SAVEDATA_DIRECTORY", "")).strip() or name
            serial = str(sfo.get("TITLE_ID", "")).strip() or folder.name
            if _valid_name(dir_name):
                icon = child / "sce_sys" / "icon0.png"
                add(FoundSave(dir_name, serial, child, param_from_sfo(sfo),
                              icon if icon.is_file() else None))
        elif grport_param.is_file() and _valid_name(name):
            data = grport_param.read_bytes()
            if len(data) == PARAM_SIZE:
                icon = grport_param.parent / "icon0.png"
                add(FoundSave(name, folder.name, child, data, icon if icon.is_file() else None))
        elif depth < MAX_DEPTH:
            try:
                children = sorted(child.iterdir())
            except OSError:
                return
            for item in children:
                if item.is_dir():
                    visit(item, depth + 1)
                elif item.name.lower().startswith("sdimg_"):
                    result.encrypted = True

    visit(Path(source), 0)
    return result


def save_root(user: Path, serial: str) -> Path:
    return Path(user) / "savedata" / "1" / serial


def _copy_files(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True)
    for item in src.iterdir():
        if item.name == "sce_sys" or item.name.startswith("sce_bu_"):
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name)
        else:
            shutil.copy2(item, dst / item.name)


def import_saves(user: Path, serial: str, saves: list) -> "Path | None":
    """Copy `saves` into GRport's save folder for `serial`, replacing saves of the same name.
    The previous saves are first copied to user/<game>/savedata-backup-<time>; returns that folder
    (None when there was nothing to back up)."""
    root = save_root(user, serial)
    memory = root.parent / f"{serial}.memory"
    backup = None
    if (root.is_dir() and any(root.iterdir())) or memory.is_dir():
        backup = Path(user) / f"savedata-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        if root.is_dir():
            shutil.copytree(root, backup / serial)
        if memory.is_dir():
            shutil.copytree(memory, backup / memory.name)
    root.mkdir(parents=True, exist_ok=True)
    for save in saves:
        if save.memory:
            memory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(save.files / "memory.dat", memory / "memory.dat")
            continue
        files, meta = root / save.name, root / f"{save.name}.sce_sys"
        for old in (files, meta):
            if old.exists():
                shutil.rmtree(old)
        _copy_files(save.files, files)
        meta.mkdir()
        (meta / "param.bin").write_bytes(save.param)
        if save.icon is not None:
            shutil.copy2(save.icon, meta / "icon0.png")
    return backup
