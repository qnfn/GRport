# SPDX-License-Identifier: GPL-2.0-or-later
"""The two games, and reading a dumped game folder: which game, region and version it is."""
import struct
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class Game:
    key: str
    title: str
    short: str
    badge: str           # assets/<badge>: the card icon
    regions: dict = field(default_factory=dict)  # serial -> region name


GR1 = Game(
    key="gr1",
    title="Gravity Rush Remastered",
    short="Gravity Rush",
    badge="game_gr1.png",
    regions={"CUSA01113": "Europe", "CUSA01130": "USA", "CUSA01112": "Asia",
             "CUSA02318": "Asia", "CUSA00546": "Asia", "CUSA02443": "Asia", "CUSA04246": "Asia",
             "PCJS50004": "Japan", "PCJS50008": "Japan", "PCJS66015": "Japan",
             "PCJS66029": "Japan"},
)

GR2 = Game(
    key="gr2",
    title="Gravity Rush 2",
    short="Gravity Rush 2",
    badge="game_gr2.png",
    regions={"CUSA03694": "USA", "CUSA04934": "Europe", "CUSA04943": "Asia",
             "CUSA04935": "Asia", "CUSA00547": "Asia", "PCJS50010": "Japan",
             "PCAS00079": "Asia"},
)

GAMES = {GR1.key: GR1, GR2.key: GR2}
SUPPORTED_REGIONS = ("USA", "Europe")  # the builds GRport is tested on


# The region from the content ID's first letters (UP9000-CUSA03694_00-...): reliable for every
# release, where the serial table above may miss one.
CONTENT_REGIONS = {"UP": "USA", "EP": "Europe", "JP": "Japan", "HP": "Asia", "KP": "Asia"}


def game_for_serial(serial: str) -> "Game | None":
    for game in GAMES.values():
        if serial in game.regions:
            return game
    return None


def game_for_title(title: str) -> "Game | None":
    """A Gravity Rush release the serial table does not list, by its title."""
    t = title.lower()
    if "gravity rush" not in t and "gravity daze" not in t:
        return None
    return GR2 if "2" in t else GR1


def region_of(sfo: dict, game: Game, serial: str) -> str:
    content = str(sfo.get("CONTENT_ID", "")).strip().upper()
    return CONTENT_REGIONS.get(content[:2]) or game.regions.get(serial, "Unknown region")


# ---------------------------------------------------------------- param.sfo

def read_sfo(path: Path) -> dict:
    """The keys of a PS4 param.sfo: strings as str, integers as int."""
    data = Path(path).read_bytes()
    magic, _version, key_table, data_table, count = struct.unpack_from("<4sIIII", data, 0)
    if magic != b"\x00PSF":
        raise ValueError("not a param.sfo")
    out = {}
    for i in range(count):
        key_off, fmt, length, _max, data_off = struct.unpack_from("<HHIII", data, 20 + i * 16)
        start = key_table + key_off
        name = data[start:data.index(b"\x00", start)].decode("ascii", "replace")
        raw = data[data_table + data_off:data_table + data_off + length]
        if fmt == 0x0404 and length == 4:
            out[name] = struct.unpack("<I", raw)[0]
        else:
            out[name] = raw.rstrip(b"\x00").decode("utf-8", "replace")
    return out


# ---------------------------------------------------------------- game folders

@dataclass(frozen=True)
class GameFolder:
    folder: Path
    game: "Game | None"
    serial: str
    region: str
    version: str
    problem: str = ""   # empty when the folder is ready to play
    # The game's update kept in a folder of its own (shadPS4's <game>-UPDATE): its files replace
    # the game's. None when there is none, or it was copied over the game (that works as well).
    update: "Path | None" = None

    def file(self, name: str) -> Path:
        """A game file as the game sees it: the update's copy when it has one."""
        if self.update is not None and (self.update / name).exists():
            return self.update / name
        return self.folder / name

    @property
    def eboot(self) -> Path:
        return self.file("eboot.bin")

    @property
    def ok(self) -> bool:
        return not self.problem

    @property
    def art(self) -> "Path | None":
        """The game's own background picture from the player's dump, for the card."""
        for name in ("pic1.png", "pic0.png"):
            path = self.file(f"sce_sys/{name}")
            if path.is_file():
                return path
        return None


