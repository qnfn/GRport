# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import pytest
from grport import steam, steam_vdf, shortcuts


def test_two_games_sharing_executable_stay_separate_and_preserve_player_data(tmp_path):
    path = tmp_path / "shortcuts.vdf"
    steam.write_shortcut(path, "Gravity Rush", "/games/GRport.AppImage", "--gr1")
    original = steam_vdf.load(path.read_bytes())
    original["shortcuts"]["0"].update({"tags": {"0": "Favorites"}, "LastPlayTime": 123,
                                        "custom": steam_vdf.Raw(7, bytes(range(8)))})
    path.write_bytes(steam_vdf.dump(original))
    before = path.read_bytes()
    steam.write_shortcut(path, "Gravity Rush 2", "/games/GRport.AppImage", "--gr2")
    assert path.with_suffix(".vdf.bak").read_bytes() == before
    steam.write_shortcut(path, "Gravity Rush Remastered", "/games/GRport.AppImage", "--gr1")
    entries = steam_vdf.load(path.read_bytes())["shortcuts"]
    assert len(entries) == 2
    assert entries["0"]["tags"] == {"0": "Favorites"}
    assert entries["0"]["LastPlayTime"] == 123
    assert entries["0"]["custom"] == steam_vdf.Raw(7, bytes(range(8)))
    assert entries["0"]["LaunchOptions"] == "--gr1"
    assert entries["1"]["LaunchOptions"] == "--gr2"
    assert entries["0"]["appid"] != entries["1"]["appid"]


def test_bad_vdf_is_never_overwritten(tmp_path):
    path = tmp_path / "shortcuts.vdf"
    path.write_bytes(b"not a valid Steam file")
    with pytest.raises(ValueError):
        steam.write_shortcut(path, "GR1", "GRport", "--gr1")
    assert path.read_bytes() == b"not a valid Steam file"


def test_account_selection_uses_most_recent_login(tmp_path):
    for account in (123, 456):
        (tmp_path / "userdata" / str(account)).mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/loginusers.vdf").write_text(
        '\n"users" { "76561197960266184" { "MostRecent" "1" } }')
    assert steam.current_config(tmp_path) == tmp_path / "userdata/456/config"


def test_account_selection_uses_autologin_when_most_recent_is_missing(tmp_path):
    for account in (123, 456):
        (tmp_path / "userdata" / str(account)).mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/loginusers.vdf").write_text('''
        "users" {
            "76561197960265851" { "AccountName" "old" "AutoLogin" "0" "timestamp" "100" }
            "76561197960266184" { "AccountName" "current" "AutoLogin" "1" "timestamp" "200" }
        }
    ''')
    assert steam.current_config(tmp_path) == tmp_path / "userdata/456/config"


def test_account_selection_falls_back_to_latest_timestamp(tmp_path):
    for account in (123, 456):
        (tmp_path / "userdata" / str(account)).mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/loginusers.vdf").write_text('''
        "users" {
            "76561197960265851" { "AccountName" "old" "timestamp" "100" }
            "76561197960266184" { "AccountName" "current" "Timestamp" "200" }
        }
    ''')
    assert steam.current_config(tmp_path) == tmp_path / "userdata/456/config"


def test_ambiguous_account_does_not_guess(tmp_path):
    for account in (123, 456):
        (tmp_path / "userdata" / str(account)).mkdir(parents=True)
    with pytest.raises(OSError, match="Sign in"):
        steam.current_config(tmp_path)


def test_game_desktop_entry_launches_selected_game(tmp_path, monkeypatch):
    from grport.paths import AppPaths
    paths = AppPaths.for_root(tmp_path / "data")
    paths.root.mkdir()
    monkeypatch.setenv("APPIMAGE", "/games/Gravity Rush/GRport.AppImage")
    entry1 = shortcuts._create_desktop_entry(paths, tmp_path / "apps", "gr1")
    entry2 = shortcuts._create_desktop_entry(paths, tmp_path / "apps", "gr2")
    assert entry1 != entry2
    assert 'Exec="/games/Gravity Rush/GRport.AppImage" --gr1' in entry1.read_text()
    assert 'Exec="/games/Gravity Rush/GRport.AppImage" --gr2' in entry2.read_text()


def test_running_steam_prevents_writes(tmp_path, monkeypatch):
    from grport.paths import AppPaths
    paths = AppPaths.for_root(tmp_path)
    (tmp_path / "GRport.exe").write_bytes(b"test")
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(steam, "is_running", lambda: True)
    with pytest.raises(OSError, match="Exit Steam"):
        steam.add_game(paths, "gr1")
    assert not (tmp_path / "shortcuts.vdf").exists()
