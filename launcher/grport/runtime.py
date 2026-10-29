# SPDX-License-Identifier: GPL-2.0-or-later
"""GRport's own runtime (the DCport-family native runtime): preparing a game and starting it.

Layout in the GRport folder: runtime/GRport-runtime.exe (with its DLLs) and
runtime/gr-prepare.exe; each game's prepared image in data/<game>/ and its saves and
settings in user/<game>/. Fonts, audio and the system libraries are the runtime's own.
"""
import hashlib
import os
from pathlib import Path

from .games import GameFolder
from .paths import AppPaths
from .settings import LANGUAGES, LauncherSettings, window

READBACKS = {"off": "0", "relaxed": "1", "precise": "2"}


def exe(paths: AppPaths) -> Path:
    return paths.root / "runtime" / "GRport-runtime.exe"


def prepare_exe(paths: AppPaths) -> Path:
    return paths.root / "runtime" / "gr-prepare.exe"


def data_dir(paths: AppPaths, key: str) -> Path:
    return paths.root / "data" / key


def user_dir(paths: AppPaths, key: str) -> Path:
    return paths.root / "user" / key


def prepare_log(paths: AppPaths, key: str) -> Path:
    return data_dir(paths, key) / "prepare.log"


def missing(paths: AppPaths) -> str:
    for path in (exe(paths), prepare_exe(paths)):
        if not path.is_file():
            return f"GRport's runtime is missing: {path}"
    return ""


def _describe(path: Path) -> str:
    st = path.stat()
    return f"{path} {st.st_size} {st.st_mtime_ns}"


def is_prepared(paths: AppPaths, info: GameFolder, patch: "Path | None" = None) -> bool:
    """The prepared image exists and was made from this eboot, this runtime and these patches."""
    data = data_dir(paths, info.game.key)
    try:
        stamp = (data / "source.txt").read_text(encoding="utf-8").splitlines()
        wanted = [_describe(info.eboot), _describe(exe(paths))]
        if patch:
            wanted.append("patches " + hashlib.sha1(patch.read_bytes()).hexdigest()[:16])
    except OSError:
        return False
    return stamp == wanted and (data / "boot-linked.bin").is_file()


def prepare_command(paths: AppPaths, info: GameFolder, patch: "Path | None" = None) -> list:
    return [str(prepare_exe(paths)), str(info.folder), str(data_dir(paths, info.game.key)),
            str(exe(paths))] + ([str(patch)] if patch else [])


def command(paths: AppPaths, info: GameFolder, patch: "Path | None" = None) -> list:
    data = data_dir(paths, info.game.key)
    return [str(exe(paths)), str(data / "boot-linked.bin"), "--content-profile",
            str(data / "content.bin"), "--app0", str(info.folder),
            "--user", str(user_dir(paths, info.game.key)), "--timeout", "0"] + (
        ["--patches", str(patch)] if patch else [])


def env(paths: AppPaths, s: LauncherSettings, info: GameFolder, base=None) -> dict:
    g = s.games[info.game.key]
    user = user_dir(paths, info.game.key)
    out = dict(os.environ if base is None else base)
    out.update({
        "BB_GPU_USER_DIR": str(user),
        "BB_CONFIG": str(user / "grport.ini"),
        "BB_LENIENT_IMPORTS": "1",
        "BB_READBACKS": READBACKS.get(g.readbacks, "0"),
        "BB_DRAW_PIPE": "1",
        "BB_PREP_WORKERS": "0",
        "BB_WINDOW_MODE": s.window_mode,
        "BB_FULLSCREEN": "0" if s.window_mode == "window" else "1",
        "BB_WINDOW_SIZE": "{}x{}".format(*window(s)),
        "BB_DMEM_MB": "5056",
        "BB_USER_NAME": "Kat",
        "BB_FPS_LOG": "1",
        "BB_LANGUAGE": str(next(code for key, _, code in LANGUAGES if key == s.language)),
    })
    # SETUP > Threading: Auto leaves it to the runtime (off).
    out.pop("BB_THREADED_RECORDING", None)
    if g.threading in ("0", "1"):
        out["BB_THREADED_RECORDING"] = g.threading
    # FSR / DLSS anti-aliasing on the scene before the tonemap (the in-game menu); Gravity
    # Rush 2's motion comes from its own velocity target.
    out["BB_GR_UPSCALE"] = "1"
    # Both games pace themselves by the vblank: Gravity Rush 2 at its FPS patch's rate,
    # Gravity Rush Remastered (60 on the PS4) at any rate, its game speed following the clock.
    if (info.game.key == "gr2" and g.fps != 30) or (info.game.key == "gr1" and g.fps != 60):
        out["BB_VBLANK_HZ"] = str(g.fps)
    return out
