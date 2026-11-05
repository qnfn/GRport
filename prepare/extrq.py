"""SSE4a EXTRQ for CPUs without it (Intel): DRIVECLUB's eboot uses `extrq xmm, len, idx`
(AMD only; 316 sites in 1.28, all `len 8, idx 0` or `len 8, idx 32`). On a CPU without SSE4a
the first one ends the game (0xC000001D). Each site becomes a jump to a trampoline in a new
executable segment: psllq xmm, 64-idx-len; psrlq xmm, 64-len; jmp back, which gives EXTRQ's
low qword (its upper qword is undefined by AMD). Found and verified by jony113; the macOS
backend's PatchExtrq does the same at run time.

Gravity Rush 2 (1.11) instead uses `extrq xmm, xmm` (66 [REX] 0F 79 /r: length and index in
the source's low bits; 96 sites in two functions at 0x3ab8cd and 0x3adb18, first run while
the game starts). Its trampoline saves rax, rcx, rdx and the flags 128 bytes below rsp (the
red zone stays untouched), computes (dst >> index) masked to length with shr/shl/shr by cl,
and restores them. 40 of those sites are 4 bytes, too short for a jmp: the next instruction
moves into the trampoline when the function's own branches (from its .eh_frame_hdr bounds)
cannot land between the two and it has no jump table. Sites left out are emulated by the
runtime's illegal-instruction handler (slower, but correct).

Runs on CPUs without SSE4a only, so AMD images stay byte-identical; DC_EXTRQ_PATCH=0/1
overrides the CPU check.
"""
import bisect
import os
import re
import struct

from cpu_compat import _cpuid_windows

# 66 [REX.B] 0F 78 /0 ib ib, register form (ModRM C0..C7).
PATTERN = re.compile(rb'\x66([\x40-\x4f]?)\x0f\x78([\xc0-\xc7])(.)(.)', re.DOTALL)
# 66 [REX.RB] 0F 79 /r, both operands XMM registers (ModRM C0..FF).
REGISTER_PATTERN = re.compile(rb'\x66([\x40-\x4f]?)\x0f\x79([\xc0-\xff])', re.DOTALL)
MAX_IMAGE_SIZE = 512 * 1024 * 1024
EH_FRAME_HDR = 0x6474e550


def sse4a_missing(cpuid=None):
    """True when the CPU lacks SSE4a (CPUID 0x80000001 ECX bit 6), None when unknown."""
    cleanup = None
    if cpuid is None:
        if os.name != 'nt' or struct.calcsize('P') != 8:
            return None
        try:
            found = _cpuid_windows()
        except (OSError, AttributeError, ValueError):
            return None
        if not found:
            return None
        cpuid, cleanup = found
    try:
        if cpuid(0x80000000)[0] < 0x80000001:
            return True
        return not cpuid(0x80000001)[2] >> 6 & 1
    finally:
        if cleanup:
            cleanup()


def enabled():
    override = os.environ.get('DC_EXTRQ_PATCH')
    if override in ('0', '1'):
        return override == '1'
    # Unknown CPU: translate (the trampolines run on every x86-64 CPU).
    missing = sse4a_missing()
    return missing is None or missing


def trampoline(rex, modrm, length, index):
    """psllq xmm, 64-index-length; psrlq xmm, 64-length (both skipped when the shift is 0)."""
    rm = modrm & 7
    prefix = b'\x66' + (bytes([rex & 0x41]) if rex & 1 else b'')
    body = b''
    if 64 - index - length:
        body += prefix + b'\x0f\x73' + bytes([0xf0 | rm, 64 - index - length])
    if 64 - length:
        body += prefix + b'\x0f\x73' + bytes([0xd0 | rm, 64 - length])
    return body


