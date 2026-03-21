#!/usr/bin/env python3
"""
XEX2 binary information dumper.
Parses XEX2 header and reports key details for static recompilation.
"""

import struct
import sys


def read_xex_info(xex_path):
    with open(xex_path, 'rb') as f:
        data = f.read()

    if data[:4] != b'XEX2':
        print("ERROR: Not a valid XEX2 file!")
        return

    module_flags = struct.unpack_from('>I', data, 0x04)[0]
    pe_offset = struct.unpack_from('>I', data, 0x08)[0]
    reserved = struct.unpack_from('>I', data, 0x0C)[0]
    security_offset = struct.unpack_from('>I', data, 0x10)[0]
    header_count = struct.unpack_from('>I', data, 0x14)[0]

    print("=" * 60)
    print("XEX2 Binary Analysis")
    print("=" * 60)
    print(f"File size:         {len(data)} bytes ({len(data) / 1024 / 1024:.1f} MB)")
    print(f"Module flags:      0x{module_flags:08X}")
    print(f"PE data offset:    0x{pe_offset:X}")
    print(f"Security offset:   0x{security_offset:X}")
    print(f"Header count:      {header_count}")

    # Security info
    if security_offset > 0 and security_offset + 0x200 < len(data):
        sec = data[security_offset:]
        sec_header_size = struct.unpack_from('>I', sec, 0x00)[0]
        image_size = struct.unpack_from('>I', sec, 0x04)[0]

        print(f"\nSecurity Info:")
        print(f"  Header size:     0x{sec_header_size:X}")
        print(f"  Image size:      0x{image_size:X} ({image_size / 1024 / 1024:.1f} MB)")

        # RSA signature at offset 0x08 (256 bytes)
        # Image hash at offset 0x108 (20 bytes = SHA1)
        # Import table count at offset 0x11C
        if sec_header_size >= 0x180:
            sha1_hash = sec[0x164:0x164 + 20]
            print(f"  SHA1 hash:       {sha1_hash.hex()}")

    # Parse optional headers
    print(f"\nOptional Headers:")
    oh_offset = 0x18
    entry_point = 0
    base_address = 0
    original_base = 0
    image_base = 0
    tls_info = None

    known_headers = {
        0x000002FF: "EXECUTION_INFO_TABLE",
        0x000003FF: "SYSTEM_FLAGS",
        0x00010100: "BOUNDING_PATH",
        0x00010201: "IMAGE_BASE_ADDRESS",
        0x000103FF: "IMPORT_LIBRARIES",
        0x00018002: "LAN_KEY",
        0x000183FF: "ORIGINAL_BASE_ADDRESS",
        0x000200FF: "BASE_REFERENCE",
        0x00020104: "DELTA_PATCH_DESCRIPTOR",
        0x00020200: "DEFAULT_HEAP_SIZE",
        0x00030000: "ENTRY_POINT",
        0x00040006: "TLS_INFO",
        0x00040310: "DEFAULT_STACK_SIZE",
        0x00040404: "DEFAULT_FILESYSTEM_CACHE_SIZE",
        0x000405FF: "STATIC_LIBRARIES",
    }

    for h in range(header_count):
        if oh_offset + 8 > len(data):
            break

        header_id = struct.unpack_from('>I', data, oh_offset)[0]
        header_data = struct.unpack_from('>I', data, oh_offset + 4)[0]

        name = known_headers.get(header_id, f"UNKNOWN_0x{header_id:08X}")

        if header_id == 0x00030000:  # ENTRY_POINT
            entry_point = header_data
            print(f"  ENTRY_POINT:              0x{header_data:08X}")
        elif header_id == 0x00010201:  # IMAGE_BASE_ADDRESS
            base_address = header_data
            print(f"  IMAGE_BASE_ADDRESS:       0x{header_data:08X}")
        elif header_id == 0x000183FF:  # ORIGINAL_BASE_ADDRESS
            if header_data + 8 < len(data):
                orig_size = struct.unpack_from('>I', data, header_data)[0]
                if header_data + 4 + orig_size <= len(data):
                    orig_base = struct.unpack_from('>I', data, header_data + 4)[0]
                    print(f"  ORIGINAL_BASE_ADDRESS:    0x{orig_base:08X}")
                    original_base = orig_base
            else:
                print(f"  ORIGINAL_BASE_ADDRESS:    (offset 0x{header_data:X})")
        elif header_id == 0x00040006:  # TLS_INFO
            if header_data + 24 < len(data):
                tls_slot = struct.unpack_from('>I', data, header_data)[0]
                tls_data_size = struct.unpack_from('>I', data, header_data + 4)[0]
                tls_raw_data = struct.unpack_from('>I', data, header_data + 8)[0]
                print(f"  TLS_INFO:")
                print(f"    Slot count:    {tls_slot}")
                print(f"    Data size:     0x{tls_data_size:X}")
                print(f"    Raw data addr: 0x{tls_raw_data:08X}")
        elif header_id == 0x000103FF:  # IMPORT_LIBRARIES
            if header_data + 8 < len(data):
                imp_size = struct.unpack_from('>I', data, header_data)[0]
                # Parse import library table
                print(f"  IMPORT_LIBRARIES:         (size 0x{imp_size:X})")
                # String table size at header_data + 4
                str_size = struct.unpack_from('>I', data, header_data + 4)[0]
                lib_count = struct.unpack_from('>I', data, header_data + 8)[0]
                print(f"    String table size:      0x{str_size:X}")
                print(f"    Library count:          {lib_count}")

                # String table at header_data + 12
                str_start = header_data + 12
                strings = data[str_start:str_start + str_size]
                lib_names = []
                pos = 0
                while pos < len(strings):
                    end = strings.find(b'\x00', pos)
                    if end == -1:
                        break
                    name_str = strings[pos:end].decode('ascii', errors='replace')
                    if name_str:
                        lib_names.append(name_str)
                    pos = end + 1
                    # Align to 4 bytes
                    while pos % 4 != 0:
                        pos += 1

                for ln in lib_names:
                    print(f"      - {ln}")
        elif header_id == 0x000405FF:  # STATIC_LIBRARIES
            if header_data + 4 < len(data):
                static_size = struct.unpack_from('>I', data, header_data)[0]
                print(f"  STATIC_LIBRARIES:         (size 0x{static_size:X})")
                # Each entry is 16 bytes: 8-byte name + version info
                num_libs = (static_size - 4) // 16
                for li in range(min(num_libs, 20)):
                    lib_off = header_data + 4 + li * 16
                    if lib_off + 16 <= len(data):
                        lib_name = data[lib_off:lib_off + 8].decode('ascii', errors='replace').rstrip('\x00')
                        lib_major = struct.unpack_from('>H', data, lib_off + 8)[0]
                        lib_minor = struct.unpack_from('>H', data, lib_off + 10)[0]
                        lib_build = struct.unpack_from('>H', data, lib_off + 12)[0]
                        print(f"      - {lib_name} v{lib_major}.{lib_minor}.{lib_build}")
        elif header_id == 0x00020200:  # DEFAULT_HEAP_SIZE
            print(f"  DEFAULT_HEAP_SIZE:        0x{header_data:X} ({header_data // 1024} KB)")
        elif header_id == 0x00040310:  # DEFAULT_STACK_SIZE
            if header_data + 4 < len(data):
                stack_size = struct.unpack_from('>I', data, header_data)[0]
                print(f"  DEFAULT_STACK_SIZE:       0x{stack_size:X} ({stack_size // 1024} KB)")
        elif header_id == 0x00040404:  # DEFAULT_FILESYSTEM_CACHE_SIZE
            if header_data + 4 < len(data):
                cache_size = struct.unpack_from('>I', data, header_data)[0]
                print(f"  DEFAULT_FS_CACHE_SIZE:    0x{cache_size:X} ({cache_size // 1024} KB)")
        else:
            print(f"  {name}: 0x{header_data:08X}")

        oh_offset += 8

    # PE section info
    print(f"\nPE Data:")
    pe_data = data[pe_offset:]
    if len(pe_data) > 0x200:
        # Check for MZ/PE or raw PE image
        # XEX embeds the PE without MZ stub usually
        # The PE image starts with section data directly
        # Or it might be compressed

        # Check first bytes
        first_bytes = pe_data[:16]
        print(f"  First 16 bytes: {first_bytes.hex()}")

        # If it starts with 'MZ', we have an uncompressed PE
        if first_bytes[:2] == b'MZ':
            print(f"  Format: Uncompressed PE (MZ header)")
        else:
            # Likely compressed or raw image
            print(f"  Format: Compressed/raw PE image")

    # Summary for recompilation
    print(f"\n{'=' * 60}")
    print(f"Summary for Static Recompilation:")
    print(f"{'=' * 60}")
    print(f"  File:            {xex_path}")
    print(f"  Base address:    0x{base_address:08X}")
    print(f"  Entry point:     0x{entry_point:08X}")
    print(f"  PE offset:       0x{pe_offset:X}")

    if security_offset > 0 and security_offset + 8 < len(data):
        image_size = struct.unpack_from('>I', data, security_offset + 4)[0]
        code_end = base_address + image_size
        print(f"  Image size:      0x{image_size:X} ({image_size / 1024 / 1024:.1f} MB)")
        print(f"  Code range:      0x{base_address:08X} - 0x{code_end:08X}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <xex_file>")
        sys.exit(1)
    read_xex_info(sys.argv[1])
