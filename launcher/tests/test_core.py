# SPDX-License-Identifier: GPL-2.0-or-later
"""Game detection, settings, and the runtime's command and environment."""
import json
import struct
from pathlib import Path

import pytest

from grport import games, runtime
from grport.paths import AppPaths
from grport.settings import LauncherSettings, load_settings, save_settings, window


def make_sfo(path: Path, values: dict) -> None:
    """A minimal param.sfo with string values."""
    keys = b""
    data = b""
    entries = []
    for name, value in values.items():
        raw = value.encode() + b"\x00"
        entries.append((len(keys), len(raw), len(data)))
        keys += name.encode() + b"\x00"
        data += raw
    key_table = 20 + 16 * len(values)
    data_table = key_table + len(keys)
    out = struct.pack("<4sIIII", b"\x00PSF", 0x101, key_table, data_table, len(values))
    for (koff, length, doff) in entries:
        out += struct.pack("<HHIII", koff, 0x0204, length, length, doff)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out + keys + data)


def make_game(folder: Path, serial: str, version: str, eboot: bool = True) -> Path:
    make_sfo(folder / "sce_sys" / "param.sfo",
             {"TITLE_ID": serial, "APP_VER": version, "TITLE": "Test"})
    if eboot:
        (folder / "eboot.bin").write_bytes(b"\x7fELF")
    return folder


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    return AppPaths.for_root(tmp_path / "GRport")


# --- games -------------------------------------------------------------------

@pytest.mark.parametrize("serial,key,region", [
    ("CUSA01113", "gr1", "USA"), ("CUSA01130", "gr1", "Europe"),
    ("CUSA03694", "gr2", "USA"), ("CUSA04934", "gr2", "Europe"),
])
def test_both_regions_of_both_games_are_recognised(tmp_path, serial, key, region):
    info = games.inspect(make_game(tmp_path / serial, serial, "01.00"))
    assert info.game.key == key and info.region == region and info.ok


def test_a_folder_holding_the_game_folder_is_accepted(tmp_path):
    make_game(tmp_path / "GR2" / "CUSA03694", "CUSA03694", "01.11")
    info = games.inspect(tmp_path / "GR2")
    assert info.serial == "CUSA03694" and info.version == "01.11"


def test_missing_eboot_and_other_games_are_explained(tmp_path):
    assert "eboot.bin" in games.inspect(make_game(tmp_path / "a", "CUSA03694", "01.11",
                                                  eboot=False)).problem
    other = games.inspect(make_game(tmp_path / "b", "CUSA00003", "01.28"))
    assert other.game is None and "not a Gravity Rush game" in other.problem
    assert "no game" in games.inspect(tmp_path / "empty").problem


def test_find_games_finds_one_folder_per_game(tmp_path):
    make_game(tmp_path / "GR1" / "CUSA01130", "CUSA01130", "01.00")
    make_game(tmp_path / "GR2" / "CUSA04934", "CUSA04934", "01.11")
    found = games.find_games(tmp_path)
    assert found["gr1"].region == "Europe" and found["gr2"].region == "Europe"


def test_the_launchers_own_folders_are_not_searched(tmp_path):
    make_game(tmp_path / "user" / "CUSA03694", "CUSA03694", "01.11")
    make_game(tmp_path / "data" / "CUSA01113", "CUSA01113", "01.00")
    assert games.find_games(tmp_path) == {}


# --- runtime ------------------------------------------------------------------

def test_runtime_command_and_env(paths, tmp_path):
    info = games.inspect(make_game(tmp_path / "CUSA04934", "CUSA04934", "01.11"))
    s = LauncherSettings()
    s.fullscreen, s.window_size = False, "2560x1440"
    s.games["gr2"].readbacks = "precise"
    cmd = runtime.command(paths, info)
    assert cmd[0] == str(runtime.exe(paths)) and str(info.folder) in cmd
    env = runtime.env(paths, s, info, base={})
    assert env["BB_FULLSCREEN"] == "0" and env["BB_WINDOW_SIZE"] == "2560x1440"
    assert env["BB_READBACKS"] == "2"
    assert env["BB_GPU_USER_DIR"] == str(runtime.user_dir(paths, "gr2"))
    assert "runtime is missing" in runtime.missing(paths)
    assert not runtime.is_prepared(paths, info)


def test_window_size_is_read_safely():
    s = LauncherSettings()
    s.window_size = "100x100"
    assert window(s) == (640, 360)
    s.window_size = "big"
    assert window(s) == (1920, 1080)


# --- settings -----------------------------------------------------------------

def test_settings_round_trip_and_bad_values(paths):
    s = LauncherSettings()
    s.games["gr2"].readbacks = "relaxed"
    s.selected = "gr1"
    save_settings(paths, s)
    back = load_settings(paths)
    assert back.games["gr2"].readbacks == "relaxed" and back.selected == "gr1"
    paths.settings_json.write_text(json.dumps({"theme": "pink", "selected": "gr9",
                                               "games": {"gr2": {"readbacks": "magic"}}}))
    bad = load_settings(paths)
    assert bad.theme == "dark" and bad.selected == "gr2" and bad.games["gr2"].readbacks == "off"


def test_old_settings_files_still_load(paths):
    """grport.json of 0.1.0 has keys that no longer exist; they are ignored."""
    paths.root.mkdir(parents=True)
    paths.settings_json.write_text(json.dumps({
        "theme": "light", "fullscreen": False, "window_size": "1600x900", "selected": "gr1",
        "games": {"gr1": {"folder": "X:/GR1", "engine": "other", "aspect": "21:9",
                          "output": "1440p", "upscaler": "fsr4", "quality": "Balanced",
                          "fps": 144, "motion_blur": False, "readbacks": "precise",
                          "patches": ["a"], "patches_off": ["b"], "costume": "c"}}}))
    s = load_settings(paths)
    assert s.theme == "light" and not s.fullscreen and s.window_size == "1600x900"
    assert s.games["gr1"].folder == "X:/GR1" and s.games["gr1"].readbacks == "precise"
    assert not hasattr(s.games["gr1"], "engine")
    save_settings(paths, s)
    assert "engine" not in json.loads(paths.settings_json.read_text())["games"]["gr1"]