UPDATE_SUFFIXES = ("-update", "-patch")  # shadPS4's and GR2port's names for the update folder
LIBC = Path("sce_module") / "libc.prx"   # in the game itself; an update rarely has one


def _sfo_or_none(folder: Path) -> "dict | None":
    try:
        return read_sfo(folder / "sce_sys" / "param.sfo")
    except (OSError, ValueError, struct.error):
        return None


def _is_update_only(folder: Path, sfo: dict) -> bool:
    """The update on its own: only the files it changes (no libc), a patch package (category gp)
    or a folder named like one. A game with its update copied over it has everything."""
    if (folder / LIBC).is_file():
        return False
    return (str(sfo.get("CATEGORY", "")).startswith("gp")
            or folder.name.lower().endswith(UPDATE_SUFFIXES))


def _siblings(folder: Path, serial: str) -> list:
    """(folder, param.sfo) of the other game folders next to `folder` with the same serial."""
    try:
        children = sorted(p for p in folder.parent.iterdir() if p.is_dir() and p != folder)
    except OSError:
        return []
    out = []
    for child in children:
        sfo = _sfo_or_none(child)
        if sfo is not None and str(sfo.get("TITLE_ID", "")).strip() == serial:
            out.append((child, sfo))
    return out


def _version_key(sfo: dict) -> tuple:
    text = str(sfo.get("APP_VER") or sfo.get("VERSION") or "")
    return tuple(int(x) if x.isdigit() else 0 for x in text.split("."))


def find_base(update: Path, serial: str) -> "Path | None":
    """The game folder next to an update folder: <name> for <name>-UPDATE first."""
    bases = [p for p, sfo in _siblings(update, serial) if not _is_update_only(p, sfo)]
    stem = update.name.lower()
    for suffix in UPDATE_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
    bases.sort(key=lambda p: p.name.lower() != stem)
    return bases[0] if bases else None


def find_update(base: Path, serial: str) -> "Path | None":
    """The update folder next to a game folder: <name>-UPDATE / <name>-patch first, else the
    newest update of the same game."""
    updates = [(p, sfo) for p, sfo in _siblings(base, serial) if _is_update_only(p, sfo)]
    named = {base.name.lower() + s for s in UPDATE_SUFFIXES}
    updates.sort(key=lambda u: (u[0].name.lower() not in named,
                                tuple(-v for v in _version_key(u[1]))))
    return updates[0][0] if updates else None


def _candidate(folder: Path) -> Path:
    """Accept the game folder itself, its eboot.bin, or a folder holding one CUSA folder."""
    folder = Path(folder)
    if folder.is_file():
        folder = folder.parent
    if (folder / "sce_sys" / "param.sfo").is_file():
        return folder
    inner = [p for p in sorted(folder.glob("*"))
             if p.is_dir() and (p / "sce_sys" / "param.sfo").is_file()]
    return inner[0] if len(inner) == 1 else folder


def inspect(folder: "Path | str") -> GameFolder:
    """Which game the folder holds and whether it can be played."""
    folder = _candidate(Path(folder))
    sfo_path = folder / "sce_sys" / "param.sfo"
    if not sfo_path.is_file():
        return GameFolder(folder, None, "", "", "", "This folder has no game in it "
                          "(sce_sys/param.sfo is missing).")
    try:
        sfo = read_sfo(sfo_path)
    except (OSError, ValueError, struct.error) as e:
        return GameFolder(folder, None, "", "", "", f"param.sfo could not be read: {e}")
    serial = str(sfo.get("TITLE_ID", "")).strip()
    version = str(sfo.get("APP_VER") or sfo.get("VERSION") or "").strip()
    game = game_for_serial(serial) or game_for_title(str(sfo.get("TITLE", "")))
    if game is None:
        title = sfo.get("TITLE", "an unknown game")
        return GameFolder(folder, None, serial, "", version,
                          f"This is {title} ({serial}), not a Gravity Rush game.")
    region = region_of(sfo, game, serial)
    update = None
    if _is_update_only(folder, sfo):
        base = find_base(folder, serial)
        if base is None:
            return GameFolder(folder, game, serial, region, version,
                              f"This folder is only the game's update (v{version}). Choose the "
                              "game's own folder: keep the update next to it, or copy the "
                              "update's files over the game.")
        folder, update = base, folder
    else:
        update = find_update(folder, serial)
        if update is not None:
            version = str((_sfo_or_none(update) or {}).get("APP_VER") or version).strip()
    info = GameFolder(folder, game, serial, region, version, "", update)
    if not info.eboot.is_file():
        problem = "eboot.bin is missing. Extract the whole game into this folder."
    elif not (folder / LIBC).is_file():
        problem = "sce_module/libc.prx is missing. Extract the whole game into this folder."
    else:
        problem = damaged_archives(folder) or (damaged_archives(update) if update else "")
    return replace(info, problem=problem)


