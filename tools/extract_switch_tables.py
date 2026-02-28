#!/usr/bin/env python3
"""
Extract switch table data from pe_image.bin and generate XenonRecomp TOML config.

Scans for the PPC pattern: add r12,r12,r0; mtctr r12; bctr
Then looks backward to find the table address, base address, entry type, and index register.
Reads the table from pe_image.bin and generates [[switch]] TOML entries.
"""

import struct
import sys
import os

PE_BASE = 0x82000000
PE_FILE = os.path.join(os.path.dirname(__file__), "..", "extracted", "default_pe.exe")

# Pattern: add r12,r12,r0 (7D8C0214) + mtctr r12 (7D8903A6) + bctr (4E800420)
PATTERN = bytes.fromhex("7D8C0214" "7D8903A6" "4E800420")


def read_u32_be(data, offset):
    return struct.unpack_from('>I', data, offset)[0]


def read_u16_be(data, offset):
    return struct.unpack_from('>H', data, offset)[0]


def read_u8(data, offset):
    return data[offset]


def sign_extend_16(val):
    if val >= 0x8000:
        val -= 0x10000
    return val


def decode_insn(data, offset):
    """Decode a PPC instruction into its fields."""
    insn = read_u32_be(data, offset)
    return {
        'raw': insn,
        'opcode': (insn >> 26) & 0x3F,
        'rd': (insn >> 21) & 0x1F,  # also rs for store/mtspr
        'ra': (insn >> 16) & 0x1F,
        'rb': (insn >> 11) & 0x1F,
        'sh': (insn >> 11) & 0x1F,
        'mb': (insn >> 6) & 0x1F,
        'me': (insn >> 1) & 0x1F,
        'xo_10': (insn >> 1) & 0x3FF,  # 10-bit XO for opcode 31
        'simm': sign_extend_16(insn & 0xFFFF),
        'uimm': insn & 0xFFFF,
    }


