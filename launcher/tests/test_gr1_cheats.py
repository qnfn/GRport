import struct
import sys
from pathlib import Path

import pytest

from grport import games, patches
from grport.paths import AppPaths
from grport.settings import LauncherSettings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prepare"))
from gr_prepare import validate_gr1_cheats


def test_gr1_cheats_require_expected_instructions_and_no_download(tmp_path, monkeypatch):
    paths = AppPaths.for_root(tmp_path)
    settings = LauncherSettings()
    settings.games["gr1"].extras = list(patches.GR1_CHEATS)
    info = games.GameFolder(tmp_path, games.GR1, "CUSA01113", "Europe", "01.00")
    monkeypatch.setattr(patches, "download", lambda *args: pytest.fail("unexpected download"))
    patch = patches.write(paths, settings, info)
    assert patch and struct.unpack_from("<8sQQ", patch.read_bytes())[2] == 4

    image = bytearray(0x2E2041)
    for offset, original in ((0x2D2F44, "895720"), (0x08169A, "c5fa1183780a0000"),
                             (0x104777, "2917"), (0x2E203E, "412b07")):
        data = bytes.fromhex(original)
        image[offset:offset + len(data)] = data
    boot = tmp_path / "boot.bin"
    boot.write_bytes(b"BBPROBE2" + struct.pack("<Q", len(image)) + image)
    validate_gr1_cheats(boot, patch)
    image[0x08169A] ^= 1
    boot.write_bytes(b"BBPROBE2" + struct.pack("<Q", len(image)) + image)
    with pytest.raises(ValueError, match="does not match"):
        validate_gr1_cheats(boot, patch)


def test_gr1_cheats_are_offered_to_other_regions(tmp_path):
    """Prepare's instruction check decides (#42): the launcher writes the same cheats for a US
    or Asian v1.00 game as for the European one."""
    settings = LauncherSettings()
    settings.games["gr1"].extras = ["GR1 gravity"]
    blobs = []
    for serial, region in (("CUSA01113", "Europe"), ("CUSA01130", "USA"), ("CUSA01112", "Asia")):
        root = tmp_path / serial
        info = games.GameFolder(root, games.GR1, serial, region, "01.00")
        blobs.append(patches.write(AppPaths.for_root(root), settings, info).read_bytes())
    assert blobs[0] == blobs[1] == blobs[2]
