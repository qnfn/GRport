# SPDX-License-Identifier: GPL-2.0-or-later
"""Trophy file icons, the earned list and the names handed to the runtime's pop-up."""
import json
import struct

from grport import trophies

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 24


def make_trp(path, names):
    entries, blobs, offset = [], b"", 0x60 + 0x40 * len(names)
    for name in names:
        data = PNG if name.endswith(".PNG") else b"\xa9encrypted"
        entries.append(name.encode().ljust(32, b"\0") + struct.pack(">QQII", offset + len(blobs),
                                                                      len(data), 0, 0) + b"\0" * 8)
        blobs += data
    head = struct.pack(">IIQIII", trophies.TRP_MAGIC, 3, offset + len(blobs), len(names), 0x40, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head.ljust(0x60, b"\0") + b"".join(entries) + blobs)


def test_icons_earned_and_names(tmp_path):
    game = tmp_path / "CUSA01113"
    make_trp(trophies.trp_path(game), ["TROPCONF.ESFM", "ICON0.PNG", "TROP000.PNG", "TROP001.PNG",
                                       "TROP002.PNG", "GR001.PNG"])
    trp = trophies.trp_path(game)
    assert trophies.icon_ids(trp) == [0, 1, 2]
    icons = trophies.extract_icons(trp, tmp_path / "icons")
    assert (icons / "trop002.png").read_bytes() == PNG and not (icons / "tropconf.esfm").exists()

    user = tmp_path / "user"
    (user / "trophies").mkdir(parents=True)
    (user / "trophies" / "1.txt").write_text("1 2000\n2 3000\n")
    (user / "trophies.log").write_text("1 1500\nbad line\n99999 5\n2 4000\n")
    assert trophies.earned(user) == {1: 1500, 2: 3000}  # earliest time wins

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "trophies-gr1.json").write_text(json.dumps([
        {"id": 0, "name": "Queen", "detail": "All", "grade": "Platinum"},
        {"id": 2, "name": "Flyer", "detail": "Fly", "grade": "bronze"}]))
    items = trophies.listing(trp, assets, "gr1", user)
    assert [(t.id, t.name, t.grade, t.earned) for t in items] == [
        (0, "Queen", "platinum", 0), (1, "Trophy 1", "", 1500), (2, "Flyer", "bronze", 3000)]
    trophies.write_names(assets, "gr1", user)
    assert (user / "trophy-names.txt").read_text() == "0\tplatinum\tQueen\n2\tbronze\tFlyer\n"


def test_no_trophy_file_or_list(tmp_path):
    assert trophies.trp_entries(tmp_path / "missing.trp") == {}
    (tmp_path / "bad.trp").write_bytes(b"nope" * 40)
    assert trophies.icon_ids(tmp_path / "bad.trp") == []
    trophies.write_names(tmp_path, "gr2", tmp_path / "user")  # no list: nothing written
    assert not (tmp_path / "user" / "trophy-names.txt").exists()
