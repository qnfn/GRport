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


def make_game(folder: Path, serial: str, version: str, eboot: bool = True,
              content_id: str = "", title: str = "Test") -> Path:
    values = {"TITLE_ID": serial, "APP_VER": version, "TITLE": title}
    if content_id:
        values["CONTENT_ID"] = content_id
    make_sfo(folder / "sce_sys" / "param.sfo", values)
    if eboot:
        (folder / "eboot.bin").write_bytes(b"\x7fELF")
    return folder


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    return AppPaths.for_root(tmp_path / "GRport")


# --- games -------------------------------------------------------------------

@pytest.mark.parametrize("serial,key,region", [
    ("CUSA01130", "gr1", "USA"), ("CUSA01113", "gr1", "Europe"),
    ("CUSA03694", "gr2", "USA"), ("CUSA04934", "gr2", "Europe"),
])
def test_both_regions_of_both_games_are_recognised(tmp_path, serial, key, region):
    info = games.inspect(make_game(tmp_path / serial, serial, "01.00"))
    assert info.game.key == key and info.region == region and info.ok


def test_the_content_id_gives_the_region_and_the_title_an_unlisted_release(tmp_path):
    eu = games.inspect(make_game(tmp_path / "a", "CUSA01113", "01.00",
                                 content_id="EP9000-CUSA01113_00-GRAVITYRUSHHDEU1"))
    assert eu.game.key == "gr1" and eu.region == "Europe"
    other = games.inspect(make_game(tmp_path / "b", "CUSA99999", "01.11", title="GRAVITY RUSH 2",
                                    content_id="EP9000-CUSA99999_00-GRAVITYRUSH20000"))
    assert other.game.key == "gr2" and other.region == "Europe" and other.ok


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
    make_game(tmp_path / "GR1" / "CUSA01113", "CUSA01113", "01.00")
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
    s.window_mode, s.window_size = "window", "2560x1440"
    s.games["gr2"].readbacks = "precise"
    cmd = runtime.command(paths, info)
    assert cmd[0] == str(runtime.exe(paths)) and str(info.folder) in cmd
    env = runtime.env(paths, s, info, base={})
    assert env["BB_WINDOW_MODE"] == "window" and env["BB_FULLSCREEN"] == "0"
    assert env["BB_WINDOW_SIZE"] == "2560x1440" and "BB_VBLANK_HZ" not in env
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
    assert s.theme == "light" and s.window_mode == "window" and s.window_size == "1600x900"
    assert s.games["gr1"].folder == "X:/GR1" and s.games["gr1"].readbacks == "precise"
    assert not hasattr(s.games["gr1"], "engine")
    save_settings(paths, s)
    assert "engine" not in json.loads(paths.settings_json.read_text())["games"]["gr1"]


# --- frame rate and optional patches --------------------------------------------

def test_frame_rates_and_patches_per_game(paths, tmp_path):
    from grport import patches
    s = LauncherSettings()
    assert s.games["gr1"].fps == 60 and s.games["gr2"].fps == 30
    assert s.window_mode == "borderless"
    assert patches.wanted(60, "gr1", []) == []
    assert patches.wanted(120, "gr1", ["Skip intro"]) == [patches.GR1_KICK_FIX, "Skip intro"]
    assert patches.wanted(30, "gr2", patches.default_extras("gr2"))[:3] == [
        patches.CRASH_FIX, patches.DLC_UNLOCK, "Disable motion blur"]
    assert patches.wanted(30, "gr2", ["unknown", "Unlock All DLC"]) == [
        patches.CRASH_FIX, patches.DLC_UNLOCK]
    info = games.inspect(make_game(tmp_path / "CUSA01113", "CUSA01113", "01.00"))
    s.games["gr1"].fps = 120
    assert runtime.env(paths, s, info, base={})["BB_VBLANK_HZ"] == "120"


def test_old_fullscreen_setting_becomes_a_window_mode(paths):
    paths.root.mkdir(parents=True)
    paths.settings_json.write_text(json.dumps({"fullscreen": True,
                                               "games": {"gr1": {"fps": 30, "extras": ["Skip intro"]}}}))
    s = load_settings(paths)
    assert s.window_mode == "borderless" and s.games["gr1"].fps == 60
    assert s.games["gr1"].extras == ["Skip intro"]


def test_shortcut_points_at_the_launcher(paths, tmp_path):
    from grport import shortcuts
    (paths.root).mkdir(parents=True, exist_ok=True)
    lnk = shortcuts.create(paths, tmp_path / "Desktop")
    assert lnk.name == "GRport.lnk" and lnk.stat().st_size > 0
    assert shortcuts.start_menu_dir().name == "Programs"


def test_threading_choice_reaches_the_runtime(paths, tmp_path):
    info = games.inspect(make_game(tmp_path / "CUSA03694", "CUSA03694", "01.11"))
    s = LauncherSettings()
    assert runtime.env(paths, s, info, base={})["BB_THREADED_RECORDING"] == "1"  # Auto: on
    s.games["gr2"].threading = "0"
    assert runtime.env(paths, s, info, base={"BB_THREADED_RECORDING": "1"})["BB_THREADED_RECORDING"] == "0"


