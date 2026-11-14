"""Prepare a Gravity Rush game for GRport's runtime: the eboot image, the game's own modules
linked, the content profile and the imports respelled for the runtime (GRport's copy of
DCport's prepare steps). Nothing from the game ends up anywhere but <data dir>.

Usage: gr_prepare <game dir> <data dir> <runtime exe> [patches.bin] [--update <update dir>]

--update: the game's update kept in a folder of its own (shadPS4's <game>-UPDATE); its eboot,
param.sfo and modules replace the game's. An update copied over the game needs nothing.

patches.bin (BBPATCH2, the launcher's frame-rate patch): its writes keep their bytes (no
red-zone rewrite there) and the modules start 8 MiB after the eboot (the patch's code cave).

The modules are the .prx files in the game's sce_module folder, libc first. When done,
<data dir>/source.txt names the eboot and runtime it was made from (the launcher prepares
again when either changes).
"""
import hashlib
import json
import os
import shutil
import struct
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content_profile  # noqa: E402
import cpu_compat  # noqa: E402
import link_modules  # noqa: E402
import prepare  # noqa: E402
import respell  # noqa: E402

KEEP = {"boot-linked.bin", "content.bin", "source.txt", "analysis.json", "link.json",
        "prepare.log", "legacy-cpu-plan.json"}  # the launcher writes our output there
PLAN = "legacy-cpu-plan.json"


def modules(game: Path) -> list:
    found = sorted(p.name for p in (game / "sce_module").glob("*.prx"))
    if "libc.prx" in found:
        found.remove("libc.prx")
        found.insert(0, "libc.prx")
    return found


def stamp(eboot: Path, runtime: Path) -> str:
    def describe(p: Path) -> str:
        st = p.stat()
        return f"{p} {st.st_size} {st.st_mtime_ns}"
    return describe(eboot) + "\n" + describe(runtime) + "\n"


VIEW = "game-view"


def game_view(game: Path, update: Path, data: Path) -> Path:
    """The files preparing reads (eboot, param.sfo, modules) with the update's copy first, in
    <data>/game-view: hard links where the drive allows, else copies (removed when done)."""
    view = data / VIEW
    shutil.rmtree(view, ignore_errors=True)
    mods = {p.name for folder in (game, update) for p in (folder / "sce_module").glob("*.prx")}
    for name in ["eboot.bin", "sce_sys/param.sfo"] + [f"sce_module/{m}" for m in sorted(mods)]:
        source = update / name if (update / name).is_file() else game / name
        if not source.is_file():
            continue
        target = view / name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
    return view


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


def patch_mismatches(boot: Path, patch: Path) -> "tuple[int, int]":
    """(call sites the patches write, of them not a call in this eboot). Patches made for
    another build of the game write into the middle of other code: most writes of a call have
    to land on a call (0xE8) here (some add new calls). Only a call written on its own counts:
    one that touches another write is part of new code (Unlock All DLC writes six calls into a
    code cave), not a call site of the game's."""
    raw = boot.read_bytes()
    size = struct.unpack_from("<Q", raw, 8)[0]
    image = raw[len(raw) - size:]
    blob = patch.read_bytes()
    _magic, _base, count = struct.unpack_from("<8sQQ", blob, 0)
    pos, writes = 24, []
    for _ in range(count):
        offset, length = struct.unpack_from("<QQ", blob, pos)
        writes.append((offset, blob[pos + 16:pos + 16 + length]))
        pos += 16 + length
    spans = {(offset, offset + len(data)) for offset, data in writes}

    def alone(start: int, end: int) -> bool:
        return not any(s <= end and e >= start for s, e in spans if (s, e) != (start, end))

    calls = bad = 0
    for offset, data in writes:
        if len(data) == 5 and data[0] == 0xE8 and alone(offset, offset + 5):
            calls += 1
            bad += offset >= size or image[offset] != 0xE8
    return calls, bad


