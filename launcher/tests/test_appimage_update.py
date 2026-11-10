# SPDX-License-Identifier: GPL-2.0-or-later
"""Linux: the AppImage finds its own release file, replaces itself and restarts cleanly."""
import hashlib
import os

import pytest

from grport import updater
from tests.test_release import _release


def test_newest_appimage_skips_releases_without_one():
    releases = [_release("v0.3.0", "GRport-0.3.0-windows.zip"),  # AppImage not uploaded yet
                _release("v0.2.9", "GRport-0.2.9-windows.zip", updater.APPIMAGE_ASSET)]
    assert updater.newest(releases, "0.2.8", fsr=False, appimage=True).version == "0.2.9"
    assert updater.newest(releases, "0.2.9", fsr=False, appimage=True) is None
    assert updater.newest(releases, "0.2.9", fsr=False).version == "0.3.0"  # Windows unchanged


def test_install_appimage_replaces_the_file(tmp_path):
    new = b"\x7fELF new appimage" * 100
    src = tmp_path / "server" / updater.APPIMAGE_ASSET
    src.parent.mkdir()
    src.write_bytes(new)
    target = tmp_path / "Games" / "GRport-x86_64.AppImage"
    target.parent.mkdir()
    target.write_bytes(b"old")
    seen = []
    release = updater.Release("0.3.1", src.as_uri(), len(new), hashlib.sha256(new).hexdigest(), "")
    assert updater.install_appimage(release, target, lambda d, t: seen.append((d, t))) == target
    assert target.read_bytes() == new and seen[-1] == (len(new), len(new))
    assert sorted(p.name for p in target.parent.iterdir()) == ["GRport-x86_64.AppImage"]
    if os.name != "nt":
        assert os.access(target, os.X_OK)


def test_install_appimage_keeps_the_old_file_on_a_bad_download(tmp_path):
    src = tmp_path / "bad.AppImage"
    src.write_bytes(b"corrupted")
    target = tmp_path / "GRport-x86_64.AppImage"
    target.write_bytes(b"old")
    release = updater.Release("0.3.1", src.as_uri(), 9, "00" * 32, "")
    with pytest.raises(ValueError):
        updater.install_appimage(release, target)
    assert target.read_bytes() == b"old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["GRport-x86_64.AppImage", "bad.AppImage"]


def test_appimage_env_is_the_players_own():
    mount = "/tmp/.mount_GRportAb12"
    running = {
        "HOME": "/home/deck", "DISPLAY": ":0", "LC_ALL": "C.UTF-8", "APPDIR": mount,
        "APPIMAGE": "/home/deck/GRport-x86_64.AppImage", "GRPORT_HOME": "/home/deck/.local/share/GRport",
        "GRPORT_RUNTIME_EXE": mount + "/bin/GRport-runtime", "PYTHONPATH": "/nix/store/abc-launcher",
        "SSL_CERT_FILE": "/nix/store/xyz-cacert/ca-bundle.crt", "FONTCONFIG_FILE": "/nix/store/f/fonts.conf",
        "PATH": "/nix/store/c-coreutils/bin:/usr/bin:" + mount + "/usr/bin:/bin",
        "XDG_DATA_DIRS": "/nix/store/x/share", "SteamAppId": "0",
        "BB_HOST_LD_PRELOAD": "/home/deck/.steam/gameoverlayrenderer.so", "BB_HOST_GTK_PATH": "",
        "DISABLE_VK_LAYER_VALVE_steam_overlay_1": "1",
    }
    env = updater.appimage_env(running)
    assert env == {"HOME": "/home/deck", "DISPLAY": ":0", "LC_ALL": "C.UTF-8",
                   "GRPORT_HOME": "/home/deck/.local/share/GRport", "PATH": "/usr/bin:/bin",
                   "SteamAppId": "0", "LD_PRELOAD": "/home/deck/.steam/gameoverlayrenderer.so"}
