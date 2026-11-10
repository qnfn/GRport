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
# Threaded recording (the runtime's BB_THREADED_RECORDING): auto (on: it runs much faster in
# both games), on ("1") or off ("0").
THREADING = ("auto", "1", "0")
# Stick dead zone in percent (the runtime's BB_STICK_DEADZONE): a radial dead zone on both
# controller sticks against drift; 0 turns it off. SETUP offers these; grport.json takes 0-90.
DEADZONE_CHOICES = tuple(range(0, 41, 2))
DEADZONE_DEFAULT = 10
DEADZONE_MAX = 90
# fullscreen: exclusive (the monitor's own mode); borderless: a window covering the monitor;
# window: a real window with a title bar, kept inside the desktop.
WINDOW_MODES = ("fullscreen", "borderless", "window")
# Frame rates: Gravity Rush 2 runs at 30 (60/90/120 with the FPS patches); Gravity Rush
# Remastered at 60, and faster with a faster vblank (its game speed follows the clock).
FPS_CHOICES = {"gr1": (60, 90, 120, 144), "gr2": (30, 60, 90, 120)}
# SETUP > Display > Resolution: (Junmin Lee's "No upscaling" patch name prefix, label). The same
# names in both games' patch files; "" is the game's own 1920x1080 (no patch).
RESOLUTIONS = (
    ("Resolution 1280x720", "1280x720 (16:9)"),
    ("Resolution 1600x900", "1600x900 (16:9)"),
    ("", "1920x1080 (16:9, the game's own)"),
    ("Resolution 2560x1440", "2560x1440 (16:9, 2K)"),
    ("Resolution 3840x2160", "3840x2160 (16:9, 4K)"),
    ("16:10 1280x800", "1280x800 (16:10)"),
    ("16:10 1600x1000", "1600x1000 (16:10)"),
    ("16:10 1920x1200", "1920x1200 (16:10)"),
    ("16:10 2560x1600", "2560x1600 (16:10)"),
    ("16:10 3840x2400", "3840x2400 (16:10, 4K)"),
    ("Ultrawide 21:9 (7:3) 2520x1080", "2520x1080 (21:9)"),
    ("Ultrawide 21:9 (7:3) 3360x1440", "3360x1440 (21:9)"),
    ("Ultrawide 21:9 (7:3) 5040x2160", "5040x2160 (21:9, 4K)"),
    ("Ultrawide 2.39:1 2584x1080", "2584x1080 (2.39:1)"),
    ("Ultrawide 2.39:1 3440x1440", "3440x1440 (2.39:1)"),
    ("Ultrawide 2.39:1 5160x2160", "5160x2160 (2.39:1, 4K)"),
    ("Ultrawide 21:10 2272x1080", "2272x1080 (21:10)"),
    ("Ultrawide 21:10 3024x1440", "3024x1440 (21:10)"),
    ("Ultrawide 21:10 4536x2160", "4536x2160 (21:10, 4K)"),
    ("Super ultrawide 32:9 3840x1080", "3840x1080 (32:9)"),
    ("Super ultrawide 32:9 5120x1440", "5120x1440 (32:9)"),
    ("Super ultrawide 32:9 7680x2160", "7680x2160 (32:9, 4K)"),
    ("Super ultrawide 32:10 3456x1080", "3456x1080 (32:10)"),
    ("Super ultrawide 32:10 4608x1440", "4608x1440 (32:10)"),
    ("Super ultrawide 32:10 6912x2160", "6912x2160 (32:10, 4K)"),
    # Made by GRport from the author's 16:10 patches (respatch.py).
    ("GRport 4:3 960x720", "960x720 (4:3)"),
    ("GRport 16:10 1440x900", "1440x900 (16:10)"),
    ("GRport 4:3 1024x768", "1024x768 (4:3)"),
    ("GRport 4:3 1280x960", "1280x960 (4:3)"),
    ("GRport 4:3 1440x1080", "1440x1080 (4:3)"),
    ("GRport 4:3 1600x1200", "1600x1200 (4:3)"),
    ("GRport 4:3 1920x1440", "1920x1440 (4:3)"),
    ("GRport 4:3 2880x2160", "2880x2160 (4:3, 4K)"),
    ("GRport 5:4 1280x1024", "1280x1024 (5:4)"),
    ("GRport 5:4 1800x1440", "1800x1440 (5:4)"),
    ("GRport 5:4 2700x2160", "2700x2160 (5:4, 4K)"),
    ("GRport 3:2 1620x1080", "1620x1080 (3:2)"),
    ("GRport 3:2 2160x1440", "2160x1440 (3:2)"),
    ("GRport 3:2 3240x2160", "3240x2160 (3:2, 4K)"),
)


def resolution_label(prefix: str) -> str:
    return dict(RESOLUTIONS).get(prefix, "1920x1080")


