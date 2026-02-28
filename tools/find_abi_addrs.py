#!/usr/bin/env python3
"""
Find Xbox 360 ABI register save/restore function addresses in the decompressed
PE image extracted from a Vigilante 8 Arcade XEX file.

These are standard PowerPC ABI helper functions present in every Xbox 360 game:
  - __savegprlr_14 / __restgprlr_14
  - __savefpr_14   / __restfpr_14
  - __savevmx_14   / __restvmx_14
  - __savevmx_64   / __restvmx_64
  - setjmp / longjmp

The Xbox 360 is a 32-bit PowerPC system, but it uses 64-bit std/ld instructions
for GPR save/restore. Key observations:
  - GPR save/restore uses std/ld with base register r1
  - FPR save/restore uses stfd/lfd with base register r12
  - VMX 14-31 save/restore uses addi r11 + stvx/lvx with r12 as base
  - VMX 64-127 save/restore uses addi r11 + stvx128/lvx128 (opcode 4) with r12
  - The LR is saved/restored via stw/lwz r12 (32-bit)
  - Stack offsets: -(32-reg)*8 - 8 for GPR, -(32-reg)*8 for FPR

Usage: py find_abi_addrs.py
"""

import struct
import os
import subprocess
import sys

# ============================================================================
# Constants
# ============================================================================

BASE_ADDR = 0x82000000

XEX_PATH = r"E:\vig8\extracted\default.xex"
PE_PATH  = r"E:\vig8\tools\default_pe.bin"
EXTRACT_EXE = r"E:\vig8\extract_pe.exe"


# ============================================================================
# Helpers
# ============================================================================

def insn_bytes(val):
    return struct.pack('>I', val)

def read_insn(data, offset):
    return struct.unpack_from('>I', data, offset)[0]


# ============================================================================
# Search Functions
# ============================================================================

def find_savegprlr_14(data):
    """Find __savegprlr_14.

    Pattern (18 instructions):
      std r14, -152(r1)   ; offset = -(32-14)*8 - 8 = -152
      std r15, -144(r1)
      ...
      std r31, -16(r1)
      stw r12, -8(r1)     ; save LR (32-bit store)
      blr

    We search for the first 4 std instructions as a key.
    """
    key = b''
    for reg in range(14, 18):
        offset = -(32 - reg) * 8 - 8
        insn = (62 << 26) | (reg << 21) | (1 << 16) | (offset & 0xFFFF)
        key += struct.pack('>I', insn)

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break
        # Verify full r14..r31 sequence
        ok = True
        for reg in range(18, 32):
            pos = idx + (reg - 14) * 4
            expected_offset = -(32 - reg) * 8 - 8
            expected = (62 << 26) | (reg << 21) | (1 << 16) | (expected_offset & 0xFFFF)
            if read_insn(data, pos) != expected:
                ok = False
                break
        if ok:
            # Check: stw r12, -8(r1) follows
            stw_pos = idx + 18 * 4
            stw_expected = (36 << 26) | (12 << 21) | (1 << 16) | ((-8) & 0xFFFF)
            if read_insn(data, stw_pos) == stw_expected:
                # Check: blr follows
                blr_pos = stw_pos + 4
                if read_insn(data, blr_pos) == 0x4E800020:
                    results.append(idx)
        idx += 4

    return results


def find_restgprlr_14(data):
    """Find __restgprlr_14.

    Pattern (18 + 3 instructions):
      ld r14, -152(r1)
      ...
      ld r31, -16(r1)
      lwz r12, -8(r1)    ; restore LR
      mtlr r12
      blr
    """
    key = b''
    for reg in range(14, 18):
        offset = -(32 - reg) * 8 - 8
        insn = (58 << 26) | (reg << 21) | (1 << 16) | (offset & 0xFFFF)
        key += struct.pack('>I', insn)

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break
        ok = True
        for reg in range(18, 32):
            pos = idx + (reg - 14) * 4
            expected_offset = -(32 - reg) * 8 - 8
            expected = (58 << 26) | (reg << 21) | (1 << 16) | (expected_offset & 0xFFFF)
            if read_insn(data, pos) != expected:
                ok = False
                break
        if ok:
            # Check: lwz r12, -8(r1)
            lwz_pos = idx + 18 * 4
            lwz_expected = (32 << 26) | (12 << 21) | (1 << 16) | ((-8) & 0xFFFF)
            if read_insn(data, lwz_pos) == lwz_expected:
                # mtlr r12
                mtlr_pos = lwz_pos + 4
                mtlr_expected = 0x7D8803A6  # mtlr r12
                if read_insn(data, mtlr_pos) == mtlr_expected:
                    # blr
                    blr_pos = mtlr_pos + 4
                    if read_insn(data, blr_pos) == 0x4E800020:
                        results.append(idx)
        idx += 4

    return results