def find_switch_info(data, add_offset):
    """
    Given the file offset of 'add r12,r12,r0', look backward to find:
    - table_addr: from first lis r12 + addi r12 pair (before lhzx/lbzx)
    - base_addr: from second lis r12 + addi r12 pair (between lhzx and add)
    - entry_type: 'u16' for lhzx, 'u8' for lbzx
    - entry_scale: post-load scaling factor (1 or 4)
    - index_reg: the PPC register holding the switch index value
    """

    # Step 1: Find the base address (second lis+addi pair, closest to the add)
    base_addr = None
    base_search_end = None  # offset of the lis that starts the base computation

    i = add_offset - 4
    while i >= add_offset - 48:
        d = decode_insn(data, i)
        # Look for addi r12, r12, SIMM
        if d['opcode'] == 14 and d['rd'] == 12 and d['ra'] == 12:
            addi_val = d['simm']
            # Find the preceding lis r12, SIMM (possibly with nop in between)
            j = i - 4
            while j >= i - 24:
                d2 = decode_insn(data, j)
                if d2['opcode'] == 15 and d2['rd'] == 12 and d2['ra'] == 0:  # lis r12
                    lis_val = sign_extend_16(d2['uimm']) << 16
                    base_addr = (lis_val + addi_val) & 0xFFFFFFFF
                    base_search_end = j
                    break
                elif d2['raw'] == 0x60000000:  # nop
                    j -= 4
                    continue
                else:
                    break
            break
        elif d['raw'] == 0x60000000:  # nop
            i -= 4
            continue
        else:
            break
        i -= 4

    if base_addr is None:
        return None

    # Step 2: Find lhzx/lbzx (table load instruction) before the base computation
    entry_type = None
    load_index_reg = None  # register used as index in the load
    load_offset = None
    entry_scale = 1

    i = base_search_end - 4
    while i >= base_search_end - 48:
        d = decode_insn(data, i)
        if d['opcode'] == 31:
            xo = d['xo_10']
            if xo == 279 and d['rd'] == 0 and d['ra'] == 12:  # lhzx r0, r12, rB
                entry_type = 'u16'
                load_index_reg = d['rb']
                load_offset = i
                break
            elif xo == 87 and d['rd'] == 0 and d['ra'] == 12:  # lbzx r0, r12, rB
                entry_type = 'u8'
                load_index_reg = d['rb']
                load_offset = i
                break
        # Skip rlwinm, addi, lis, nop etc.
        i -= 4

    if entry_type is None:
        return None

    # Step 3: Check for post-load scaling (between lbzx and add r12,r12,r0)
    # For lbzx tables, there might be rlwinm r0,r0,2,0,29 (multiply by 4)
    if entry_type == 'u8':
        for k in range(load_offset + 4, add_offset, 4):
            d = decode_insn(data, k)
            if d['opcode'] == 21:  # rlwinm
                rs = d['rd']  # source register (bits 21-25 for rlwinm is rS)
                # Actually for rlwinm: rA = bits 16-20, rS = bits 21-25
                rs = (d['raw'] >> 21) & 0x1F
                ra = (d['raw'] >> 16) & 0x1F
                sh = d['sh']
                mb = d['mb']
                me = d['me']
                if rs == 0 and ra == 0 and sh == 2 and mb == 0 and me == 29:
                    entry_scale = 4
                    break

    # Step 4: Find the table address (first lis+addi pair, before the load)
    table_addr = None
    table_search_start = load_offset

    i = load_offset - 4
    while i >= load_offset - 48:
        d = decode_insn(data, i)
        if d['opcode'] == 14 and d['rd'] == 12 and d['ra'] == 12:  # addi r12, r12, SIMM
            addi_val = d['simm']
            j = i - 4
            while j >= i - 40:
                d2 = decode_insn(data, j)
                if d2['opcode'] == 15 and d2['rd'] == 12 and d2['ra'] == 0:  # lis r12
                    lis_val = sign_extend_16(d2['uimm']) << 16
                    table_addr = (lis_val + addi_val) & 0xFFFFFFFF
                    table_search_start = j
                    break
                elif d['raw'] == 0x60000000:  # nop
                    j -= 4
                    continue
                else:
                    j -= 4
                    continue
            break
        elif d['raw'] == 0x60000000:  # nop
            i -= 4
            continue
        # Also skip rlwinm that scales the index
        elif d['opcode'] == 21:
            i -= 4
            continue
        else:
            i -= 4
            continue

    if table_addr is None:
        return None

    # Step 5: Find the actual index register
    # For u16 tables: look for rlwinm rX, rN, 1, 0, 30 before the load (scales index by 2)
    # The actual switch register is rN
    # For u8 tables: the index register is directly the one used in lbzx
    actual_index_reg = load_index_reg

    if entry_type == 'u16':
        # The load_index_reg is the scaled register (r0 typically)
        # Look for rlwinm r0, rN, 1, 0, 30
        for k in range(load_offset - 4, table_search_start - 4, -4):
            d = decode_insn(data, k)
            if d['opcode'] == 21:  # rlwinm
                rs = (d['raw'] >> 21) & 0x1F
                ra = (d['raw'] >> 16) & 0x1F
                sh = d['sh']
                mb = d['mb']
                me = d['me']
                if ra == load_index_reg and sh == 1 and mb == 0 and me == 30:
                    actual_index_reg = rs
                    break

    # Step 6: Determine table size from bounds checking
    # Look backward from the table setup for cmplwi + bgt/bge/bgtlr/bgelr or clrlwi
    # Strategy: find BOTH clrlwi (mask) and cmplwi (bounds check), prefer cmplwi
    table_size = None
    clrlwi_size = None  # from mask instruction

    def check_branch_gt_or_ge(data, branch_offset):
        """Check if instruction at branch_offset is bgt/bge/bgtlr/bgelr. Returns (type, None) or None."""
        d_br = decode_insn(data, branch_offset)
        opcode = d_br['opcode']
        bo = (d_br['raw'] >> 21) & 0x1F
        bi = (d_br['raw'] >> 16) & 0x1F
        bi_cond = bi & 3  # 0=lt, 1=gt, 2=eq

        # bc (opcode 16) - conditional branch to offset
        # bclr (opcode 19, XO=16) - conditional branch to LR (bgtlr, bgelr, etc.)
        if opcode == 16 or (opcode == 19 and ((d_br['raw'] >> 1) & 0x3FF) == 16):
            if bi_cond == 1 and (bo & 0x0C) == 0x0C:  # bgt / bgtlr
                return 'gt'
            if bi_cond == 0 and (bo & 0x0C) == 0x04:  # bge / bgelr
                return 'ge'
        return None

    # Search backward from the table area (extended range for complex functions)
    search_start = table_search_start
    for k in range(search_start - 4, max(search_start - 400, 0), -4):
        d = decode_insn(data, k)

        # clrlwi rA, rS, N = rlwinm rA, rS, 0, N, 31 (mask to lower bits)
        if d['opcode'] == 21:
            rs = (d['raw'] >> 21) & 0x1F
            ra = (d['raw'] >> 16) & 0x1F
            sh = d['sh']
            mb = d['mb']
            me = d['me']
            if sh == 0 and me == 31 and (ra == actual_index_reg or rs == actual_index_reg):
                if clrlwi_size is None:  # Only keep first (closest to switch)
                    mask_bits = 32 - mb
                    clrlwi_size = 1 << mask_bits
                # Don't break - keep looking for a tighter cmplwi bound
                continue

        # cmplwi crN, rA, UIMM (opcode 10)
        if d['opcode'] == 10:
            ra = d['ra']
            uimm = d['uimm']
            if ra == actual_index_reg:
                br_type = check_branch_gt_or_ge(data, k + 4)
                if br_type == 'gt':
                    table_size = uimm + 1
                    break
                elif br_type == 'ge':
                    table_size = uimm
                    break

        # cmpwi (opcode 11) - signed compare
        if d['opcode'] == 11:
            ra = d['ra']
            simm = d['simm']
            if ra == actual_index_reg and simm >= 0:
                br_type = check_branch_gt_or_ge(data, k + 4)
                if br_type == 'gt':
                    table_size = simm + 1
                    break

    # Use clrlwi size as fallback if no cmplwi was found
    if table_size is None and clrlwi_size is not None:
        table_size = clrlwi_size

    if table_size is None:
        # Fallback: try to infer from table data
        # Read entries until we get unreasonable targets
        table_file_off = (table_addr - PE_BASE)
        max_reasonable = 512
        table_size = 0
        for idx in range(max_reasonable):
            if entry_type == 'u16':
                off = table_file_off + idx * 2
                if off + 2 > len(data):
                    break
                entry_val = read_u16_be(data, off)
            else:
                off = table_file_off + idx
                if off + 1 > len(data):
                    break
                entry_val = read_u8(data, off)

            target = (base_addr + entry_val * entry_scale) & 0xFFFFFFFF
            # Check if target is in code range and 4-byte aligned (PPC instructions)
            if target < 0x82000000 or target >= 0x82300000:
                break
            if (target & 3) != 0:
                break
            table_size = idx + 1

        if table_size == 0:
            table_size = 1  # At least 1 entry

    return {
        'table_addr': table_addr,
        'base_addr': base_addr,
        'entry_type': entry_type,
        'entry_scale': entry_scale,
        'index_reg': actual_index_reg,
        'table_size': table_size,
    }