# SETUP > Display: Render and Aspect ratio pick one of RESOLUTIONS. Per aspect ratio, its sizes
# from small to 4K (21:9 is the 2.39:1 of 2560x1080 / 3440x1440 monitors). Other RESOLUTIONS
# entries (chosen in older GRports) still work; the page then shows no Render choice.
ASPECTS = ("4:3", "16:10", "16:9", "21:9", "32:9")
RENDER_GRID = {
    "4:3": ("GRport 4:3 960x720", "GRport 4:3 1440x1080", "GRport 4:3 1920x1440",
            "GRport 4:3 2880x2160"),
    "16:10": ("16:10 1280x800", "16:10 1920x1200", "16:10 2560x1600", "16:10 3840x2400"),
    "16:9": ("Resolution 1280x720", "", "Resolution 2560x1440", "Resolution 3840x2160"),
    "21:9": ("Ultrawide 2.39:1 2584x1080", "Ultrawide 2.39:1 3440x1440",
             "Ultrawide 2.39:1 5160x2160"),
    "32:9": ("Super ultrawide 32:9 3840x1080", "Super ultrawide 32:9 5120x1440",
             "Super ultrawide 32:9 7680x2160"),
}
# SETUP > Window size: heights; the width follows the render shape (1200p is 1920x1200 on 16:10).
WINDOW_HEIGHTS = (720, 900, 1080, 1200, 1440, 1600, 2160)


def resolution_size(prefix: str) -> tuple:
    """(width, height) the game draws at with this RESOLUTIONS entry."""
    w, h = resolution_label(prefix).split()[0].split("x")
    return int(w), int(h)


def aspect_of(prefix: str) -> str:
    """The ASPECTS entry of a RESOLUTIONS entry: its own, or the nearest by shape."""
    for aspect, prefixes in RENDER_GRID.items():
        if prefix in prefixes:
            return aspect
    w, h = resolution_size(prefix)
    num = lambda a: int(a.split(":")[0]) / int(a.split(":")[1])
    return min(ASPECTS, key=lambda a: abs(num(a if a != "21:9" else "43:18") - w / h))
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
    threading: str = "auto"     # THREADING
    fps: int = 30               # FPS_CHOICES; the lowest when not one of them
    stick_deadzone: int = DEADZONE_DEFAULT  # percent, 0-DEADZONE_MAX
    ps4_pro: bool = False       # Gravity Rush 2 only: the runtime's BB_NEO (report a PS4 Pro)
    resolution: str = ""        # RESOLUTIONS: a resolution patch prefix; "" the game's 1080p
    extras: "list | None" = None  # optional patches chosen (name prefixes); None: the defaults


@dataclass
class LauncherSettings:
    theme: str = "dark"
    window_mode: str = "borderless"  # WINDOW_MODES
    window_size: str = "1080p"  # "<height>p" in the render shape, or "WxH"
    language: str = "en"        # LANGUAGES
    selected: str = "gr2"
    games: dict = field(default_factory=lambda: {key: GameSettings(fps=FPS_CHOICES[key][0])
                                                 for key in GAMES})


def window(s: LauncherSettings, g: "GameSettings | None" = None) -> tuple:
    """The window size as (width, height), at least 640x360; 1920x1080 when unreadable.
    "1080p" is that height in the shape of the game's render resolution (16:9 without g)."""
    try:
        size = s.window_size.lower()
        if size.endswith("p"):
            h = int(size[:-1])
            rw, rh = resolution_size(g.resolution) if g is not None else (16, 9)
            return max(640, round(h * rw / rh / 2) * 2), max(360, h)
        w, h = (int(v) for v in size.split("x"))
        return max(640, w), max(360, h)
    except ValueError:
        return 1920, 1080


def _valid(value, default) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, type(default))


def _load_game(key: str, raw) -> GameSettings:
    g = GameSettings(fps=FPS_CHOICES[key][0])
    if not isinstance(raw, dict):
        return g
    for f in fields(GameSettings):
        if f.name in raw and _valid(raw[f.name], getattr(g, f.name)):
            setattr(g, f.name, raw[f.name])
    extras = raw.get("extras")
    if isinstance(extras, list) and all(isinstance(e, str) for e in extras):
        g.extras = extras
    if g.readbacks not in READBACKS:
        g.readbacks = "off"
    if g.threading not in THREADING:
        g.threading = "auto"
    if g.fps not in FPS_CHOICES[key]:
        g.fps = FPS_CHOICES[key][0]
    if not 0 <= g.stick_deadzone <= DEADZONE_MAX:
        g.stick_deadzone = DEADZONE_DEFAULT
    if g.resolution not in dict(RESOLUTIONS):
        g.resolution = ""
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
    s.games = {key: _load_game(key, games.get(key)) for key in GAMES}
    # Launchers up to 0.1.1 saved fullscreen=true/false; their fullscreen was borderless.
    if "window_mode" not in raw and isinstance(raw.get("fullscreen"), bool):
        s.window_mode = "borderless" if raw["fullscreen"] else "window"
    if s.window_mode not in WINDOW_MODES:
        s.window_mode = "borderless"
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
