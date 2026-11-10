# SPDX-License-Identifier: GPL-2.0-or-later
"""The generated resolution patches equal the author's own at his 16:10 sizes."""
from pathlib import Path

import pytest

from grport import respatch

# The author's patch files are not part of GRport: copy them into tests/data (gitignored) to
# run these checks.
PATCHES = Path(__file__).resolve().parent / "data"
GAMES = (("GravityDaze2-Orbis.xml", "01.11"), ("GravityRushRemastered-Orbis.xml", "01.00"))
pytestmark = pytest.mark.skipif(not all((PATCHES / n).is_file() for n, _ in GAMES),
                                reason="the author's patch files are not in tests/data")


@pytest.mark.parametrize("name,version", GAMES)
def test_generated_sizes_match_the_authors(name, version):
    root = respatch.load(PATCHES / name)
    for w, h in ((968, 604), (1600, 1000), (3840, 2400)):
        want = dict(respatch._lines(root, f"16:10 {w}x{h}", version))
        got = dict(respatch.generate(root, version, w, h, 1.6))
        assert got == want, (name, w, h)


def test_parse_and_limits():
    assert respatch.parse("GRport 4:3 1440x1080") == (1440, 1080, 4 / 3)
    assert respatch.parse("Resolution 3840x2160") is None
    root = respatch.load(PATCHES / GAMES[0][0])
    with pytest.raises(ValueError):
        respatch.generate(root, "01.11", 1366, 768, 16 / 9)
