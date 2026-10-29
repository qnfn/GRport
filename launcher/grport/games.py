# SPDX-License-Identifier: GPL-2.0-or-later
"""The two games, and reading a dumped game folder: which game, region and version it is."""
import struct
from dataclasses import dataclass, field
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
    regions={"CUSA01113": "USA", "CUSA01130": "Europe", "CUSA01112": "Asia",
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


def game_for_serial(serial: str) -> "Game | None":
    for game in GAMES.values():
        if serial in game.regions:
            return game
    return None


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

    @property
    def eboot(self) -> Path:
        return self.folder / "eboot.bin"

    @property
    def ok(self) -> bool:
        return not self.problem

    @property
    def art(self) -> "Path | None":
        """The game's own background picture from the player's dump, for the card."""
        for name in ("pic1.png", "pic0.png"):
            path = self.folder / "sce_sys" / name
            if path.is_file():
                return path
        return None


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
    game = game_for_serial(serial)
    if game is None:
        title = sfo.get("TITLE", "an unknown game")
        return GameFolder(folder, None, serial, "", version,
                          f"This is {title} ({serial}), not a Gravity Rush game.")
    region = game.regions[serial]
    problem = ""
    if not (folder / "eboot.bin").is_file():
        problem = "eboot.bin is missing. Extract the whole game into this folder."
    return GameFolder(folder, game, serial, region, version, problem)


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
