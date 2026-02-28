#!/usr/bin/env python3
"""
Extract and decrypt the PE image from an Xbox 360 XEX2 file.

Based on XenonRecomp's XEX loading implementation (XenonUtils/xex.cpp).

XEX2 encryption:
  1. A per-file AES key is stored at security_info + 0x150, encrypted with retail key
  2. The retail key decrypts the file key using AES-CBC with a zero IV
  3. The file key decrypts the PE data (from pe_data_offset to EOF) using AES-CBC with zero IV

XEX2 basic block compression:
  Block descriptors are in the file format info (after the 8-byte header).
  Each block: { data_size(4), zero_size(4) }
  Terminated by {0, 0}.

Usage: python extract_pe.py <input.xex> <output.bin>
"""

import struct
import sys

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        print("ERROR: pycryptodome is required. Install with: pip install pycryptodome")
        sys.exit(1)


# Xbox 360 retail AES key for XEX2 decryption
XEX2_RETAIL_KEY = bytes([
    0x20, 0xB1, 0x85, 0xA5, 0x9D, 0x28, 0xFD, 0xC3,
    0x40, 0x58, 0x3F, 0xBB, 0x08, 0x96, 0xBF, 0x91
])
AES_BLANK_IV = b'\x00' * 16

# Security info offsets (from XenonRecomp's Xex2SecurityInfo struct)
SEC_AES_KEY_OFFSET = 0x150  # 16 bytes, encrypted with retail key


def read_be32(data, off):
    return struct.unpack('>I', data[off:off+4])[0]

def read_be16(data, off):
    return struct.unpack('>H', data[off:off+2])[0]


