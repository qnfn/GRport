"""Prepare a Gravity Rush game for GRport's runtime: the eboot image, the game's own modules
linked, the content profile and the imports respelled for the runtime (GRport's copy of
DCport's prepare steps). Nothing from the game ends up anywhere but <data dir>.

Usage: gr_prepare <game dir> <data dir> <runtime exe> [patches.bin]

patches.bin (BBPATCH2, the launcher's frame-rate patch): its writes keep their bytes (no
red-zone rewrite there) and the modules start 8 MiB after the eboot (the patch's code cave).

The modules are the .prx files in the game's sce_module folder, libc first. When done,
<data dir>/source.txt names the eboot and runtime it was made from (the launcher prepares
again when either changes).
"""
import hashlib
import struct
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content_profile  # noqa: E402
import link_modules  # noqa: E402
import prepare  # noqa: E402
import respell  # noqa: E402

KEEP = {"boot-linked.bin", "content.bin", "source.txt", "analysis.json", "link.json",
        "prepare.log"}  # the launcher writes our output there


def modules(game: Path) -> list:
    found = sorted(p.name for p in (game / "sce_module").glob("*.prx"))
    if "libc.prx" in found:
        found.remove("libc.prx")
        found.insert(0, "libc.prx")
    return found


def stamp(game: Path, runtime: Path) -> str:
    def describe(p: Path) -> str:
        st = p.stat()
        return f"{p} {st.st_size} {st.st_mtime_ns}"
    return describe(game / "eboot.bin") + "\n" + describe(runtime) + "\n"


def patched_offsets(path: Path) -> list:
    """Every eboot byte a BBPATCH2 file writes."""
    raw = path.read_bytes()
    magic, _base, count = struct.unpack_from("<8sQQ", raw, 0)
    if magic != b"BBPATCH2":
        raise ValueError(f"{path} is not a BBPATCH2 file")
    pos, out = 24, []
    for _ in range(count):
        offset, length = struct.unpack_from("<QQ", raw, pos)
        out.extend(range(offset, offset + length))
        pos += 16 + length
    return out


def main(argv) -> int:
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    game, data, runtime = (Path(a) for a in argv[:3])
    patch = Path(argv[3]) if len(argv) == 4 else None
    for name in ("eboot.bin", "sce_sys/param.sfo"):
        if not (game / name).is_file():
            print(f"Missing {name} in {game}: choose the game's folder")
            return 1
    mods = modules(game)
    print("Modules: " + ", ".join(mods))
    data.mkdir(parents=True, exist_ok=True)
    (data / "source.txt").unlink(missing_ok=True)
    prepare.prepare(game, data)
    if patch:
        patched = patched_offsets(patch)
        print(f"Patches: {len(patched)} bytes kept")
        link_modules.link(game, data, mods, patched)
    else:
        link_modules.link(game, data, mods, [])
    content_profile.prepare(game, data, "full")
    respell.respell(data / "boot-linked.bin", runtime)
    for f in data.iterdir():
        if f.is_file() and f.name not in KEEP:
            try:
                f.unlink()
            except OSError:
                pass  # a leftover intermediate file does no harm
    (data / "source.txt").write_text(stamp(game, runtime) + ("patches " + hashlib.sha1(patch.read_bytes()).hexdigest()[:16] + "\n" if patch else ""),
                                     encoding="utf-8")
    print("Game files prepared.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:  # the launcher shows the log
        traceback.print_exc()
        sys.exit(1)