def psarc_missing_bytes(path: Path) -> int:
    """How many bytes a .psarc archive is short of what its own table of contents says it holds
    (0 when complete). ValueError when it is not a PSARC at all (zeros, still encrypted)."""
    with open(path, "rb") as f:
        head = f.read(32)
        if len(head) < 32 or head[:4] != b"PSAR":
            raise ValueError("not a PSARC archive")
        toc_length, entry_size, entries, block = struct.unpack(">IIII", head[12:28])
        if entry_size < 30 or block == 0 or toc_length < 32 + entries * entry_size:
            raise ValueError("bad PSARC header")
        toc = f.read(toc_length - 32)
        size = f.seek(0, 2)
    if len(toc) < toc_length - 32:
        return toc_length - len(toc) - 32
    width = 2 if block <= 0x10000 else 3 if block <= 0x1000000 else 4
    table = toc[entries * entry_size:]
    blocks = [int.from_bytes(table[i:i + width], "big") for i in range(0, len(table) - width + 1, width)]
    end = 0
    for i in range(entries):
        e = toc[i * entry_size:(i + 1) * entry_size]
        first = int.from_bytes(e[16:20], "big")
        length = int.from_bytes(e[20:25], "big")
        offset = int.from_bytes(e[25:30], "big")
        count = (length + block - 1) // block
        if first + count > len(blocks):
            raise ValueError("bad PSARC block table")
        end = max(end, offset + sum(blocks[j] or block for j in range(first, first + count)))
    return max(0, end - size)


_archive_checks: dict = {}


def damaged_archives(folder: Path) -> str:
    """Why the game's .psarc data archives cannot work ('' when they look whole). A copy through
    a FAT32 drive cuts files at 4 GB, and Gravity Rush 2's two biggest are 10 and 16 GB (#18:
    every font failed to open, then a crash at the start with "code 3")."""
    for path in sorted(list(folder.glob("*.psarc")) + list(folder.glob("*/*.psarc"))):
        try:
            stat = path.stat()
            key = (str(path), stat.st_size, stat.st_mtime_ns)
            if key not in _archive_checks:
                try:
                    missing = psarc_missing_bytes(path)
                    _archive_checks[key] = (f"is cut short ({missing / 2**30:.1f} GB missing)"
                                            if missing else "")
                except ValueError:
                    _archive_checks[key] = "is damaged"
            why = _archive_checks[key]
        except OSError as e:
            why = f"cannot be read ({e.strerror or e})"
        if why:
            return f"{path.relative_to(folder).as_posix()} {why}: copy the game files again."
    return ""


def find_games(base: Path, depth: int = 3) -> dict:
    """Game folders under `base` (a few levels deep), first one found per game."""
    found: dict = {}

    def walk(folder: Path, level: int) -> None:
        if level > depth or len(found) == len(GAMES):
            return
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir())
        except OSError:
            return
        if (folder / "sce_sys" / "param.sfo").is_file():
            info = inspect(folder)
            if info.game is not None and info.game.key not in found:
                found[info.game.key] = info
            return
        for child in children:
            if child.name.startswith(".") or child.name.lower() in ("data", "runtime", "user", "patches"):
                continue
            walk(child, level + 1)

    walk(Path(base), 0)
    return found
