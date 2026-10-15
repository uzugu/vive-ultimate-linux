#!/usr/bin/env python3
"""Tiny static helper for PE64 files: find code that references a string, and disassemble around it.

  xref.py <file.dll> "<substring>" [--ctx N]      list string hits and the code that loads them
  xref.py <file.dll> --func <rva-hex> [--n N]     disassemble N instructions from an RVA
  xref.py <file.dll> --exports                    list exports with RVAs

Pure static analysis (pefile + capstone). Run with `python3 -I`. Never executes the target.
"""
import argparse, struct, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

def load(path):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, "rb").read()
    return pe, data

def sections(pe):
    return [(s.Name.rstrip(b"\0").decode(), s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData, s.Characteristics) for s in pe.sections]

def rva_to_off(pe, rva):
    for _, va, vs, ro, rs, _ in sections(pe):
        if va <= rva < va + max(vs, rs):
            return ro + rva - va
    return None

def find_strings(pe, data, needle):
    hits = []
    for enc, nb in (("ascii", needle.encode()), ("utf-16le", needle.encode("utf-16le"))):
        start = 0
        while True:
            i = data.find(nb, start)
            if i < 0:
                break
            start = i + 1
            for _, va, vs, ro, rs, ch in sections(pe):
                if ro <= i < ro + rs and not (ch & 0x20000000):  # skip executable sections
                    # expand to full string
                    j = i
                    while j > ro and data[j-1] not in (0,) and (j == i or data[j-1] >= 32): j -= 1
                    hits.append((va + (j - ro), enc))
                    break
    return sorted(set(hits))

def code_xrefs(pe, data, target_rvas):
    """Scan every function listed in .pdata (so decoding never desyncs on data) for RIP-relative refs."""
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    refs = {t: [] for t in target_rvas}
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    for e in getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", []):
        s, en = e.struct.BeginAddress, e.struct.EndAddress
        off = rva_to_off(pe, s)
        if off is None:
            continue
        for ins in md.disasm(data[off:off + (en - s)], s):
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    tgt = ins.address + ins.size + op.mem.disp
                    if tgt in refs:
                        refs[tgt].append(ins.address)
    return refs

def func_start(pe, data, rva):
    """Walk back to a plausible function start using the .pdata unwind table."""
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    best = None
    for e in getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", []):
        s, en = e.struct.BeginAddress, e.struct.EndAddress
        if s <= rva < en:
            return s, en
    return None

def cstr(pe, data, rva):
    off = rva_to_off(pe, rva)
    if off is None:
        return None
    raw = data[off:off + 160]
    a = raw.split(b"\0")[0]
    if len(a) >= 3 and all(32 <= c < 127 for c in a):
        return a.decode()
    w = raw
    chars = []
    for i in range(0, len(w) - 1, 2):
        c = w[i] | (w[i + 1] << 8)
        if c == 0: break
        if not 32 <= c < 127: return None
        chars.append(chr(c))
    return "".join(chars) if len(chars) >= 3 else None

def disasm(pe, data, rva, n=80, end=None, annotate=True):
    off = rva_to_off(pe, rva)
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = annotate
    out = []
    for ins in md.disasm(data[off:off + 0x4000], rva):
        note = ""
        if annotate:
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    t = ins.address + ins.size + op.mem.disp
                    sv = cstr(pe, data, t) if ins.mnemonic == "lea" else None
                    note = f'   ; "{sv}"' if sv else f"   ; [{t:x}]"
        out.append(f"{ins.address:08x}  {ins.mnemonic:7s} {ins.op_str}{note}")
        if len(out) >= n or (end and ins.address >= end):
            break
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file"); ap.add_argument("needle", nargs="?")
    ap.add_argument("--ctx", type=int, default=0); ap.add_argument("--func"); ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--exports", action="store_true")
    a = ap.parse_args()
    pe, data = load(a.file)
    if a.exports:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
        for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            print(f"{s.address:08x} {s.name.decode() if s.name else s.ordinal}")
        return
    if a.func:
        rva = int(a.func, 16); f = func_start(pe, data, rva); end = f[1] if f else None
        print("\n".join(disasm(pe, data, rva, a.n, end))); return
    base = pe.OPTIONAL_HEADER.ImageBase
    hits = find_strings(pe, data, a.needle)
    rvas = [h[0] for h in hits]
    refs = code_xrefs(pe, data, rvas)
    for rva, enc in hits:
        off = rva_to_off(pe, rva)
        s = data[off:off + 120].split(b"\0\0" if enc == "utf-16le" else b"\0")[0]
        txt = s.decode("utf-16le", "ignore") if enc == "utf-16le" else s.decode("latin1")
        print(f"string rva={rva:08x} ({enc}): {txt[:100]!r}")
        for r in refs.get(rva, []):
            f = func_start(pe, data, r)
            print(f"   used at {r:08x}" + (f" in func {f[0]:08x}-{f[1]:08x}" if f else ""))

if __name__ == "__main__":
    main()
