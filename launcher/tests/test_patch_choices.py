import struct
import tempfile
import unittest
from pathlib import Path

from grport import patches

XML = """<Patch>
<Metadata Name="Shifter 1.0 costume -&gt; Lisa (later outfit)" AppVer="01.11">
 <PatchList><Line Type="bytes" Address="0x00400010" Value="BB"/></PatchList></Metadata>
<Metadata Name="Shifter 1.0 costume -&gt; Lisa" AppVer="01.11">
 <PatchList><Line Type="bytes" Address="0x00400010" Value="AA"/></PatchList></Metadata>
</Patch>"""


class PatchChoices(unittest.TestCase):
    def test_one_costume_at_most(self):
        a, b = patches.COSTUMES["gr2"][:2]
        names = patches.wanted(30, "gr2", [b, a])
        self.assertEqual([n for n in names if n in patches.COSTUMES["gr2"]], [a])

    def test_performance_patches_are_optional(self):
        names = patches.wanted(30, "gr2", ["Performance: RGBA8 HDR render targets"])
        self.assertIn("Performance: RGBA8 HDR render targets", names)
        self.assertNotIn("Performance: RGBA8 HDR render targets", patches.wanted(30, "gr2", []))

    def test_exact_name_wins_over_longer_names(self):
        with tempfile.TemporaryDirectory() as d:
            xml = Path(d) / "p.xml"
            xml.write_text(XML, encoding="utf-8")
            blob = patches.compile_patches(xml, ["Shifter 1.0 costume -> Lisa"])
        _, _, count = struct.unpack_from("<8sQQ", blob)
        offset, size = struct.unpack_from("<QQ", blob, 24)
        self.assertEqual((count, blob[40:40 + size]), (1, b"\xAA"))

    def test_names_exist_in_the_authors_file(self):
        xml = Path(r"D:\GRport\GRport-0.3.8-test\patches\GravityDaze2-Orbis.xml")
        if not xml.is_file():
            self.skipTest("no downloaded patch file here")
        names = [p for p, *_ in patches.OPTIONAL["gr2"]] + list(patches.COSTUMES["gr2"])
        patches.compile_patches(xml, names)  # raises for a name the file lacks


if __name__ == "__main__":
    unittest.main()
