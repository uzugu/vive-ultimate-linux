#!/usr/bin/env python3
"""Find code that references a string in a PE64 file and disassemble functions.

Static analysis helper for the reverse-engineering notes in docs/re/. Needs
`pip install pefile capstone`. Run on files extracted into a fresh directory:

    python3 -I tools/re/pe_disasm.py FILE.dll str "some log string"
    python3 -I tools/re/pe_disasm.py FILE.dll dis 43460 [END_RVA]

`str` prints each string match with the RVAs of the lea/mov instructions that
reference it and the start RVA of the containing function (from .pdata).
`dis` disassembles one function; rip-relative `lea` targets that point at
printable strings are annotated.
"""
import re
import struct
import sys

import capstone
import pefile


def load(path):
    pe = pefile.PE(path)
    img = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    funcs = sorted((f.struct.BeginAddress, f.struct.EndAddress) for f in pe.DIRECTORY_ENTRY_EXCEPTION)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    return pe, img, base, funcs, md


def func_of(funcs, rva):
    for begin, end in funcs:
        if begin <= rva < end:
            return begin, end
    return None


def xrefs(pe, img, rva):
    text = next(s for s in pe.sections if s.Characteristics & 0x20000000)
    code = img[text.VirtualAddress:text.VirtualAddress + text.Misc_VirtualSize]
    hits = []
    for i in range(len(code) - 4):
        disp = struct.unpack_from("<i", code, i)[0]
        addr = text.VirtualAddress + i
        # approximate: disp32 sits 0..4 bytes before the end of the instruction
        if any(addr + 4 + extra + disp == rva for extra in range(0, 5)):
            hits.append(addr)
    return hits


def disassemble(img, base, md, begin, end):
    for ins in md.disasm(img[begin:end], begin + base):
        note = ""
        m = re.search(r"rip ([+-]) (0x[0-9a-f]+)", ins.op_str)
        if m and ins.mnemonic == "lea":
            delta = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            target = ins.address - base + ins.size + delta
            if 0 <= target < len(img):
                raw = img[target:img.find(b"\0", target, target + 300)]
                if len(raw) > 2 and all(32 <= c < 127 or c in (9, 10) for c in raw):
                    note = '   ; "%s"' % raw.decode()
        print("%x: %s %s%s" % (ins.address - base, ins.mnemonic, ins.op_str, note))


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    pe, img, base, funcs, md = load(sys.argv[1])
    if sys.argv[2] == "str":
        for needle in sys.argv[3:]:
            data = needle.encode()
            pos = img.find(data)
            while pos >= 0:
                refs = [(hex(x), hex(func_of(funcs, x)[0]) if func_of(funcs, x) else None) for x in xrefs(pe, img, pos)]
                print(needle, hex(pos), refs)
                pos = img.find(data, pos + 1)
    elif sys.argv[2] == "dis":
        begin = int(sys.argv[3], 16)
        end = int(sys.argv[4], 16) if len(sys.argv) > 4 else func_of(funcs, begin)[1]
        disassemble(img, base, md, begin, end)


if __name__ == "__main__":
    main()