def test_stick_deadzone_reaches_the_runtime_and_bad_values_reset(paths, tmp_path):
    info = games.inspect(make_game(tmp_path / "CUSA03694", "CUSA03694", "01.11"))
    s = LauncherSettings()
    assert runtime.env(paths, s, info, base={})["BB_STICK_DEADZONE"] == "10"  # the default
    s.games["gr2"].stick_deadzone = 0
    assert runtime.env(paths, s, info, base={})["BB_STICK_DEADZONE"] == "0"   # off
    s.games["gr2"].stick_deadzone = 33  # any value from grport.json, not only SETUP's steps
    save_settings(paths, s)
    assert load_settings(paths).games["gr2"].stick_deadzone == 33
    for bad in (-5, 91, "12", True):
        paths.settings_json.write_text(json.dumps({"games": {"gr2": {"stick_deadzone": bad}}}))
        assert load_settings(paths).games["gr2"].stick_deadzone == 10


def test_ps4_pro_mode_reaches_only_gravity_rush_2(paths, tmp_path):
    gr2 = games.inspect(make_game(tmp_path / "CUSA03694", "CUSA03694", "01.11"))
    gr1 = games.inspect(make_game(tmp_path / "CUSA01130", "CUSA01130", "01.00"))
    s = LauncherSettings()
    assert "BB_NEO" not in runtime.env(paths, s, gr2, base={"BB_NEO": "1"})  # off by default
    s.games["gr2"].ps4_pro = True
    assert runtime.env(paths, s, gr2, base={})["BB_NEO"] == "1"
    s.games["gr1"].ps4_pro = True  # only from a hand-edited grport.json; no Pro mode in GR1
    assert "BB_NEO" not in runtime.env(paths, s, gr1, base={})
    save_settings(paths, s)
    assert load_settings(paths).games["gr2"].ps4_pro is True
    paths.settings_json.write_text(json.dumps({"games": {"gr2": {"ps4_pro": "yes"}}}))
    assert load_settings(paths).games["gr2"].ps4_pro is False


def test_autoplay_key():
    from grport.__main__ import autoplay_key
    assert autoplay_key([]) is None
    assert autoplay_key(["--gr1"]) == "gr1"
    assert autoplay_key(["-GR2"]) == "gr2"
    assert autoplay_key(["/gr2"]) == "gr2"
    assert autoplay_key(["--play", "gr1"]) == "gr1"
    assert autoplay_key(["--play", "x"]) is None


def test_resolution_patch_extra_dmem(tmp_path):
    from grport import patches
    xml = tmp_path / "p.xml"
    xml.write_text('<Patch><Metadata Name="Resolution 3840x2160 (2160p, 16:9) (READ NOTES)" '
                   'AppVer="01.11" Note="3840x2160. Needs Additional DMem Allocation 128 '
                   '(extra_dmem_in_mbytes)."><PatchList/></Metadata>'
                   '<Metadata Name="16:10 1920x1200" AppVer="01.11" Note="1920x1200, 16:10.">'
                   '<PatchList/></Metadata></Patch>', encoding="utf-8")
    assert patches.extra_dmem_mb(xml, "Resolution 3840x2160", "01.11") == 128
    assert patches.extra_dmem_mb(xml, "16:10 1920x1200", "01.11") == 0
    assert patches.extra_dmem_mb(xml, "", "01.11") == 0
    assert patches.extra_dmem_mb(tmp_path / "missing.xml", "Resolution 3840x2160", "01.11") == 0


def test_version_problem_names_the_needed_update():
    """#17: Gravity Rush 2 v01.00 got no patches (30 FPS, 1080p) without a word."""
    from grport import patches
    gr2, gr1 = games.GAMES["gr2"], games.GAMES["gr1"]
    old = games.GameFolder(Path("x"), gr2, "CUSA04943", "Europe", "01.00", "")
    problem = patches.version_problem(old)
    assert "01.11" in problem and "60 FPS" in problem
    assert patches.version_problem(games.GameFolder(Path("x"), gr2, "CUSA04934", "Europe", "01.11", "")) == ""
    assert patches.version_problem(games.GameFolder(Path("x"), gr1, "CUSA01113", "Europe", "01.00", "")) == ""
    assert patches.version_problem(games.GameFolder(Path("x"), gr2, "CUSA03694", "USA", "", "")) == ""


def test_linux_desktop_entry_and_packaged_paths(tmp_path, monkeypatch):
    """Linux AppImage: .desktop shortcuts start $APPIMAGE; the runtime comes from the package."""
    from grport import shortcuts
    paths = AppPaths.for_root(tmp_path / "home")
    paths.root.mkdir()
    monkeypatch.delenv("APPIMAGE", raising=False)
    with pytest.raises(OSError):
        shortcuts._create_desktop_entry(paths, tmp_path / "apps")
    monkeypatch.setenv("APPIMAGE", "/games/GRport-x86_64.AppImage")
    entry = shortcuts._create_desktop_entry(paths, tmp_path / "apps").read_text(encoding="utf-8")
    assert entry.startswith("[Desktop Entry]\n")
    assert 'Exec="/games/GRport-x86_64.AppImage"\n' in entry
    assert (paths.root / "grport.png").is_file()
    monkeypatch.setenv("GRPORT_RUNTIME_EXE", "/pkg/bin/GRport-runtime")
    monkeypatch.setenv("GRPORT_PREPARE_EXE", "/pkg/bin/gr-prepare")
    assert runtime.exe(paths) == Path("/pkg/bin/GRport-runtime")
    assert runtime.prepare_exe(paths) == Path("/pkg/bin/gr-prepare")
    monkeypatch.setenv("GRPORT_HOME", str(tmp_path / "data"))
    assert AppPaths.current().root == tmp_path / "data"
