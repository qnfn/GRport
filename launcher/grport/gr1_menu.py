# SPDX-License-Identifier: GPL-2.0-or-later
"""Gravity Rush Remastered: Exit to Desktop in the game's own menus.

The game's menus are Lua scripts and its texts .txb tables inside arc/arc_0_ep_0_0.psarc. From the
player's own copy this builds an archive patch (.grpo, a few MB) that the runtime lays over the
archive (--app0-patch):

- the settings menu (Options) gets an "Exit to Desktop" prompt on R3 and the title screen a hint;
- R3 makes the runtime leave /temp0/grport_exit_desktop, which the open menu takes up and answers
  with the game's own Yes/No dialog; Yes prints GRPORT_QUIT_TO_DESKTOP and the runtime closes.

Nothing of the game is shipped: the patch is made from the player's files, in data/gr1/patch.
"""
import os
import struct
import zlib
from pathlib import Path

ARCHIVE = "arc/arc_0_ep_0_0.psarc"
VERSION = "1"  # raise when the scripts or texts below change: the patch is rebuilt

# --- PSARC ---------------------------------------------------------------------------------


class Psarc:
    """Reads a PSARC (big-endian header, MD5 + block index + 40-bit size/offset entries)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        with open(path, "rb") as f:
            (magic, _, self.comp, self.toc_len, self.ent_size, count, self.block,
             _) = struct.unpack(">4sI4sIIIII", f.read(32))
            if magic != b"PSAR":
                raise ValueError(f"{path.name} is not a PSARC archive")
            self.toc = f.read(self.toc_len - 32)
        self.entries = []
        for i in range(count):
            e = self.toc[i * self.ent_size:(i + 1) * self.ent_size]
            self.entries.append((struct.unpack(">I", e[16:20])[0], int.from_bytes(e[20:25], "big"),
                                 int.from_bytes(e[25:30], "big")))
        self.width = 2 if self.block <= 0x10000 else 3 if self.block <= 0x1000000 else 4
        rest = self.toc[count * self.ent_size:]
        self.zsizes = [int.from_bytes(rest[i:i + self.width], "big")
                       for i in range(0, len(rest) - self.width + 1, self.width)]
        names = self.read(0).decode("utf-8", "replace").replace("\r", "").split("\n")
        self.names = {n.lower().lstrip("/"): i + 1 for i, n in enumerate(names) if n}

    def read(self, i: int) -> bytes:
        idx, size, off = self.entries[i]
        out = bytearray()
        with open(self.path, "rb") as f:
            f.seek(off)
            while len(out) < size:
                z = self.zsizes[idx]
                idx += 1
                chunk = f.read(z if z else self.block)
                want = min(self.block, size - len(out))
                if z == 0 or len(chunk) == want:
                    out += chunk
                elif self.comp == b"zlib" or chunk[:1] == b"\x78":
                    out += zlib.decompress(chunk)
                else:
                    import lzma
                    out += lzma.decompress(chunk)
        return bytes(out)

    def get(self, name: str) -> bytes:
        return self.read(self.names[name.lower()])


def overlay(p: Psarc, repl: dict) -> bytes:
    """The runtime's archive patch for `p` with the entries in `repl` replaced (stored, appended):
    'GRPOVL01', base size, base skip, head size, tail size (u64 LE), head, tail."""
    zs = list(p.zsizes)
    tail = bytearray()
    new = {}
    for name, data in repl.items():
        i = p.names[name.lower()]
        first = len(zs)
        for o in range(0, len(data), p.block):
            chunk = data[o:o + p.block]
            zs.append(0 if len(chunk) == p.block else len(chunk))
        new[i] = (first, len(data), len(tail))
        tail += data
    count = len(p.entries)
    head_len = 32 + count * p.ent_size + len(zs) * p.width
    delta = head_len - p.toc_len
    base_size = p.path.stat().st_size
    with open(p.path, "rb") as f:
        raw_header = f.read(32)
    head = bytearray(raw_header[:12] + struct.pack(">I", head_len) + raw_header[16:])
    for i, (idx, size, off) in enumerate(p.entries):
        raw = p.toc[i * p.ent_size:(i + 1) * p.ent_size]
        if i in new:
            idx, size, at = new[i]
            off = base_size + delta + at
        else:
            off += delta
        head += raw[:16] + struct.pack(">I", idx) + size.to_bytes(5, "big") + off.to_bytes(5, "big") + raw[30:]
    for z in zs:
        head += z.to_bytes(p.width, "big")
    return (b"GRPOVL01" + struct.pack("<QQQQ", base_size, p.toc_len, len(head), len(tail)) +
            bytes(head) + bytes(tail))

# --- .txb text tables ----------------------------------------------------------------------
# 'txbL', version 2, size, count, sorted FNV-1a ids of the names, offsets from the end of the
# tables; records: u16 characters, u16 bytes, u16 runs, 2 flag bytes (the last one aligns
# captions), UTF-8 text NUL-padded to 4, runs of (u16 first, u16 last, u32 style), 1-based.


def fnv1a(name: bytes) -> int:
    h = 0x811C9DC5
    for c in name:
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return h


def txb_parse(d: bytes) -> dict:
    magic, ver, _, n = struct.unpack("<4sIII", d[:16])
    if magic != b"txbL" or ver != 2:
        raise ValueError("not a version 2 text table")
    ids = struct.unpack("<%dI" % n, d[16:16 + 4 * n])
    offs = struct.unpack("<%dI" % n, d[16 + 4 * n:16 + 8 * n])
    base = 16 + 8 * n
    order = sorted(range(n), key=lambda i: offs[i])
    records = {}
    for k, i in enumerate(order):
        end = offs[order[k + 1]] if k + 1 < n else len(d) - base
        records[ids[i]] = d[base + offs[i]:base + end]
    return records


def txb_build(records: dict) -> bytes:
    ids = sorted(records)
    blob, offs = bytearray(), []
    for i in ids:
        offs.append(len(blob))
        blob += records[i]
    n = len(ids)
    return (struct.pack("<4sIII", b"txbL", 2, 16 + 8 * n + len(blob), n) +
            struct.pack("<%dI" % n, *ids) + struct.pack("<%dI" % n, *offs) + bytes(blob))


def text_of(rec: bytes) -> str:
    return rec[8:8 + struct.unpack("<H", rec[2:4])[0]].decode("utf-8")


def runs_of(rec: bytes) -> list:
    nb, n = struct.unpack("<HH", rec[2:6])
    at = 8 + nb + 1
    at += -at % 4
    return [struct.unpack("<HHHH", rec[at + 8 * i:at + 8 * i + 8]) for i in range(n)]


def _record(text: str, flags: bytes, runs: list) -> bytes:
    if runs[-1][1] != len(text) or any(a[1] + 1 != b[0] for a, b in zip(runs, runs[1:])):
        raise ValueError("text runs must cover the text exactly")  # the game crashes otherwise
    b = text.encode("utf-8")
    body = b + b"\0"
    body += b"\0" * (-len(body) % 4)
    return (struct.pack("<HHH", len(text), len(b), len(runs)) + flags + body +
            b"".join(struct.pack("<HHHH", *r) for r in runs))


def plain_record(text: str, like: bytes) -> bytes:
    """`text` in one run, styled like the record `like`."""
    return _record(text, like[6:8], [(1, len(text)) + runs_of(like)[0][2:]])


def append_prompt(rec: bytes, glyph: str, label: str) -> bytes:
    """'  <glyph> <label>' added to a button-prompt line. The space after the glyph is in the
    button font: plain spaces right after a glyph run are swallowed, and R3's glyph is narrower
    than the others."""
    text, runs = text_of(rec), runs_of(rec)
    glyph_style = next(r[2:] for r in runs if r[0] == r[1])
    text_style = next(r[2:] for r in runs if r[0] != r[1])
    n = len(text)
    if runs[-1][0] != runs[-1][1]:
        runs = runs[:-1] + [runs[-1][:1] + (n + 2,) + runs[-1][2:]]
    else:
        runs = runs + [(n + 1, n + 2) + text_style]
    new = text + "  " + glyph + "  " + label
    runs = runs + [(n + 3, n + 4) + glyph_style, (n + 5, len(new)) + text_style]
    return _record(new, rec[6:8], runs)


def glyph_line(caption: bytes, glyph: str, label: str) -> bytes:
    """'<glyph> <label>' as a centred caption, styled like the game caption `caption`."""
    runs = runs_of(caption)
    glyph_style = next(r[2:] for r in runs if r[0] == r[1])
    new = glyph + "  " + label
    return _record(new, caption[6:7] + b"\x81", [(1, 2) + glyph_style, (3, len(new)) + runs[-1][2:]])

# --- what changes --------------------------------------------------------------------------

LANGUAGES = ("en", "gb", "de", "fr", "es", "la", "it", "pt", "br", "nl", "pl", "ru", "cs", "jp",
             "kr", "ct")  # cs is Simplified Chinese here
LABEL = {"en": "Exit to Desktop", "gb": "Exit to Desktop", "de": "Zum Desktop",
         "fr": "Retour au bureau", "es": "Salir al escritorio", "la": "Salir al escritorio",
         "it": "Esci al desktop", "pt": "Sair para o desktop", "br": "Sair para o desktop",
         "nl": "Naar bureaublad", "pl": "Wyjdź do pulpitu", "ru": "На рабочий стол",
         "cs": "退出到桌面", "jp": "デスクトップに戻る", "kr": "바탕 화면으로 나가기", "ct": "退出至桌面"}
QUESTION = {"en": "Exit to the desktop?", "gb": "Exit to the desktop?", "de": "Zum Desktop beenden?",
            "fr": "Quitter vers le bureau ?", "es": "¿Salir al escritorio?", "la": "¿Salir al escritorio?",
            "it": "Uscire al desktop?", "pt": "Sair para o ambiente de trabalho?",
            "br": "Sair para a área de trabalho?", "nl": "Afsluiten naar het bureaublad?",
            "pl": "Wyjść do pulpitu?", "ru": "Выйти на рабочий стол?", "cs": "要退出到桌面吗？",
            "jp": "デスクトップに戻りますか？", "kr": "바탕 화면으로 나가시겠습니까?", "ct": "要退出至桌面嗎？"}
UNSAVED = {"en": "Any unsaved progress will be lost.", "gb": "Any unsaved progress will be lost.",
           "de": "Nicht gespeicherter Fortschritt geht verloren.",
           "fr": "Toute progression non sauvegardée sera perdue.",
           "es": "Se perderá el progreso no guardado.", "la": "Se perderá el progreso no guardado.",
           "it": "I progressi non salvati andranno persi.",
           "pt": "O progresso não guardado será perdido.", "br": "O progresso não salvo será perdido.",
           "nl": "Niet-opgeslagen voortgang gaat verloren.",
           "pl": "Niezapisane postępy zostaną utracone.", "ru": "Несохранённый прогресс будет потерян.",
           "cs": "未保存的进度将会丢失。", "jp": "セーブしていない進行状況は失われます。",
           "kr": "저장하지 않은 진행 상황은 사라집니다.", "ct": "未儲存的進度將會遺失。"}
GLYPH_R3 = "D"  # Gravity_Gaiji

# The settings menu (Options): clear an old request when it opens; take one up while it waits.
SETTINGS = "lua/game/menu/bp/selectscene.lua"
SETTINGS_EDITS = [(
    '''		function(cutno) -- c01
			gcd.info_view = nil''',
    '''		function(cutno) -- c01
			gcd.info_view = nil
			-- GRport: an Exit to Desktop request from before the menu opened does not count
			os.remove("/temp0/grport_exit_desktop")
			gcd.grport_desktop = nil'''), (
    '''				if gcd.current_submenu == nil then
					gcd.ChangeSubMenu()
				end

				-- Cancel Mission''',
    '''				if gcd.current_submenu == nil then
					gcd.ChangeSubMenu()
				end

				-- GRport: Exit to Desktop (R3; the runtime leaves the request in /temp0). While the
				-- dialog is up the menu holds still as for Exit to Title (the same flag, cleared on No).
				if not gcd.grport_desktop then
					local request = io.open("/temp0/grport_exit_desktop", "rb")
					if request then
						request:close()
						os.remove("/temp0/grport_exit_desktop")
						if not GameDatabase:get("Menu", "SelectMenu", "CodeTriggeredReturnToTitle") and
						   not GameDatabase:get("Menu", "SelectMenu", "CodeTriggeredCancelMission") and
						   not GameDatabase:get("Menu", "SelectMenu", "CodeTriggeredExit") then
							gcd.grport_desktop = true
							GameDatabase:set("Menu", "SelectMenu", "CodeTriggeredReturnToTitle", true)
						end
					end
				end
				if gcd.grport_desktop then
					local ans = UI:exitConfirmView_Sys("grport_exit_desktop")
					if ans == 2 then
						if not gcd.grport_quitting then print("GRPORT_QUIT_TO_DESKTOP") end
						gcd.grport_quitting = true
					elseif ans == -2 then
						gcd.grport_desktop = nil
						GameDatabase:set("Menu", "SelectMenu", "CodeTriggeredReturnToTitle", false)
					end
					return
				end

				-- Cancel Mission''')]

# The title screen: a hint caption while it waits for a choice, the same request and dialog.
TITLE = "lua/game/menu/title.lua"
TITLE_EDITS = [(
    '''	function(cutno) -- c03
		if gcd.bgm_state == 0 and Sound:isReadyBgm("bgm01") then''',
    '''	function(cutno) -- c03
		-- GRport: Exit to Desktop (R3; the runtime leaves the request in /temp0), with a hint
		-- while the title waits for a choice
		if not gcd.grport_cleared then
			os.remove("/temp0/grport_exit_desktop")
			gcd.grport_cleared = true
		end
		if gcd.touch_name == "" and not gcd.grport_desktop then
			if not gcd.grport_hint then
				gcd.grport_hint = Font:captionBegin("grport_title_hint", 0, Font.kLayerOverMovie)
			end
			local request = io.open("/temp0/grport_exit_desktop", "rb")
			if request then
				request:close()
				os.remove("/temp0/grport_exit_desktop")
				gcd.grport_desktop = true
				ComicDemo:setUserInteract(gcd.name, false, false, false, false)
			end
		elseif gcd.grport_hint and gcd.touch_name ~= "" then
			Font:captionEnd(gcd.grport_hint)
			gcd.grport_hint = nil
		end
		if gcd.grport_desktop then
			local ans = UI:exitConfirmView_Sys("grport_exit_desktop_title")
			if ans == 2 then
				if not gcd.grport_quitting then print("GRPORT_QUIT_TO_DESKTOP") end
				gcd.grport_quitting = true
			elseif ans == -2 then
				gcd.grport_desktop = nil
				ComicDemo:setUserInteract(gcd.name, false, false, false, true)
			end
			return
		end
		if gcd.bgm_state == 0 and Sound:isReadyBgm("bgm01") then''')]


def edit_script(raw: bytes, edits: list) -> bytes:
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")
    for old, new in edits:
        if text.count(old) != 1:
            raise ValueError("this copy of the game has different menu scripts")
        text = text.replace(old, new)
    if crlf:
        text = text.replace("\n", "\r\n")
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


def replacements(p: Psarc) -> dict:
    """The entries of arc_0 GRport changes: two menu scripts and the texts of every language."""
    repl = {SETTINGS: edit_script(p.get(SETTINGS), SETTINGS_EDITS),
            TITLE: edit_script(p.get(TITLE), TITLE_EDITS)}
    conf_title = fnv1a(b"conf_title")
    caption = txb_parse(p.get("txb/ingame_ep_datafile1_en.txb"))[fnv1a(b"opening_tap_message")]
    english = txb_parse(p.get("txb/ui_datafile1_en.txb"))
    # The settings menu's button-prompt lines (each tab, in and out of missions).
    prompts = [k for k, v in english.items()
               if any(r[0] == r[1] for r in runs_of(v)) and len(text_of(v)) < 120 and
               ("Exit to Title" in text_of(v) or "Cancel Mission" in text_of(v))]
    for lang in LANGUAGES:
        name = f"txb/ui_datafile1_{lang}.txb"
        recs = txb_parse(p.get(name))
        for k in prompts:
            recs[k] = append_prompt(recs[k], GLYPH_R3, LABEL[lang])
        like = recs[conf_title]
        recs[fnv1a(b"grport_exit_desktop")] = plain_record(QUESTION[lang] + "\n" + UNSAVED[lang], like)
        recs[fnv1a(b"grport_exit_desktop_title")] = plain_record(QUESTION[lang], like)
        repl[name] = txb_build(recs)
        name = f"txb/ingame_ep_datafile1_{lang}.txb"
        recs = txb_parse(p.get(name))
        recs[fnv1a(b"grport_title_hint")] = glyph_line(caption, GLYPH_R3, LABEL[lang])
        repl[name] = txb_build(recs)
    return repl


def ensure(archive: Path, out_dir: Path) -> Path:
    """The patch directory for the runtime (--app0-patch): builds out_dir/<ARCHIVE>.grpo from
    `archive` unless it was made from this very file by this version. Raises on a copy of the
    game this does not fit (other scripts), so the caller plays without it."""
    st = archive.stat()
    stamp = f"{VERSION} {st.st_size} {int(st.st_mtime)}"
    target = out_dir / (ARCHIVE + ".grpo")
    stamp_file = out_dir / "source.txt"
    if target.is_file() and stamp_file.is_file() and stamp_file.read_text(encoding="utf-8") == stamp:
        return out_dir
    p = Psarc(archive)
    data = overlay(p, replacements(p))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    stamp_file.write_text(stamp, encoding="utf-8")
    return out_dir

