# SPDX-License-Identifier: GPL-2.0-or-later
"""Trophies: what each game has and what the player has earned.

The game's trophy file (sce_sys/trophy/trophy00.trp) holds every trophy's icon as a plain PNG
(TROP000.PNG, TROP001.PNG...); its names and texts are encrypted, so they come from
assets/trophies-<game>.json when GRport has that list. The runtime keeps the earned ones in
user/<game>/trophies/1.txt ("id unix-time" lines; older runs only appended trophies.log in the
same format) and shows a pop-up on each unlock, named from user/<game>/trophy-names.txt.
"""
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

TRP_MAGIC = 0xDCA24D00
GRADES = ("platinum", "gold", "silver", "bronze")


@dataclass
class Trophy:
    id: int
    name: str
    detail: str
    grade: str          # GRADES, or "" when GRport has no list for the game
    earned: int = 0     # unix time, 0 when not earned


def trp_entries(path: Path) -> dict:
    """{name: (offset, size)} of a trophy00.trp; {} when it is not one."""
    try:
        with open(path, "rb") as f:
            head = f.read(0x60)
            if len(head) < 0x60:
                return {}
            magic, _version, _size, count, entry_size = struct.unpack_from(">IIQII", head, 0)
            if magic != TRP_MAGIC or not 0 < count < 4096 or entry_size < 0x30:
                return {}
            table = f.read(count * entry_size)
    except OSError:
        return {}
    out = {}
    for i in range(min(count, len(table) // entry_size)):
        entry = table[i * entry_size:(i + 1) * entry_size]
        name = entry[:32].split(b"\0")[0].decode("ascii", "replace")
        offset, size = struct.unpack_from(">QQ", entry, 32)
        out[name] = (offset, size)
    return out


def trp_path(game_folder: Path) -> Path:
    return Path(game_folder) / "sce_sys" / "trophy" / "trophy00.trp"


def icon_ids(trp: Path) -> list:
    """The trophy ids of the game: one TROPnnn.PNG per trophy."""
    ids = []
    for name in trp_entries(trp):
        m = re.fullmatch(r"TROP(\d{3})\.PNG", name)
        if m:
            ids.append(int(m.group(1)))
    return sorted(ids)


def extract_icons(trp: Path, folder: Path) -> Path:
    """Writes TROPnnn.PNG and ICON0.PNG into folder (once); returns folder."""
    entries = trp_entries(trp)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with open(trp, "rb") as f:
            for name, (offset, size) in entries.items():
                if not (name.startswith("TROP") or name == "ICON0.PNG") or not name.endswith(".PNG"):
                    continue
                target = folder / name.lower()
                if target.is_file() and target.stat().st_size == size:
                    continue
                f.seek(offset)
                data = f.read(size)
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    target.write_bytes(data)
    except OSError:
        pass
    return folder


def names(assets: Path, key: str) -> dict:
    """{id: (name, detail, grade)} from assets/trophies-<key>.json; {} when there is none."""
    try:
        raw = json.loads((assets / f"trophies-{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for item in raw if isinstance(raw, list) else []:
        try:
            grade = str(item.get("grade", "")).lower()
            out[int(item["id"])] = (str(item["name"]), str(item.get("detail", "")),
                                    grade if grade in GRADES else "")
        except (KeyError, TypeError, ValueError):
            continue
    return out


def earned(user: Path) -> dict:
    """{id: unix time} earned in this user folder (all players' lists, earliest time)."""
    out: dict = {}
    files = sorted((user / "trophies").glob("*.txt")) + [user / "trophies.log"]
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                continue
            tid, when = int(parts[0]), int(parts[1])
            if 0 <= tid < 128 and when > 0 and (tid not in out or when < out[tid]):
                out[tid] = when
    return out


def listing(trp: Path, assets: Path, key: str, user: Path) -> list:
    """Every trophy of the game, in id order, with what the player earned."""
    known = names(assets, key)
    got = earned(user)
    ids = icon_ids(trp) or sorted(known)
    out = []
    for tid in ids:
        name, detail, grade = known.get(tid, (f"Trophy {tid}", "", ""))
        out.append(Trophy(tid, name, detail, grade, got.get(tid, 0)))
    return out


def write_names(assets: Path, key: str, user: Path) -> None:
    """user/<game>/trophy-names.txt for the runtime's pop-up ("id<TAB>grade<TAB>name")."""
    known = names(assets, key)
    if not known:
        return
    text = "".join(f"{tid}\t{grade}\t{name}\n" for tid, (name, _, grade) in sorted(known.items()))
    try:
        user.mkdir(parents=True, exist_ok=True)
        target = user / "trophy-names.txt"
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
    except OSError:
        pass