def decrypt_xex2(xex_path, output_path):
    with open(xex_path, 'rb') as f:
        data = bytearray(f.read())

    # Validate magic
    if data[0:4] != b'XEX2':
        print(f"ERROR: Not a XEX2 file (magic: {bytes(data[0:4])})")
        return False

    pe_data_offset = read_be32(data, 8)
    sec_info_offset = read_be32(data, 16)
    opt_header_count = read_be32(data, 20)

    print(f"XEX2 file: {len(data)} bytes")
    print(f"  PE data offset: 0x{pe_data_offset:X}")
    print(f"  Security info: 0x{sec_info_offset:X}")
    print(f"  Optional headers: {opt_header_count}")

    # Parse optional headers
    ffi_offset = 0
    entry_point = 0
    image_base = 0
    pos = 24
    for i in range(opt_header_count):
        hdr_id = read_be32(data, pos)
        hdr_val = read_be32(data, pos + 4)
        key_id = (hdr_id >> 8) & 0xFFFFFF

        if key_id == 0x000003:  # File format info
            ffi_offset = hdr_val
        elif key_id == 0x000101:  # Entry point
            entry_point = hdr_val
        elif key_id == 0x000102:  # Image base address
            image_base = hdr_val
        pos += 8

    print(f"  Entry point: 0x{entry_point:08X}")
    print(f"  Image base: 0x{image_base:08X}")

    # Read file format info
    if not ffi_offset:
        print("ERROR: File format info header not found")
        return False

    ffi_size = read_be32(data, ffi_offset)
    enc_type = read_be16(data, ffi_offset + 4)
    comp_type = read_be16(data, ffi_offset + 6)

    enc_names = {0: 'None', 1: 'Normal'}
    comp_names = {0: 'None', 1: 'Basic', 2: 'Normal (LZX)', 3: 'Delta'}
    print(f"  Encryption: {enc_names.get(enc_type, f'Unknown({enc_type})')}")
    print(f"  Compression: {comp_names.get(comp_type, f'Unknown({comp_type})')}")

    # Read image size from security info
    image_size = read_be32(data, sec_info_offset + 4)
    load_address = read_be32(data, sec_info_offset + 0x110)
    print(f"  Image size: 0x{image_size:X} ({image_size} bytes)")
    print(f"  Load address: 0x{load_address:08X}")

    # Step 1: Decrypt the file key
    enc_key = bytes(data[sec_info_offset + SEC_AES_KEY_OFFSET:
                         sec_info_offset + SEC_AES_KEY_OFFSET + 16])
    print(f"\n  Encrypted file key: {enc_key.hex()}")

    if enc_type == 1:  # Normal encryption
        cipher = AES.new(XEX2_RETAIL_KEY, AES.MODE_CBC, AES_BLANK_IV)
        file_key = cipher.decrypt(enc_key)
        print(f"  Decrypted file key: {file_key.hex()}")
    else:
        file_key = None
        print("  No encryption")

    # Step 2: Decrypt the PE data (everything from pe_data_offset onward)
    raw_pe_data = bytes(data[pe_data_offset:])
    if file_key:
        # Pad to 16-byte boundary for AES
        pad_len = (16 - (len(raw_pe_data) % 16)) % 16
        if pad_len:
            raw_pe_data += b'\x00' * pad_len
        cipher = AES.new(file_key, AES.MODE_CBC, AES_BLANK_IV)
        decrypted_data = cipher.decrypt(raw_pe_data)
        print(f"  Decrypted {len(decrypted_data)} bytes")
    else:
        decrypted_data = raw_pe_data

    print(f"  First 32 bytes: {' '.join(f'{b:02X}' for b in decrypted_data[:32])}")

    # Step 3: Decompress
    if comp_type == 1:  # Basic block compression
        print("\nDecompressing basic blocks...")

        # Read block descriptors from file format info
        # Each block is 8 bytes: data_size(4) + zero_size(4)
        # Located right after the 8-byte FFI header (size, enc_type, comp_type)
        blocks = []
        block_pos = ffi_offset + 8
        while block_pos + 8 <= ffi_offset + ffi_size:
            data_size = read_be32(data, block_pos)
            zero_size = read_be32(data, block_pos + 4)
            if data_size == 0 and zero_size == 0:
                break
            blocks.append((data_size, zero_size))
            block_pos += 8

        print(f"  Found {len(blocks)} compression blocks")
        for i, (ds, zs) in enumerate(blocks):
            print(f"    Block[{i}]: data={ds} (0x{ds:X}), zero={zs} (0x{zs:X})")

        # Calculate total image size from blocks
        total_size = sum(ds + zs for ds, zs in blocks)
        print(f"  Total image size from blocks: 0x{total_size:X}")

        pe_image = bytearray(max(image_size, total_size))
        src_pos = 0
        dst_pos = 0

        for i, (ds, zs) in enumerate(blocks):
            if src_pos + ds > len(decrypted_data):
                print(f"  Warning: block {i} overflow (src=0x{src_pos:X}, need {ds})")
                # Copy what we can
                avail = len(decrypted_data) - src_pos
                pe_image[dst_pos:dst_pos + avail] = decrypted_data[src_pos:src_pos + avail]
                dst_pos += avail + (ds - avail) + zs
                break
            pe_image[dst_pos:dst_pos + ds] = decrypted_data[src_pos:src_pos + ds]
            src_pos += ds
            dst_pos += ds
            # Zero fill (already zero from bytearray init)
            dst_pos += zs

        print(f"  Decompressed to {dst_pos} bytes")
        final_image = bytes(pe_image[:image_size])

    elif comp_type == 0:  # No compression
        final_image = decrypted_data[:image_size]
    else:
        print(f"  WARNING: Compression type {comp_type} not supported")
        final_image = decrypted_data[:image_size]

    # Step 4: Validate PE image
    print(f"\nValidating PE image ({len(final_image)} bytes)...")
    print(f"  First 32 bytes: {' '.join(f'{b:02X}' for b in final_image[:32])}")

    has_mz = final_image[0:2] == b'MZ'
    if has_mz:
        e_lfanew = struct.unpack('<I', final_image[0x3C:0x40])[0]
        print(f"  MZ header found, e_lfanew: 0x{e_lfanew:X}")
        pe_off = e_lfanew
    else:
        # Xbox 360 PE images may not have MZ header
        # Check if PE signature is at offset 0
        if final_image[0:4] == b'PE\x00\x00':
            print("  PE signature at offset 0 (no MZ header)")
            pe_off = 0
        else:
            print(f"  No MZ or PE header found. Checking common Xbox PE offsets...")
            # Try to find PE\0\0 signature
            pe_off = None
            for try_off in [0, 0x80, 0x100, 0x1000]:
                if try_off + 4 <= len(final_image) and final_image[try_off:try_off+4] == b'PE\x00\x00':
                    pe_off = try_off
                    print(f"  Found PE signature at offset 0x{try_off:X}")
                    break
            if pe_off is None:
                print("  WARNING: No PE signature found anywhere")
                # Write anyway for debugging
                with open(output_path, 'wb') as f:
                    f.write(final_image)
                print(f"\nWrote {len(final_image)} bytes to {output_path} (unvalidated)")
                return True

    # Parse PE sections
    coff_off = pe_off + 4 if has_mz or final_image[pe_off:pe_off+4] == b'PE\x00\x00' else pe_off
    if coff_off + 20 <= len(final_image):
        machine = struct.unpack('<H', final_image[coff_off:coff_off+2])[0]
        num_sections = struct.unpack('<H', final_image[coff_off+2:coff_off+4])[0]
        opt_hdr_size = struct.unpack('<H', final_image[coff_off+16:coff_off+18])[0]
        sec_table = coff_off + 20 + opt_hdr_size

        machine_names = {0x01F2: 'PowerPC (Xbox 360)', 0x1F2: 'PowerPC', 0x14C: 'x86', 0x8664: 'x64'}
        print(f"  Machine: 0x{machine:04X} ({machine_names.get(machine, 'Unknown')})")
        print(f"  Sections: {num_sections}")
        print(f"  Optional header size: {opt_hdr_size}")

        total_data_loaded = 0
        for i in range(num_sections):
            off = sec_table + i * 40
            if off + 40 > len(final_image):
                break
            name = final_image[off:off+8].rstrip(b'\x00').decode('ascii', errors='replace')
            vsize = struct.unpack('<I', final_image[off+8:off+12])[0]
            vaddr = struct.unpack('<I', final_image[off+12:off+16])[0]
            rsize = struct.unpack('<I', final_image[off+16:off+20])[0]
            roff = struct.unpack('<I', final_image[off+20:off+24])[0]
            chars = struct.unpack('<I', final_image[off+36:off+40])[0]
            is_code = bool(chars & 0x20)
            flags = []
            if chars & 0x20: flags.append('CODE')
            if chars & 0x40: flags.append('IDATA')
            if chars & 0x80: flags.append('UDATA')
            if chars & 0x20000000: flags.append('X')
            if chars & 0x40000000: flags.append('R')
            if chars & 0x80000000: flags.append('W')
            print(f"    {name:8s} VA=0x{image_base+vaddr:08X} VSize=0x{vsize:06X} "
                  f"Raw=0x{rsize:06X} @ 0x{roff:06X} [{','.join(flags)}]")
            if not is_code:
                total_data_loaded += min(rsize, vsize)
        print(f"  Total data section size: {total_data_loaded} bytes")

    # Write output
    with open(output_path, 'wb') as f:
        f.write(final_image)
    print(f"\nWrote {len(final_image)} bytes to {output_path}")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.xex> <output.bin>")
        sys.exit(1)
    if not decrypt_xex2(sys.argv[1], sys.argv[2]):
        sys.exit(1)