def find_savefpr_14(data):
    """Find __savefpr_14.

    Pattern: stfd f14..f31, -(32-reg)*8(r12), then blr.
    Base register is r12, not r1!
    Offsets: -(32-reg)*8 for each FPR.
    f14 at -144, f15 at -136, ..., f31 at -8.
    """
    key = b''
    for reg in range(14, 18):
        offset = -(32 - reg) * 8
        insn = (54 << 26) | (reg << 21) | (12 << 16) | (offset & 0xFFFF)
        key += struct.pack('>I', insn)

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break
        ok = True
        for reg in range(18, 32):
            pos = idx + (reg - 14) * 4
            expected_offset = -(32 - reg) * 8
            expected = (54 << 26) | (reg << 21) | (12 << 16) | (expected_offset & 0xFFFF)
            if read_insn(data, pos) != expected:
                ok = False
                break
        if ok:
            blr_pos = idx + 18 * 4
            if read_insn(data, blr_pos) == 0x4E800020:
                results.append(idx)
        idx += 4

    return results


def find_restfpr_14(data):
    """Find __restfpr_14.

    Pattern: lfd f14..f31, -(32-reg)*8(r12), then blr.
    """
    key = b''
    for reg in range(14, 18):
        offset = -(32 - reg) * 8
        insn = (50 << 26) | (reg << 21) | (12 << 16) | (offset & 0xFFFF)
        key += struct.pack('>I', insn)

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break
        ok = True
        for reg in range(18, 32):
            pos = idx + (reg - 14) * 4
            expected_offset = -(32 - reg) * 8
            expected = (50 << 26) | (reg << 21) | (12 << 16) | (expected_offset & 0xFFFF)
            if read_insn(data, pos) != expected:
                ok = False
                break
        if ok:
            blr_pos = idx + 18 * 4
            if read_insn(data, blr_pos) == 0x4E800020:
                results.append(idx)
        idx += 4

    return results


def find_savevmx_14(data):
    """Find __savevmx_14.

    Pattern: pairs of (addi r11, r0, offset ; stvx vrN, r11, r12) for vr14..vr31.
    Offsets: -(32-reg)*16 for each VMX register.
    vr14 at -288, vr15 at -272, ..., vr31 at -16.
    """
    key = b''
    for reg in range(14, 17):  # First 3 pairs as key
        offset = -(32 - reg) * 16
        addi = (14 << 26) | (11 << 21) | (0 << 16) | (offset & 0xFFFF)
        stvx = (31 << 26) | (reg << 21) | (11 << 16) | (12 << 11) | (231 << 1)
        key += struct.pack('>I', addi) + struct.pack('>I', stvx)

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break
        # Verify more pairs
        ok = True
        for i in range(3, 18):  # regs 17..31
            reg = 14 + i
            pos = idx + i * 8
            offset = -(32 - reg) * 16
            expected_addi = (14 << 26) | (11 << 21) | (0 << 16) | (offset & 0xFFFF)
            expected_stvx = (31 << 26) | (reg << 21) | (11 << 16) | (12 << 11) | (231 << 1)
            if pos + 8 > len(data):
                ok = False
                break
            if read_insn(data, pos) != expected_addi or read_insn(data, pos + 4) != expected_stvx:
                ok = False
                break
        if ok:
            # Check blr after all 18 pairs
            blr_pos = idx + 18 * 8
            if blr_pos + 4 <= len(data) and read_insn(data, blr_pos) == 0x4E800020:
                results.append(idx)
        idx += 4

    return results


