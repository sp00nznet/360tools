"""
Scan an Xbox 360 PE image data section for vtable-like function pointers
that are NOT in the recompiled function table.

We scan the data section for big-endian 32-bit values that:
1. Fall in the code range
2. Are 4-byte aligned
3. Are NOT already in the function table (*_init.cpp)
4. Appear in clusters of 2+ consecutive code pointers (vtable pattern)

Results are categorized as:
- THUNK: 2-instruction C++ virtual adjustor thunks (addi r3,r3,offset; b func)
- FUNC: Genuine function entry points

Usage: py find_missing_vtable_funcs.py <pe_image.bin> <init.cpp> [options]
"""

import struct
import re
import sys
import argparse
from collections import defaultdict


def detect_pe_sections(pe_data, image_base):
    """Auto-detect code and data section boundaries from PE headers.
    Returns (data_start_offset, data_end_offset, code_start, code_end).
    Falls back to scanning heuristics if PE parsing fails."""

    # Try to parse PE/COFF headers
    if pe_data[:2] == b'MZ':
        pe_off = struct.unpack_from('<I', pe_data, 0x3C)[0]
        if pe_data[pe_off:pe_off+4] == b'PE\x00\x00':
            num_sections = struct.unpack_from('<H', pe_data, pe_off + 6)[0]
            opt_hdr_size = struct.unpack_from('<H', pe_data, pe_off + 20)[0]
            section_off = pe_off + 24 + opt_hdr_size

            code_start = None
            code_end = None
            data_end = 0

            for i in range(num_sections):
                s = section_off + i * 40
                name = pe_data[s:s+8].rstrip(b'\x00').decode('ascii', errors='replace')
                vsize = struct.unpack_from('<I', pe_data, s + 8)[0]
                vaddr = struct.unpack_from('<I', pe_data, s + 12)[0]
                chars = struct.unpack_from('<I', pe_data, s + 36)[0]

                section_start = vaddr
                section_end = vaddr + vsize

                # IMAGE_SCN_CNT_CODE = 0x20, IMAGE_SCN_MEM_EXECUTE = 0x20000000
                if chars & 0x20000020:
                    if code_start is None or section_start < code_start:
                        code_start = section_start
                    if code_end is None or section_end > code_end:
                        code_end = section_end
                else:
                    if section_end > data_end:
                        data_end = section_end

            if code_start is not None:
                data_start_off = 0
                data_end_off = code_start  # data is everything before code
                return data_start_off, data_end_off, image_base + code_start, image_base + code_end

    # Fallback: assume data is first 1/6 of image, code is the rest
    data_end_off = len(pe_data) // 6
    code_start = image_base + data_end_off
    code_end = image_base + len(pe_data)
    return 0, data_end_off, code_start, code_end


def parse_function_table(path):
    """Parse all function addresses from *_init.cpp"""
    addrs = set()
    pattern = re.compile(r'\{\s*0x([0-9A-Fa-f]+)\s*,')
    with open(path, 'r') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                addrs.add(int(m.group(1), 16))
    return addrs


def classify_entry(pe_data, target, image_base):
    """Classify a code address as THUNK or FUNC based on instruction pattern."""
    offset = target - image_base
    if offset + 8 > len(pe_data):
        return 'FUNC', {}

    instr1 = struct.unpack('>I', pe_data[offset:offset+4])[0]
    instr2 = struct.unpack('>I', pe_data[offset+4:offset+8])[0]

    op1 = (instr1 >> 26) & 0x3F
    op2 = (instr2 >> 26) & 0x3F

    # Check for thunk: addi r3,r3,imm; b target
    is_addi_r3 = (op1 == 14
                  and ((instr1 >> 21) & 0x1F) == 3
                  and ((instr1 >> 16) & 0x1F) == 3)
    is_branch = (op2 == 18 and (instr2 & 1) == 0)

    if is_addi_r3 and is_branch:
        imm = instr1 & 0xFFFF
        if imm >= 0x8000:
            imm -= 0x10000
        li = instr2 & 0x03FFFFFC
        if li >= 0x02000000:
            li -= 0x04000000
        branch_target = target + 4 + li
        return 'THUNK', {'adjust': imm, 'branch_target': branch_target}

    return 'FUNC', {}


