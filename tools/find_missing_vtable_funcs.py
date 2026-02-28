"""
Scan the Xbox 360 PE image data section for vtable-like function pointers
that are NOT in the recompiled function table.

The PE image (pe_image.bin) is mapped at guest address 0x82000000.
- Data section: 0x82000000 - 0x82090000 (offsets 0x00000 - 0x90000)
- Code section: 0x82090000 - 0x824E0000 (offsets 0x90000 - 0x4E0000)

We scan the data section for big-endian 32-bit values that:
1. Fall in the code range (0x82090000 - 0x8238D8F8)
2. Are 4-byte aligned
3. Are NOT already in the function table (vig8_init.cpp)
4. Appear in clusters of 2+ consecutive code pointers (vtable pattern)

Results are categorized as:
- THUNK: 2-instruction C++ virtual adjustor thunks (addi r3,r3,offset; b func)
- FUNC: Genuine function entry points
"""

import struct
import re
import sys
from collections import defaultdict

IMAGE_BASE = 0x82000000
CODE_START = 0x82090000
CODE_END   = 0x8238D8F8


def parse_function_table(path):
    """Parse all function addresses from vig8_init.cpp"""
    addrs = set()
    pattern = re.compile(r'\{\s*0x([0-9A-Fa-f]+)\s*,')
    with open(path, 'r') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                addrs.add(int(m.group(1), 16))
    return addrs


def classify_entry(pe_data, target):
    """Classify a code address as THUNK or FUNC based on instruction pattern."""
    offset = target - IMAGE_BASE
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
    init_cpp = 'E:/vig8/generated/vig8_init.cpp'
    pe_image = 'E:/vig8/extracted/pe_image.bin'

    print("=" * 80)
    print("Vigilante 8 Arcade - Missing VTable Function Finder")
    print("=" * 80)

    # Step 1: Parse function table
    print("\n[1] Parsing function table from vig8_init.cpp...")
    known_funcs = parse_function_table(init_cpp)
    print(f"    Found {len(known_funcs)} known function addresses")

    # Step 2: Read PE image
    print("\n[2] Reading PE image...")
    with open(pe_image, 'rb') as f:
        pe_data = f.read()
    print(f"    Image size: 0x{len(pe_data):X} bytes")

    # Step 3: Scan data section for all code-range pointers
    print("\n[3] Scanning data section (0x00000-0x90000) for code pointers...")
    all_ptrs = []
    for i in range(0, 0x90000 - 3, 4):
        val = struct.unpack('>I', pe_data[i:i+4])[0]
        if CODE_START <= val <= CODE_END and (val & 3) == 0:
            all_ptrs.append((i, IMAGE_BASE + i, val))
    print(f"    Found {len(all_ptrs)} code-range pointers")

    # Step 4: Build clusters of consecutive pointers
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

    # Step 5: Find missing entries in clusters only
    missing_in_clusters = set()
    ref_locations = defaultdict(list)
    for cluster in clusters:
        for _, guest, target in cluster:
            if target not in known_funcs:
                missing_in_clusters.add(target)
                ref_locations[target].append(guest)

    # Step 6: Classify and report
    thunks = []
    funcs = []
    for target in sorted(missing_in_clusters):
        kind, info = classify_entry(pe_data, target)
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

    # Group: game-logic (0x8209-0x822F) vs CRT/library (0x8230+)
    game_thunks = [(t, i, r) for t, i, r in thunks if t < 0x82300000]
    game_funcs  = [(t, r) for t, r in funcs if t < 0x82300000]
    lib_thunks  = [(t, i, r) for t, i, r in thunks if t >= 0x82300000]
    lib_funcs   = [(t, r) for t, r in funcs if t >= 0x82300000]

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

    # Step 7: Generate TOML snippet for XenonRecomp config
    print("\n" + "=" * 80)
    print("TOML CONFIG SNIPPET (add to vig8.toml [functions] section)")
    print("=" * 80)
    print()
    print("# Missing vtable function entries found by find_missing_vtable_funcs.py")
    all_missing_sorted = sorted(missing_in_clusters)
    for target in all_missing_sorted:
        kind, info = classify_entry(pe_data, target)
        if kind == 'THUNK':
            comment = f"  # thunk: addi r3,{info['adjust']}; b 0x{info['branch_target']:08X}"
        else:
            comment = ""
        print(f'# 0x{target:08X}{comment}')

    # Step 8: Status of known missing
    print("\n" + "=" * 80)
    print("STATUS OF PREVIOUSLY KNOWN MISSING FUNCTIONS")
    print("=" * 80)
    known_missing = [0x821A17D0, 0x821664F0, 0x8216BEA8]
    for addr in known_missing:
        in_table = "IN TABLE" if addr in known_funcs else "MISSING"
        in_vtable = "in vtable data" if addr in missing_in_clusters else "not in vtable clusters"
        print(f"  0x{addr:08X}: {in_table}, {in_vtable}")


if __name__ == '__main__':
    main()