def register_trampoline(rex, modrm):
    """`extrq xmm(dst), xmm(src)`: dst.low = (dst.low >> src[13:8]) & ((1 << src[5:0]) - 1),
    length 0 meaning 64; the upper qword becomes 0 (undefined on AMD). Flags, GPRs and the
    128 bytes below rsp are preserved. x86 masks shift counts to 6 bits, so cl = src >> 8
    shifts by the index and cl = -src by (64 - length) & 63."""
    dst = (modrm >> 3 & 7) | (rex & 4) << 1
    src = (modrm & 7) | (rex & 1) << 3

    def movq(xmm, opcode, gpr):  # 66 REX.W[R] 0F 7E (movq r64, xmm) / 6E (movq xmm, r64)
        return bytes([0x66, 0x48 | (xmm >> 3) << 2, 0x0f, opcode, 0xc0 | (xmm & 7) << 3 | gpr])
    return (bytes.fromhex('488d642480' '9c' '50' '51' '52')  # lea rsp,[rsp-128]; pushfq; push rax/rcx/rdx
            + movq(src, 0x7e, 2) + movq(dst, 0x7e, 0)           # movq rdx, src; movq rax, dst
            + bytes.fromhex('89d1' 'c1e908' '48d3e8'            # mov ecx,edx; shr ecx,8; shr rax,cl
                            '89d1' 'f7d9' '48d3e0' '48d3e8')    # mov ecx,edx; neg ecx; shl rax,cl; shr rax,cl
            + movq(dst, 0x6e, 0)                                # movq dst, rax
            + bytes.fromhex('5a' '59' '58' '9d' '488da42480000000'))  # pop rdx/rcx/rax; popfq; lea rsp,[rsp+128]


def function_ranges(image, ph):
    """Function starts of the eboot (from its .eh_frame_hdr) within its text, plus the end."""
    text = next((p for p in ph if p['type'] == 1 and p['flags'] & 1), None)
    hdr = next((p for p in ph if p['type'] == EH_FRAME_HDR), None)
    if text is None or hdr is None:
        return []
    at = hdr['vaddr']
    if image[at + 2] != 0x03 or image[at + 3] != 0x3b:  # udata4 count, sdata4 datarel table
        return []
    count, = struct.unpack_from('<I', image, at + 8)
    start, end = text['vaddr'], text['vaddr'] + text['filesz']
    starts = sorted({at + struct.unpack_from('<i', image, at + 12 + 8 * i)[0] for i in range(count)})
    return [s for s in starts if start <= s < end] + [end]


def _branch_targets(md, image, start, end):
    """Direct branch targets of one function, or None when it has a jump table or does not
    decode to its end (its entries are then unknown)."""
    from capstone import CS_GRP_JUMP, x86
    targets, at = set(), start
    for i in md.disasm(bytes(image[start:end]), start):
        at = i.address + i.size
        if i.group(CS_GRP_JUMP):
            op = i.operands[0]
            if op.type == x86.X86_OP_IMM:
                targets.add(op.imm)
            elif not (op.type == x86.X86_OP_MEM and op.mem.base == x86.X86_REG_RIP):
                return None
    return targets if at == end else None


def _movable(i):
    """Runs the same from a trampoline: no control flow, nothing rip-relative, rsp unchanged."""
    from capstone import CS_GRP_CALL, CS_GRP_INT, CS_GRP_IRET, CS_GRP_JUMP, CS_GRP_RET, x86
    read, written = i.regs_access()
    return (not {CS_GRP_JUMP, CS_GRP_CALL, CS_GRP_RET, CS_GRP_INT, CS_GRP_IRET} & set(i.groups)
            and x86.X86_REG_RSP not in written and x86.X86_REG_RIP not in read
            and not any(op.type == x86.X86_OP_MEM and op.mem.base == x86.X86_REG_RIP
                        for op in i.operands))


def _register_edits(image, code, main_size, relocations, ph):
    """(start, end, body) for each `extrq xmm, xmm` of the eboot, and how many are left to the
    runtime (4-byte sites whose neighbour cannot move, or no capstone)."""
    found = []
    for start, size in code:
        for m in REGISTER_PATTERN.finditer(image, start, min(start + size, main_size)):
            found.append((m.start(), m.end(), m.group(1)[0] if m.group(1) else 0, m.group(2)[0]))
    if not found:
        return [], 0
    try:
        import capstone
    except ImportError:  # 5-byte sites still translate; 4-byte ones run in the runtime
        capstone = None
    md = None
    if capstone:
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
    bounds = function_ranges(image, ph) if ph else []
    branch_cache = {}
    reloc_sites = sorted(r[0] for r in relocations)
    reloc_targets = sorted(r[2] + r[3] for r in relocations if r[1] == 0)

    def touched(a, b):  # a relocation written into [a, b) or pointing inside (a, b)
        i = bisect.bisect_left(reloc_sites, a - 7)
        j = bisect.bisect_right(reloc_targets, a)
        return ((i < len(reloc_sites) and reloc_sites[i] < b)
                or (j < len(reloc_targets) and reloc_targets[j] < b))

    edits, left, consumed = [], 0, set()
    for site_start, site_end, rex, modrm in found:
        if site_start in consumed:
            continue
        if rex & 0x08 or touched(site_start, site_end):  # REX.W: not an EXTRQ encoding we know
            left += 1
            continue
        body = register_trampoline(rex, modrm)
        if site_end - site_start >= 5:
            edits.append((site_start, site_end, body))
            continue
        k = bisect.bisect_right(bounds, site_start) - 1
        if md is None or k < 0 or k + 1 >= len(bounds):
            left += 1
            continue
        function = (bounds[k], bounds[k + 1])
        if function not in branch_cache:
            branch_cache[function] = _branch_targets(md, image, *function)
        targets = branch_cache[function]
        neighbour = next(md.disasm(bytes(image[site_end:site_end + 15]), site_end, 1), None)
        if (targets is None or neighbour is None or not _movable(neighbour)
                or site_end in targets or site_end + neighbour.size > function[1]
                or touched(site_start, site_end + neighbour.size)):
            left += 1
            continue
        moved = REGISTER_PATTERN.fullmatch(bytes(neighbour.bytes))
        if moved and not (moved.group(1) and moved.group(1)[0] & 0x08):
            body += register_trampoline(moved.group(1)[0] if moved.group(1) else 0, moved.group(2)[0])
            consumed.add(site_end)
        else:
            body += bytes(neighbour.bytes)
        edits.append((site_start, site_end + neighbour.size, body))
    return edits, left


