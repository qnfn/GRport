"""PS5 dumps of PS4 discs hold plain (decrypted) ELF modules instead of SELF files."""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prepare"))
import prepare  # noqa: E402


def make_elf(code=b"\xc3" * 16):
    """A minimal x86-64 ELF with one PT_LOAD segment holding `code`."""
    ph_off, code_off = 64, 64 + 56
    header = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + bytes(9), 2, 62, 1,
                         0, ph_off, 0, 0, 64, 56, 1, 64, 0, 0)
    ph = struct.pack("<IIQQQQQQ", 1, 5, code_off, 0, 0, len(code), len(code), 0x4000)
    return header + ph + code


def make_self(elf):
    """Wrap a plain ELF the way a PS4 SELF does (one plaintext segment)."""
    header, ph = prepare.elf_header(elf)
    p = ph[0]
    head = elf[:header[5] + 56]
    body_off = 32 + 32 + len(head)
    segment = struct.pack("<QQQQ", 0x800 | (0 << 20), body_off, p["filesz"], p["filesz"])
    self_header = b"O\x15=\x1d" + bytes(20) + struct.pack("<H", 1) + bytes(6)
    return self_header + segment + head + elf[p["offset"]:p["offset"] + p["filesz"]]


def test_plain_elf_matches_self():
    elf = make_elf()
    from_elf = prepare.parse_self(elf)
    from_self = prepare.parse_self(make_self(elf))
    assert from_elf[0] == from_self[0]
    assert from_elf[2] == from_self[2]
    assert from_elf[3] == [] and from_elf[4] == []


def test_cut_short_elf_is_named():
    with pytest.raises(ValueError, match="cut short"):
        prepare.parse_self(make_elf()[:-4])


def test_other_files_get_a_clear_message():
    with pytest.raises(ValueError, match="encrypted"):
        prepare.parse_self(b"\x54\x14\xf5\xee" + bytes(200))