def find_restvmx_14(data):
    """Find __restvmx_14.

    Pattern: pairs of (addi r11, r0, offset ; lvx vrN, r11, r12) for vr14..vr31.
    """
    key = b''
    for reg in range(14, 17):
        offset = -(32 - reg) * 16
        addi = (14 << 26) | (11 << 21) | (0 << 16) | (offset & 0xFFFF)
        lvx = (31 << 26) | (reg << 21) | (11 << 16) | (12 << 11) | (103 << 1)
        key += struct.pack('>I', addi) + struct.pack('>I', lvx)

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break
        ok = True
        for i in range(3, 18):
            reg = 14 + i
            pos = idx + i * 8
            offset = -(32 - reg) * 16
            expected_addi = (14 << 26) | (11 << 21) | (0 << 16) | (offset & 0xFFFF)
            expected_lvx = (31 << 26) | (reg << 21) | (11 << 16) | (12 << 11) | (103 << 1)
            if pos + 8 > len(data):
                ok = False
                break
            if read_insn(data, pos) != expected_addi or read_insn(data, pos + 4) != expected_lvx:
                ok = False
                break
        if ok:
            blr_pos = idx + 18 * 8
            if blr_pos + 4 <= len(data) and read_insn(data, blr_pos) == 0x4E800020:
                results.append(idx)
        idx += 4

    return results


def find_savevmx_64(data):
    """Find __savevmx_64.

    Pattern: 64 pairs of (addi r11, r0, offset ; stvx128 vrN, r11, r12) for vr64..vr127.
    Offsets: -(128-reg)*16 for each VMX128 register. vr64 at -1024, vr65 at -1008, ...

    The stvx128 instruction uses primary opcode 4 (not 31).
    From the binary, the first stvx128 at 0x82311858 is 0x100B61CB.

    Let me decode: 0x100B61CB
    opcode = 0x04 (bits 0-5 = 000100)
    Then it's a VMX128 instruction form.

    The Xbox 360 VMX128 encoding for stvx128/stvrx128:
    The pattern we see is: addi r11, r0, -1024 ; <0x100B61CB>
    And for next: addi r11, r0, -1008 ; <0x102B61CB>

    The VD field (bits 6-10) changes: 0x10_0B = VD=0 (vr64), 0x10_2B = VD=1 (vr65).
    The constant part is 0x000B61CB masked against non-VD bits.
    Actually: 0x100B61CB = 000100 00000 01011 01100 0011100 1011
    It's: primary=4, VD128l=0, then some fields.

    For the key, let's just search for the first addi + opcode4 pairs.
    """
    # First instruction: addi r11, r0, -1024
    first_addi = (14 << 26) | (11 << 21) | (0 << 16) | ((-1024) & 0xFFFF)
    # Second instruction: the stvx128 for vr64 = 0x100B61CB
    # Third instruction: addi r11, r0, -1008
    second_addi = (14 << 26) | (11 << 21) | (0 << 16) | ((-1008) & 0xFFFF)
    # Fourth instruction: stvx128 for vr65 = 0x102B61CB

    key = struct.pack('>I', first_addi)
    # We expect the stvx128 after, but we don't know the exact encoding
    # So search for the addi pattern and verify the structure

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break

        # Check if this is followed by an opcode-4 instruction
        if idx + 8 > len(data):
            idx += 4
            continue

        w2 = read_insn(data, idx + 4)
        if (w2 >> 26) != 4:
            idx += 4
            continue

        # Check next addi
        if idx + 12 > len(data):
            idx += 4
            continue

        w3 = read_insn(data, idx + 8)
        if w3 != struct.unpack('>I', struct.pack('>I', second_addi))[0]:
            idx += 4
            continue

        w4 = read_insn(data, idx + 12)
        if (w4 >> 26) != 4:
            idx += 4
            continue

        # Verify pattern continues: count consecutive addi+op4 pairs
        pairs = 0
        for i in range(64):
            pos = idx + i * 8
            if pos + 8 > len(data):
                break
            wa = read_insn(data, pos)
            wb = read_insn(data, pos + 4)
            if (wa >> 26) == 14 and (wb >> 26) == 4:
                pairs += 1
            else:
                break

        if pairs >= 32:  # At least 32 pairs (half of 64 VMX128 regs)
            results.append((idx, pairs))

        idx += 4

    return results


