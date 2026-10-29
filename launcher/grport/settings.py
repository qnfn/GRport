# SPDX-License-Identifier: GPL-2.0-or-later
"""The launcher's own settings (grport.json): window, theme, and each game's choices.

Graphics, upscaler and frame rate are set in the game itself (GRport's in-game menu: Insert,
or L3+R3 on a controller), not here. Keys older launchers wrote are ignored.
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields

from .games import GAMES
from .paths import AppPaths

READBACKS = ("off", "relaxed", "precise")
# The console language the games see (menus, subtitles; the voices are the games' own
# invented language): key, name, PS4 language code.
LANGUAGES = (("en", "English", 1), ("ja", "Japanese", 0), ("fr", "French", 2),
             ("es", "Spanish", 3), ("de", "German", 4), ("it", "Italian", 5),
             ("pt-br", "Portuguese (Brazil)", 17), ("ru", "Russian", 8), ("ko", "Korean", 9),
             ("zh-hant", "Chinese (Traditional)", 10), ("en-gb", "English (UK)", 18))


@dataclass
class GameSettings:
    folder: str = ""
    readbacks: str = "off"      # READBACKS
    fps: int = 30               # Gravity Rush 2: 30, or 60/90/120 with the FPS patches


@dataclass
class LauncherSettings:
    theme: str = "dark"
    fullscreen: bool = True
    window_size: str = "1920x1080"
    language: str = "en"        # LANGUAGES
    selected: str = "gr2"
    games: dict = field(default_factory=lambda: {key: GameSettings() for key in GAMES})


def window(s: LauncherSettings) -> tuple:
    """The window size as (width, height), at least 640x360; 1920x1080 when unreadable."""
    try:
        w, h = (int(v) for v in s.window_size.lower().split("x"))
        return max(640, w), max(360, h)
    except ValueError:
        return 1920, 1080


def _valid(value, default) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, type(default))


def _load_game(raw) -> GameSettings:
    g = GameSettings()
    if not isinstance(raw, dict):
        return g
    for f in fields(GameSettings):
        if f.name in raw and _valid(raw[f.name], getattr(g, f.name)):
            setattr(g, f.name, raw[f.name])
    if g.readbacks not in READBACKS:
        g.readbacks = "off"
    if g.fps not in (30, 60, 90, 120):
        g.fps = 30
    return g


def load_settings(paths: AppPaths) -> LauncherSettings:
    s = LauncherSettings()
    try:
        raw = json.loads(paths.settings_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return s
    if not isinstance(raw, dict):
        return s
    for f in fields(LauncherSettings):
        if f.name == "games" or f.name not in raw:
            continue
        if _valid(raw[f.name], getattr(s, f.name)):
            setattr(s, f.name, raw[f.name])
    games = raw.get("games") if isinstance(raw.get("games"), dict) else {}
    s.games = {key: _load_game(games.get(key)) for key in GAMES}
    if s.selected not in GAMES:
        s.selected = "gr2"
    if s.language not in (key for key, _, _ in LANGUAGES):
        s.language = "en"
    if s.theme not in ("dark", "light"):
        s.theme = "dark"
    return s


def save_settings(paths: AppPaths, s: LauncherSettings) -> None:
    data = asdict(s)
    paths.root.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=paths.root, prefix=".grport-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, paths.settings_json)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