def main():
    pe_file = PE_FILE
    if len(sys.argv) > 1:
        pe_file = sys.argv[1]

    with open(pe_file, 'rb') as f:
        data = f.read()

    print(f"# Loaded {len(data)} bytes from {pe_file}")
    print(f"# Scanning for switch table pattern: add r12,r12,r0; mtctr r12; bctr")
    print()

    # Manual overrides for tables where auto-detection fails
    # (bounds check too far away, uses bgtlr, or no explicit bounds check)
    SIZE_OVERRIDES = {
        0x82140EB0: 29,   # inflate: state 0-28, no bounds check (struct field)
        0x82147BC0: 30,   # cmplwi cr6,r11,29 + bgtlr cr6
        0x820B53D8: 241,  # cmplwi cr6,r10,240 + bgt cr6
        0x820B4FDC: 188,  # cmplwi cr6,r3,187 + bgt cr6
    }

    # Cross-function switches: bctr is in a small trampoline function but targets
    # are in a different (larger) function. XenonRecomp can't generate goto for
    # cross-function jumps, so exclude these and let PPC_CALL_INDIRECT_FUNC handle them.
    EXCLUDE_BCTRS = {
        0x820D6660,   # targets in sub_820D6664
        0x82147BC0,   # targets in sub_82147BC4
        0x821499E4,   # targets in sub_821499E8
        0x8214B160,   # targets in sub_8214B164
        0x8214B314,   # targets in sub_8214B318
        0x82257B60,   # targets in sub_82257B64
    }

    switches = []
    pos = 0
    while True:
        idx = data.find(PATTERN, pos)
        if idx == -1:
            break

        add_offset = idx
        bctr_offset = idx + 8
        bctr_addr = bctr_offset + PE_BASE

        # Verify this is within code range
        if bctr_addr < 0x82000000 or bctr_addr >= 0x82300000:
            pos = idx + 4
            continue

        # Skip cross-function switches
        if bctr_addr in EXCLUDE_BCTRS:
            pos = idx + 12
            continue

        info = find_switch_info(data, add_offset)

        # Apply manual size override if available
        if info and bctr_addr in SIZE_OVERRIDES:
            info['table_size'] = SIZE_OVERRIDES[bctr_addr]

        if info:
            # Read table entries and compute target addresses
            table_file_off = info['table_addr'] - PE_BASE
            labels = []
            for i in range(info['table_size']):
                if info['entry_type'] == 'u16':
                    entry_val = read_u16_be(data, table_file_off + i * 2)
                else:
                    entry_val = read_u8(data, table_file_off + i)
                target = (info['base_addr'] + entry_val * info['entry_scale']) & 0xFFFFFFFF
                labels.append(target)

            switches.append({
                'bctr_addr': bctr_addr,
                'info': info,
                'labels': labels,
            })
        else:
            switches.append({
                'bctr_addr': bctr_addr,
                'error': 'Could not parse switch table info',
            })

        pos = idx + 12

    # Output TOML
    print(f"# Auto-generated switch tables for Crazy Taxi (XBLA)")
    print(f"# Found {len(switches)} switch table sites")
    print()

    errors = 0
    for sw in switches:
        if 'error' in sw:
            print(f"# ERROR at bctr=0x{sw['bctr_addr']:08X}: {sw['error']}")
            errors += 1
            continue

        info = sw['info']
        print(f"[[switch]]")
        print(f"base = 0x{sw['bctr_addr']:08X}")
        print(f"r = {info['index_reg']}")

        # Format labels array
        labels_strs = [f"0x{l:08X}" for l in sw['labels']]
        if len(labels_strs) <= 8:
            print(f"labels = [{', '.join(labels_strs)}]")
        else:
            # Multi-line for readability
            print(f"labels = [")
            for i in range(0, len(labels_strs), 8):
                chunk = labels_strs[i:i+8]
                comma = "," if i + 8 < len(labels_strs) else ""
                print(f"    {', '.join(chunk)}{comma}")
            print(f"]")

        print(f"# table=0x{info['table_addr']:08X} base_ref=0x{info['base_addr']:08X} type={info['entry_type']} scale={info['entry_scale']} size={info['table_size']}")
        print()

    print(f"# Summary: {len(switches)} total, {len(switches) - errors} parsed, {errors} errors")

    return 0 if errors == 0 else 1


if __name__ == '__main__':
    main()
