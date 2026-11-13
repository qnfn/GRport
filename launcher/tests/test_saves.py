import struct
from pathlib import Path

from grport import games, saves

GR2 = games.GAMES["gr2"]


def make_sfo(path: Path, entries: dict) -> None:
    keys, values, index = b"", b"", b""
    for name, value in entries.items():
        if isinstance(value, int):
            raw, fmt = struct.pack("<I", value), 0x0404
        else:
            raw, fmt = value.encode() + b"\0", 0x0204
        index += struct.pack("<HHIII", len(keys), fmt, len(raw), len(raw), len(values))
        keys += name.encode() + b"\0"
        values += raw
    key_table = 20 + len(index)
    data_table = key_table + len(keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<4sIIII", b"\0PSF", 0x101, key_table, data_table, len(entries))
                     + index + keys + values)


def shadps4_save(home: Path, serial: str, name: str, title: str = "Auto Save") -> Path:
    folder = home / "1" / "savedata" / serial / name
    folder.mkdir(parents=True)
    (folder / f"{name}.bin").write_bytes(b"game data")
    (folder / "sce_bu_old_x").mkdir()
    make_sfo(folder / "sce_sys" / "param.sfo",
             {"MAINTITLE": title, "SAVEDATA_DIRECTORY": name, "TITLE_ID": serial,
              "SAVEDATA_LIST_PARAM": 7})
    (folder / "sce_sys" / "icon0.png").write_bytes(b"png")
    return folder


def test_param_from_sfo_layout():
    param = saves.param_from_sfo({"MAINTITLE": "Auto Save", "DETAIL": "Hekseville",
                                  "SAVEDATA_LIST_PARAM": 7})
    assert len(param) == saves.PARAM_SIZE
    assert param[:9] == b"Auto Save" and param[256:266] == b"Hekseville"
    assert struct.unpack_from("<I", param, 1280)[0] == 7


def test_import_from_shadps4_layout(tmp_path):
    home = tmp_path / "other" / "user" / "home"
    shadps4_save(home, "CUSA04934", "data0000")  # European save into the USA game
    shadps4_save(home, "CUSA03694", "system0020")
    shadps4_save(home, "CUSA01113", "data0000")  # Gravity Rush 1: not imported
    memory = home / "1" / "savedata" / "CUSA03694" / "sce_sdmemory"
    memory.mkdir()
    (memory / "memory.dat").write_bytes(b"mem")

    found = saves.scan(tmp_path / "other", GR2)
    assert sorted((s.name, s.memory) for s in found.saves) == [
        ("data0000", False), ("sce_sdmemory", True), ("system0020", False)]
    assert found.other_games == {"CUSA01113"} and not found.encrypted

    user = tmp_path / "GRport" / "user" / "gr2"
    old = saves.save_root(user, "CUSA03694") / "data0000"
    old.mkdir(parents=True)
    (old / "data0000.bin").write_bytes(b"old progress")
    backup = saves.import_saves(user, "CUSA03694", found.saves)

    root = saves.save_root(user, "CUSA03694")
    assert (root / "data0000" / "data0000.bin").read_bytes() == b"game data"
    assert sorted(p.name for p in (root / "data0000").iterdir()) == ["data0000.bin"]
    assert (root / "data0000.sce_sys" / "param.bin").read_bytes()[:9] == b"Auto Save"
    assert (root / "data0000.sce_sys" / "icon0.png").is_file()
    assert (root.parent / "CUSA03694.memory" / "memory.dat").read_bytes() == b"mem"
    assert (backup / "CUSA03694" / "data0000" / "data0000.bin").read_bytes() == b"old progress"


def test_import_from_other_grport_and_single_save(tmp_path):
    other = tmp_path / "old" / "user" / "gr2"
    root = saves.save_root(other, "CUSA03694")
    (root / "data0000").mkdir(parents=True)
    (root / "data0000" / "data0000.bin").write_bytes(b"x")
    (root / "data0000.sce_sys").mkdir()
    (root / "data0000.sce_sys" / "param.bin").write_bytes(bytes(saves.PARAM_SIZE))
    found = saves.scan(tmp_path / "old", GR2)
    assert [s.name for s in found.saves] == ["data0000"]

    one = shadps4_save(tmp_path / "apollo", "CUSA03694", "data0001")
    assert [s.name for s in saves.scan(one, GR2).saves] == ["data0001"]


def test_encrypted_ps4_backup_is_reported(tmp_path):
    folder = tmp_path / "PS4" / "SAVEDATA" / "1a2b3c" / "CUSA03694"
    folder.mkdir(parents=True)
    (folder / "sdimg_data0000").write_bytes(b"sealed")
    (folder / "data0000.bin").write_bytes(b"key")
    found = saves.scan(tmp_path, GR2)
    assert found.saves == [] and found.encrypted


def test_nothing_to_back_up(tmp_path):
    save = shadps4_save(tmp_path / "src", "CUSA03694", "data0000")
    found = saves.scan(save, GR2)
    assert saves.import_saves(tmp_path / "user", "CUSA03694", found.saves) is None
