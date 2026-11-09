# SPDX-License-Identifier: GPL-2.0-or-later
"""Updates from GitHub releases and the Gravity Rush 2 patch compiler."""
import struct
from pathlib import Path

from grport import patches, updater


def _release(tag, *names, draft=False):
    return {"tag_name": tag, "draft": draft, "prerelease": False, "html_url": "https://x",
            "assets": [{"name": n, "browser_download_url": f"https://dl/{n}", "size": 5,
                        "digest": "sha256:" + "ab" * 32} for n in names]}


def test_newest_picks_own_edition_above_current():
    releases = [_release("v0.1.0", "GRport-0.1.0-windows.zip", "GRport-0.1.0-windows-fsr.zip"),
                _release("v0.1.2", "GRport-0.1.2-windows.zip"),
                _release("v0.1.1", "GRport-0.1.1-windows.zip", "GRport-0.1.1-windows-fsr.zip"),
                _release("v0.2.0", "GRport-0.2.0-windows-fsr.zip", draft=True)]
    assert updater.newest(releases, "0.1.0", fsr=False).version == "0.1.2"
    assert updater.newest(releases, "0.1.0", fsr=True).version == "0.1.1"
    assert updater.newest(releases, "0.1.2", fsr=False) is None


XML = """<Patch>
<Metadata Name="30 fps Crash fix (GNF readiness check)" AppVer="01.11"><PatchList>
  <Line Type="bytes" Address="0x00400010" Value="c3"/></PatchList></Metadata>
<Metadata Name="60fps v4.8 (READ NOTES)" AppVer="01.11"><PatchList>
  <Line Type="bytes" Address="0x00401000" Value="9090"/></PatchList></Metadata>
<Metadata Name="60fps v4.8 (READ NOTES)" AppVer="01.00"><PatchList>
  <Line Type="bytes" Address="0x00402000" Value="cc"/></PatchList></Metadata>
</Patch>"""


def test_patches_compile_by_prefix_and_version(tmp_path):
    xml = tmp_path / "p.xml"
    xml.write_text(XML, encoding="utf-8")
    blob = patches.compile_patches(xml, patches.wanted(60))
    magic, base, count = struct.unpack_from("<8sQQ", blob, 0)
    assert (magic, base, count) == (b"BBPATCH2", 0x400000, 2)
    # GoldHEN addresses are image offsets + 0x400000; the 01.00 patch is not used.
    offset, length = struct.unpack_from("<QQ", blob, 24)
    assert (offset, length) == (0x1000, 2)
    assert patches.wanted(30) == [patches.CRASH_FIX]


def test_patch_line_types(tmp_path):
    # Unlock All DLC writes its DLC names as utf8 lines; the debug patches use bytes32.
    xml = tmp_path / "p.xml"
    xml.write_text("""<Patch><Metadata Name="Unlock All DLC" AppVer="01.11"><PatchList>
  <Line Type="utf8" Address="0x00430a63" Value="CROW"/>
  <Line Type="bytes32" Address="0x00400100" Value="0x3f000000"/>
  <Line Type="bytes" Address="0x00400200" Value="e9f840f900"/></PatchList></Metadata>
</Patch>""", encoding="utf-8")
    blob = patches.compile_patches(xml, ["Unlock All DLC"])
    assert struct.unpack_from("<8sQQ", blob, 0)[2] == 3
    pos, writes = 24, []
    for _ in range(3):
        offset, length = struct.unpack_from("<QQ", blob, pos)
        writes.append((offset, blob[pos + 16:pos + 16 + length]))
        pos += 16 + length
    assert writes == [(0x30a63, b"CROW\0"), (0x100, b"\x00\x00\x00\x3f"),
                      (0x200, bytes.fromhex("e9f840f900"))]


def _bbpatch(writes):
    blob = struct.pack("<8sQQ", b"BBPATCH2", patches.GOLDHEN_BASE, len(writes))
    for offset, data in writes:
        blob += struct.pack("<QQ", offset, len(data)) + data
    return blob


def test_patch_mismatch_ignores_calls_in_new_code(tmp_path):
    # Unlock All DLC writes six calls into a code cave next to its other writes: they are new
    # code, not the game's call sites, and must not make prepare call the patches mismatched.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prepare"))
    import gr_prepare
    image = bytearray(0x1000)
    image[0x100] = image[0x200] = 0xE8  # the game's calls
    boot = tmp_path / "boot.bin"
    boot.write_bytes(struct.pack("<QQ", 0, len(image)) + bytes(image))
    call = bytes.fromhex("e800000000")
    cave = [(0x800, bytes.fromhex("488d3d00000000")), (0x807, b"\x31\xf6"), (0x809, call),
            (0x80e, bytes.fromhex("488d3d00000000")), (0x815, b"\x31\xf6"), (0x817, call)]
    patch = tmp_path / "p.bin"
    patch.write_bytes(_bbpatch([(0x100, call), (0x200, call)] + cave))
    assert gr_prepare.patch_mismatches(boot, patch) == (2, 0)
    patch.write_bytes(_bbpatch([(0x110, call), (0x210, call)] + cave))  # another build
    assert gr_prepare.patch_mismatches(boot, patch) == (2, 2)


def test_patch_mismatch_is_kept_only_for_the_same_patches(tmp_path):
    # A mismatch found with one set of patches does not disable another set (or the same set
    # after an update) for good.
    from types import SimpleNamespace
    eboot = tmp_path / "eboot.bin"
    eboot.write_bytes(b"x")
    info = SimpleNamespace(eboot=eboot, game=SimpleNamespace(key="gr2"))
    paths = SimpleNamespace(root=tmp_path)
    patches.patch_file(paths, "gr2").parent.mkdir(parents=True)
    patches.patch_file(paths, "gr2").write_bytes(b"one")
    patches.mark_mismatch(paths, info)
    assert not patches.patch_file(paths, "gr2").exists()
    assert patches.mismatched(paths, info, b"one")
    assert not patches.mismatched(paths, info, b"two")