def find_restvmx_64(data):
    """Find __restvmx_64.

    Same structure as savevmx_64 but with lvx128 (different opcode-4 encoding).
    From the binary: 0x100B60CB for lvx128 vr64 vs 0x100B61CB for stvx128 vr64.
    The difference is bit pattern: 61CB vs 60CB. Bit 8 differs (store vs load).
    """
    first_addi = (14 << 26) | (11 << 21) | (0 << 16) | ((-1024) & 0xFFFF)
    second_addi = (14 << 26) | (11 << 21) | (0 << 16) | ((-1008) & 0xFFFF)
    key = struct.pack('>I', first_addi)

    results = []
    idx = 0
    while True:
        idx = data.find(key, idx)
        if idx == -1:
            break

        if idx + 12 > len(data):
            idx += 4
            continue

        w2 = read_insn(data, idx + 4)
        if (w2 >> 26) != 4:
            idx += 4
            continue

        w3 = read_insn(data, idx + 8)
        w4 = read_insn(data, idx + 12) if idx + 16 <= len(data) else 0

        if w3 != struct.unpack('>I', struct.pack('>I', second_addi))[0]:
            idx += 4
            continue

        if (w4 >> 26) != 4:
            idx += 4
            continue

        # Distinguish save vs restore by checking the opcode-4 instruction
        # Save (stvx128) has the store bit set, restore (lvx128) doesn't
        # From binary: save=0x100B61CB, restore=0x100B60CB
        # Bit 8 (from LSB): 61CB has bit 8 set, 60CB doesn't

        pairs = 0
        for i in range(64):
            pos = idx + i * 8
            if pos + 8 > len(data):
                break
            wa = read_insn(data, pos)
            wb = read_insn(data, pos + 4)
            if (wa >> 26) == 14 and (wb >> 26) == 4:
                pairs += 1
            else:
                break

        if pairs >= 32:
            results.append((idx, pairs, w2))

        idx += 4

    return results


def find_setjmp(data):
    """Find setjmp. Searches for a function that stores many registers to a
    buffer pointed to by r3 using stw instructions.

    Returns None if not found (some games don't use setjmp/longjmp).
    """
    # Search for stw r1, 0(r3) (common setjmp start)
    pattern = struct.pack('>I', (36 << 26) | (1 << 21) | (3 << 16) | 0)
    results = []
    idx = 0
    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break
        # Count stores to r3 in the next 50 instructions
        stores = 0
        for k in range(1, 50):
            pos = idx + k * 4
            if pos + 4 > len(data):
                break
            w = read_insn(data, pos)
            if (w >> 26) == 36 and ((w >> 16) & 0x1F) == 3:
                stores += 1
        if stores >= 15:
            results.append(idx)
        idx += 4
    return results


def find_longjmp(data):
    """Find longjmp. Searches for a function that loads many registers from r3."""
    # Search for lwz r1, 0(r3)
    pattern = struct.pack('>I', (32 << 26) | (1 << 21) | (3 << 16) | 0)
    results = []
    idx = 0
    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break
        loads = 0
        for k in range(1, 50):
            pos = idx + k * 4
            if pos + 4 > len(data):
                break
            w = read_insn(data, pos)
            if (w >> 26) == 32 and ((w >> 16) & 0x1F) == 3:
                loads += 1
        if loads >= 15:
            results.append(idx)
        idx += 4
    return results


# ============================================================================
# Main
# ============================================================================