def validate_gr1_cheats(boot: Path, patch: Path) -> None:
    """Reject a GR1 cheat if its target instruction differs from the tested build."""
    guards = {
        (0x2D2F44, bytes.fromhex("894f20")): bytes.fromhex("895720"),
        (0x08169A, bytes.fromhex("9090909090909090")): bytes.fromhex("c5fa1183780a0000"),
        (0x104777, bytes.fromhex("0117")): bytes.fromhex("2917"),
        (0x2E203E, bytes.fromhex("909090")): bytes.fromhex("412b07"),
    }
    raw = boot.read_bytes()
    size = struct.unpack_from("<Q", raw, 8)[0]
    image = raw[len(raw) - size:]
    blob = patch.read_bytes()
    magic, _base, count = struct.unpack_from("<8sQQ", blob, 0)
    if magic != b"BBPATCH2":
        raise ValueError("Invalid patch file")
    pos = 24
    for _ in range(count):
        offset, length = struct.unpack_from("<QQ", blob, pos)
        value = blob[pos + 16:pos + 16 + length]
        expected = guards.get((offset, value))
        if expected is not None and image[offset:offset + len(expected)] != expected:
            raise ValueError(f"GR1 cheat does not match the game's instruction at 0x{offset:x}")
        pos += 16 + length


def legacy_cpu_plan(game: Path, data: Path, mods: list) -> bool:
    """CPUs without BMI1, LZCNT or MOVBE (Intel 3rd generation and older): build the instruction
    translations from the player's own eboot and modules (a few minutes, once; kept in the data
    folder while the files are the same; no game bytes ship with GRport). The launcher reads
    legacy-cpu-plan.json in the data folder as "the game is translated" (BB_CPU_COMPAT).
    Returns False when this game can't be translated (only Gravity Rush Remastered's libc is
    the one the translations were checked against)."""
    plan = data / PLAN
    libc = link_modules.module(game / "sce_module" / "libc.prx")
    if libc["sha256"] != cpu_compat.LIBC_SHA256:
        print("Older CPU (no BMI1/LZCNT/MOVBE): this game can't be translated for it; "
              "it needs a newer CPU.", flush=True)
        plan.unlink(missing_ok=True)
        os.environ["BB_LEGACY_CPU"] = "0"
        return False
    try:
        made_for = json.loads(plan.read_text(encoding="utf-8"))["modules"]
    except (OSError, ValueError, KeyError, TypeError):
        made_for = None
    current = {"eboot.bin": link_modules.module(game / "eboot.bin")["sha256"]}
    for m in mods:
        current[m] = link_modules.module(game / "sce_module" / m)["sha256"]
    if made_for != current:
        print("Older CPU (no BMI1/LZCNT/MOVBE): building its instruction translations from your "
              "game files, once (a few minutes)...", flush=True)
        import cpu_plan
        cpu_plan.build(game, plan, mods)
    os.environ["BB_LEGACY_CPU_PLAN"] = str(plan)
    return True


def main(argv) -> int:
    argv = list(argv)
    update = None
    if "--update" in argv:
        i = argv.index("--update")
        if i + 1 >= len(argv):
            print(__doc__)
            return 2
        update = Path(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    game, data, runtime = (Path(a) for a in argv[:3])
    patch = Path(argv[3]) if len(argv) == 4 else None
    data.mkdir(parents=True, exist_ok=True)
    (data / "source.txt").unlink(missing_ok=True)
    eboot = game / "eboot.bin"
    if update is not None:
        print(f"Update: {update}")
        if (update / "eboot.bin").is_file():
            eboot = update / "eboot.bin"
        game = game_view(game, update, data)
    for name in ("eboot.bin", "sce_sys/param.sfo", "sce_module/libc.prx"):
        if not (game / name).is_file():
            print(f"Missing {name} in {game}: choose the game's folder (not only its update)")
            return 1
    mods = modules(game)
    print("Modules: " + ", ".join(mods))
    prepare.prepare(game, data)
    if not (cpu_compat.enabled() and legacy_cpu_plan(game, data, mods)):
        (data / PLAN).unlink(missing_ok=True)
    if patch:
        try:
            validate_gr1_cheats(data / "boot.bin", patch)
        except ValueError as e:
            print(f"PATCH MISMATCH: {e}")
            return 3
        calls, bad = patch_mismatches(data / "boot.bin", patch)
        if bad * 2 > calls:  # the patches also add new calls in places; most must match
            print(f"PATCH MISMATCH: {bad} of {calls} patched call sites are not calls in this "
                  "eboot: the patches are for another build of the game.")
            return 3
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
    shutil.rmtree(data / VIEW, ignore_errors=True)
    (data / "source.txt").write_text(stamp(eboot, runtime) +("patches " + hashlib.sha1(patch.read_bytes()).hexdigest()[:16] + "\n" if patch else ""),
                                     encoding="utf-8")
    print("Game files prepared.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:  # the launcher shows the log
        traceback.print_exc()
        sys.exit(1)
