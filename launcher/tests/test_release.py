# SPDX-License-Identifier: GPL-2.0-or-later
"""Updates from GitHub releases and the Gravity Rush 2 patch compiler."""
import struct

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