def main():
    parser = argparse.ArgumentParser(
        description='Find vtable function pointers missing from the recompiled function table.')
    parser.add_argument('pe_image', help='Path to the decompressed PE image')
    parser.add_argument('init_cpp', help='Path to the generated *_init.cpp file')
    parser.add_argument('--base', type=lambda x: int(x, 0), default=0x82000000,
                        help='Image base address (default: 0x82000000)')
    parser.add_argument('--code-start', type=lambda x: int(x, 0), default=None,
                        help='Start of code section (auto-detected if omitted)')
    parser.add_argument('--code-end', type=lambda x: int(x, 0), default=None,
                        help='End of code section (auto-detected if omitted)')
    parser.add_argument('--data-end', type=lambda x: int(x, 0), default=None,
                        help='End of data section to scan (auto-detected if omitted)')
    args = parser.parse_args()

    IMAGE_BASE = args.base

    print("=" * 80)
    print("Missing VTable Function Finder")
    print("=" * 80)

    # Step 1: Parse function table
    print(f"\n[1] Parsing function table from {args.init_cpp}...")
    known_funcs = parse_function_table(args.init_cpp)
    print(f"    Found {len(known_funcs)} known function addresses")

    # Step 2: Read PE image
    print("\n[2] Reading PE image...")
    with open(args.pe_image, 'rb') as f:
        pe_data = f.read()
    print(f"    Image size: 0x{len(pe_data):X} bytes")

    # Step 3: Determine section boundaries
    data_start_off, data_end_off, code_start, code_end = detect_pe_sections(pe_data, IMAGE_BASE)

    if args.code_start is not None:
        code_start = args.code_start
    if args.code_end is not None:
        code_end = args.code_end
    if args.data_end is not None:
        data_end_off = args.data_end - IMAGE_BASE

    print(f"    Data section: 0x{IMAGE_BASE + data_start_off:08X} - 0x{IMAGE_BASE + data_end_off:08X}")
    print(f"    Code section: 0x{code_start:08X} - 0x{code_end:08X}")

    # Step 4: Scan data section for all code-range pointers
    print(f"\n[3] Scanning data section for code pointers...")
    all_ptrs = []
    for i in range(data_start_off, data_end_off - 3, 4):
        val = struct.unpack('>I', pe_data[i:i+4])[0]
        if code_start <= val <= code_end and (val & 3) == 0:
            all_ptrs.append((i, IMAGE_BASE + i, val))
    print(f"    Found {len(all_ptrs)} code-range pointers")

    # Step 5: Build clusters of consecutive pointers
    print("\n[4] Finding vtable clusters (2+ consecutive code pointers)...")
    clusters = []
    current = []
    for file_off, guest, target in all_ptrs:
        if current and file_off == current[-1][0] + 4:
            current.append((file_off, guest, target))
        else:
            if len(current) >= 2:
                clusters.append(current[:])
            current = [(file_off, guest, target)]
    if len(current) >= 2:
        clusters.append(current)
    print(f"    Found {len(clusters)} vtable clusters")

    # Step 6: Find missing entries in clusters only
    missing_in_clusters = set()
    ref_locations = defaultdict(list)
    for cluster in clusters:
        for _, guest, target in cluster:
            if target not in known_funcs:
                missing_in_clusters.add(target)
                ref_locations[target].append(guest)

    # Step 7: Classify and report
    thunks = []
    funcs = []
    for target in sorted(missing_in_clusters):
        kind, info = classify_entry(pe_data, target, IMAGE_BASE)
        refs = ref_locations[target]
        if kind == 'THUNK':
            thunks.append((target, info, refs))
        else:
            funcs.append((target, refs))

    print("\n" + "=" * 80)
    print(f"RESULTS: {len(missing_in_clusters)} missing vtable entries")
    print(f"  {len(thunks)} C++ virtual adjustor thunks")
    print(f"  {len(funcs)} function entry points")
    print("=" * 80)

    # Group by region: game-logic vs CRT/library
    # Use midpoint between code_start and code_end as heuristic boundary
    lib_boundary = code_start + (code_end - code_start) * 3 // 4

    game_thunks = [(t, i, r) for t, i, r in thunks if t < lib_boundary]
    game_funcs  = [(t, r) for t, r in funcs if t < lib_boundary]
    lib_thunks  = [(t, i, r) for t, i, r in thunks if t >= lib_boundary]
    lib_funcs   = [(t, r) for t, r in funcs if t >= lib_boundary]

    print(f"\n--- GAME-LOGIC THUNKS ({len(game_thunks)}) ---")
    for target, info, refs in game_thunks:
        loc_str = ", ".join(f"0x{r:08X}" for r in refs[:3])
        print(f"  0x{target:08X}  addi r3,r3,{info['adjust']}; b 0x{info['branch_target']:08X}"
              f"  ({len(refs)} refs: {loc_str})")

    print(f"\n--- GAME-LOGIC FUNCTIONS ({len(game_funcs)}) ---")
    for target, refs in game_funcs:
        loc_str = ", ".join(f"0x{r:08X}" for r in refs[:3])
        print(f"  0x{target:08X}  ({len(refs)} refs: {loc_str})")

    print(f"\n--- LIBRARY/CRT THUNKS ({len(lib_thunks)}) ---")
    for target, info, refs in lib_thunks:
        print(f"  0x{target:08X}  addi r3,r3,{info['adjust']}; b 0x{info['branch_target']:08X}")

    print(f"\n--- LIBRARY/CRT FUNCTIONS ({len(lib_funcs)}) ---")
    for target, refs in lib_funcs:
        print(f"  0x{target:08X}")

    # Step 8: Generate TOML snippet
    print("\n" + "=" * 80)
    print("TOML CONFIG SNIPPET (add to your [functions] section)")
    print("=" * 80)
    print()
    print("# Missing vtable function entries found by find_missing_vtable_funcs.py")
    all_missing_sorted = sorted(missing_in_clusters)
    for target in all_missing_sorted:
        kind, info = classify_entry(pe_data, target, IMAGE_BASE)
        if kind == 'THUNK':
            comment = f"  # thunk: addi r3,{info['adjust']}; b 0x{info['branch_target']:08X}"
        else:
            comment = ""
        print(f'# 0x{target:08X}{comment}')


if __name__ == '__main__':
    main()