def patch(image, segments, main_size, relocations, *, active=None, ph=None):
    """A copy of the linked image with every EXTRQ of the eboot translated, the segment list
    with the trampoline segment added, and a report. Unchanged when inactive or none found.
    ph: the eboot's program headers (function bounds for 4-byte register-form sites)."""
    is_active = enabled() if active is None else active
    report = dict(enabled=bool(is_active), sites=0, by_form={}, trampoline_bytes=0,
                  register_sites=0, register_spans=0, left_to_runtime=0)
    result, new_segments = bytearray(image), list(segments)
    if not is_active:
        return result, new_segments, report
    code = [(start, size) for start, size, flags in segments
            if flags & 1 and start < main_size]
    targets = sorted(r[0] for r in relocations)
    edits, forms = [], {}
    for start, size in code:
        end = min(start + size, main_size)
        for m in PATTERN.finditer(image, start, end):
            rex, modrm = m.group(1), m.group(2)[0]
            length, index = m.group(3)[0], m.group(4)[0]
            length = length & 63 or 64
            index &= 63
            if index + length > 64:
                raise ValueError(f'EXTRQ at {m.start():#x}: index {index} + length {length} > 64')
            if rex and rex[0] & 0x0e:  # only REX.B may be set for a register-form EXTRQ
                raise ValueError(f'EXTRQ at {m.start():#x}: unexpected REX {rex[0]:#x}')
            i = bisect.bisect_left(targets, m.start() - 7)
            if i < len(targets) and targets[i] < m.end():
                raise ValueError(f'EXTRQ at {m.start():#x} overlaps a relocation')
            edits.append((m.start(), m.end(), trampoline(rex[0] if rex else 0, modrm, length, index)))
            key = f'len {length} idx {index}'
            forms[key] = forms.get(key, 0) + 1
    register, left = _register_edits(image, code, main_size, relocations, ph)
    report.update(register_sites=len(register), left_to_runtime=left,
                  register_spans=sum(1 for start, end, _ in register if end - start != 5))
    if register:
        forms['xmm, xmm'] = len(register)
    edits = sorted(edits + register)
    if not edits:
        return result, new_segments, report
    arena = (len(image) + 65535) & ~65535
    cursor = arena
    for site_start, site_end, body in edits:
        back = site_end - (cursor + len(body) + 5)
        go = site_start + 5
        body += b'\xe9' + struct.pack('<i', back)
        jump = b'\xe9' + struct.pack('<i', cursor - go) + b'\x90' * (site_end - site_start - 5)
        if len(result) < cursor + len(body):
            result.extend(bytes(cursor + len(body) - len(result)))
        result[site_start:site_end] = jump
        result[cursor:cursor + len(body)] = body
        cursor = (cursor + len(body) + 15) & ~15
    padded = (cursor + 4095) & ~4095
    if padded > MAX_IMAGE_SIZE:
        raise ValueError('EXTRQ trampolines exceed the image size limit')
    result.extend(bytes(padded - len(result)))
    new_segments.append((arena, padded - arena, 5))
    report.update(sites=len(edits), by_form=forms, trampoline_bytes=cursor - arena)
    return result, new_segments, report
