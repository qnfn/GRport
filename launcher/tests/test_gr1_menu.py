# SPDX-License-Identifier: GPL-2.0-or-later
"""Gravity Rush Remastered's Exit to Desktop patch: text tables, archive patches, scripts."""
import struct

import pytest

from grport import gr1_menu as m


def record(text, runs, flags=b"\x01\x00"):
    return m._record(text, flags, runs)


def test_text_table_round_trip_and_lookup():
    recs = {m.fnv1a(b"conf_title"): record("Return?", [(1, 7, 1, 0)]),
            m.fnv1a(b"other"): record("e Close", [(1, 1, 1, 768), (2, 7, 1, 0)])}
    data = m.txb_build(recs)
    assert m.txb_parse(data) == recs
    assert m.fnv1a(b"conf_title") == 0x8BCE8BBE  # the game's id for this name


def test_prompt_line_gets_the_glyph_and_label_with_matching_runs():
    line = record("e Close", [(1, 1, 1, 768), (2, 7, 1, 0)])
    out = m.append_prompt(line, "D", "Exit to Desktop")
    assert m.text_of(out) == "e Close  D  Exit to Desktop"
    runs = m.runs_of(out)
    assert runs[-1][1] == len(m.text_of(out))
    assert all(a[1] + 1 == b[0] for a, b in zip(runs, runs[1:]))
    assert runs[-2][2:] == (1, 768)  # glyph and its space in the button font


def test_runs_that_do_not_cover_the_text_are_refused():
    with pytest.raises(ValueError):
        record("abc", [(1, 5, 1, 0)])


def test_scripts_must_match_or_the_patch_is_not_made():
    with pytest.raises(ValueError):
        m.edit_script(b"\xef\xbb\xbfsomething else\r\n", m.SETTINGS_EDITS)
    old, new = m.TITLE_EDITS[0]
    out = m.edit_script(b"\xef\xbb\xbf" + old.replace("\n", "\r\n").encode(), m.TITLE_EDITS)
    assert out.startswith(b"\xef\xbb\xbf") and b"\r\n" in out and b"GRPORT_QUIT_TO_DESKTOP" in out


def make_psarc(path, files, block=0x10000):
    """A small stored PSARC: manifest first, one block per entry."""
    names = list(files)
    blobs = ["\n".join(names).encode()] + [files[n] for n in names]
    count, ent = len(blobs), 30
    toc_len = 32 + count * ent + count * 2
    entries, zs, off = bytearray(), bytearray(), toc_len
    for i, b in enumerate(blobs):
        entries += b"\0" * 16 + struct.pack(">I", i) + len(b).to_bytes(5, "big") + off.to_bytes(5, "big")
        zs += (len(b) if len(b) < block else 0).to_bytes(2, "big")
        off += len(b)
    path.write_bytes(struct.pack(">4sI4sIIIII", b"PSAR", 0x10004, b"zlib", toc_len, ent, count, block, 0)
                     + bytes(entries) + bytes(zs) + b"".join(blobs))


def read_patched(base, grpo, name):
    """The entry `name` as the runtime serves the patched archive."""
    size, skip, hl, tl = struct.unpack("<QQQQ", grpo[8:40])
    head, tail = grpo[40:40 + hl], grpo[40 + hl:]
    virtual = head + base.read_bytes()[skip:] + tail
    assert len(virtual) == hl + size - skip + tl
    tmp = base.with_name("virtual.psarc")
    tmp.write_bytes(virtual)
    return m.Psarc(tmp).get(name)


def test_archive_patch_replaces_entries_and_keeps_the_others(tmp_path):
    base = tmp_path / "arc.psarc"
    make_psarc(base, {"lua/a.lua": b"old script", "txb/t.txb": b"table", "big.bin": b"x" * 70000})
    p = m.Psarc(base)
    grpo = m.overlay(p, {"lua/a.lua": b"new script, longer than before"})
    assert grpo[:8] == b"GRPOVL01"
    assert read_patched(base, grpo, "lua/a.lua") == b"new script, longer than before"
    assert read_patched(base, grpo, "txb/t.txb") == b"table"


def test_patch_is_rebuilt_only_when_the_game_file_changes(tmp_path, monkeypatch):
    archive = tmp_path / "arc.psarc"
    make_psarc(archive, {"lua/a.lua": b"x"})
    built = []
    monkeypatch.setattr(m, "replacements", lambda p: built.append(1) or {"lua/a.lua": b"y"})
    out = tmp_path / "patch"
    assert m.ensure(archive, out) == out and (out / (m.ARCHIVE + ".grpo")).is_file()
    m.ensure(archive, out)
    assert len(built) == 1
    make_psarc(archive, {"lua/a.lua": b"changed"})
    import os
    os.utime(archive, (1, 1))
    m.ensure(archive, out)
    assert len(built) == 2