def main():
    # Ensure PE is extracted
    if not os.path.exists(PE_PATH):
        print("PE binary not found at %s" % PE_PATH)
        if os.path.exists(EXTRACT_EXE):
            print("Extracting PE from XEX...")
            result = subprocess.run(
                [EXTRACT_EXE, XEX_PATH, PE_PATH],
                capture_output=True, text=True
            )
            print(result.stdout)
            if result.returncode != 0:
                print("ERROR: %s" % result.stderr)
                return
        else:
            print("ERROR: extract_pe.exe not found. Build it first.")
            return

    print("Loading PE image: %s" % PE_PATH)
    with open(PE_PATH, 'rb') as f:
        pe_data = f.read()

    print("PE size: %d bytes (0x%X)" % (len(pe_data), len(pe_data)))
    print("Base address: 0x%08X" % BASE_ADDR)

    if pe_data[0:2] == b'MZ':
        print("Valid PE header (MZ)\n")
    else:
        print("WARNING: No MZ header\n")

    print("=" * 70)
    print("SCANNING FOR ABI FUNCTIONS")
    print("=" * 70)

    results = {}

    # --- savegprlr_14 ---
    print("\n[1/10] __savegprlr_14")
    matches = find_savegprlr_14(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['savegprlr_14'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND")

    # --- restgprlr_14 ---
    print("\n[2/10] __restgprlr_14")
    matches = find_restgprlr_14(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['restgprlr_14'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND")

    # --- savefpr_14 ---
    print("\n[3/10] __savefpr_14")
    matches = find_savefpr_14(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['savefpr_14'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND")

    # --- restfpr_14 ---
    print("\n[4/10] __restfpr_14")
    matches = find_restfpr_14(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['restfpr_14'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND")

    # --- savevmx_14 ---
    print("\n[5/10] __savevmx_14")
    matches = find_savevmx_14(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['savevmx_14'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND")

    # --- restvmx_14 ---
    print("\n[6/10] __restvmx_14")
    matches = find_restvmx_14(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['restvmx_14'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND")

    # --- savevmx_64 and restvmx_64 ---
    # These share the same addi pattern; we need to distinguish store vs load
    print("\n[7/10] __savevmx_64")
    print("[8/10] __restvmx_64")

    # Find all addi+opcode4 sequences
    all_vmx128 = find_restvmx_64(pe_data)

    # Separate save from restore based on the opcode-4 instruction encoding
    # Save stvx128 first word: 0x100B61CB (bit 8 set = 0x100)
    # Rest lvx128 first word: 0x100B60CB (bit 8 clear)
    save64_found = False
    rest64_found = False
    for idx, pairs, first_op4 in all_vmx128:
        # Check bit 8 of the opcode-4 instruction
        is_store = (first_op4 >> 8) & 1
        addr = BASE_ADDR + idx
        if is_store and not save64_found:
            results['savevmx_64'] = addr
            print("  savevmx_64 FOUND at 0x%08X (offset 0x%X, %d pairs)" % (addr, idx, pairs))
            save64_found = True
        elif not is_store and not rest64_found:
            results['restvmx_64'] = addr
            print("  restvmx_64 FOUND at 0x%08X (offset 0x%X, %d pairs)" % (addr, idx, pairs))
            rest64_found = True

    if not save64_found:
        # Try savevmx_64 separately
        matches = find_savevmx_64(pe_data)
        if matches:
            # Need to distinguish from restore
            for idx, pairs in matches:
                # Check if this is same as a rest match
                w2 = read_insn(pe_data, idx + 4)
                is_store = (w2 >> 8) & 1
                if is_store:
                    addr = BASE_ADDR + idx
                    results['savevmx_64'] = addr
                    print("  savevmx_64 FOUND at 0x%08X (offset 0x%X, %d pairs)" % (addr, idx, pairs))
                    save64_found = True
                    break

    if not save64_found:
        print("  savevmx_64 NOT FOUND")
    if not rest64_found:
        print("  restvmx_64 NOT FOUND")

    # --- setjmp ---
    print("\n[9/10] setjmp")
    matches = find_setjmp(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['setjmp'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND (game may not use setjmp)")

    # --- longjmp ---
    print("\n[10/10] longjmp")
    matches = find_longjmp(pe_data)
    if matches:
        addr = BASE_ADDR + matches[0]
        results['longjmp'] = addr
        print("  FOUND at 0x%08X (offset 0x%X)" % (addr, matches[0]))
    else:
        print("  NOT FOUND (game may not use longjmp)")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    toml_keys = [
        ('savegprlr_14', 'savegprlr_14_address'),
        ('restgprlr_14', 'restgprlr_14_address'),
        ('savefpr_14',   'savefpr_14_address'),
        ('restfpr_14',   'restfpr_14_address'),
        ('savevmx_14',   'savevmx_14_address'),
        ('restvmx_14',   'restvmx_14_address'),
        ('savevmx_64',   'savevmx_64_address'),
        ('restvmx_64',   'restvmx_64_address'),
        ('setjmp',       'setjmp_address'),
        ('longjmp',      'longjmp_address'),
    ]

    found = sum(1 for k, _ in toml_keys if k in results)
    print("\nFound %d/%d functions\n" % (found, len(toml_keys)))

    print("TOML config snippet:")
    print("-" * 50)
    for name, toml_key in toml_keys:
        if name in results:
            print('%s = 0x%08X' % (toml_key, results[name]))
        else:
            print('# %s = NOT FOUND' % toml_key)
    print("-" * 50)

    return results


if __name__ == '__main__':
    main()
