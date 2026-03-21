#!/usr/bin/env python3
"""
Direct XEX2 extraction from STFS container.
Finds XEX2 magic and extracts the complete XEX binary.
"""

import struct
import sys
import os


def extract_xex_from_stfs(stfs_path, output_path):
    """Extract XEX2 binary from STFS container by finding XEX2 magic."""
    with open(stfs_path, 'rb') as f:
        data = f.read()

    print(f"File size: {len(data)} bytes ({len(data) / 1024 / 1024:.1f} MB)")

    # Find all XEX2 magic occurrences
    xex_offsets = []
    pos = 0
    while pos < len(data):
        idx = data.find(b'XEX2', pos)
        if idx == -1:
            break
        xex_offsets.append(idx)
        pos = idx + 1

    if not xex_offsets:
        print("ERROR: No XEX2 magic found in file!")
        return False

    print(f"Found {len(xex_offsets)} XEX2 header(s)")

    for i, xex_off in enumerate(xex_offsets):
        print(f"\n=== XEX2 #{i} at offset 0x{xex_off:X} ===")

        if xex_off + 0x18 >= len(data):
            print("  Too close to end of file, skipping")
            continue

        # XEX2 header layout:
        # 0x00: magic "XEX2" (4 bytes)
        # 0x04: module flags (4 bytes)
        # 0x08: PE data offset (4 bytes, BE) - offset from XEX start to embedded PE
        # 0x0C: reserved (4 bytes)
        # 0x10: security info offset (4 bytes, BE)
        # 0x14: optional header count (4 bytes, BE)
        # 0x18+: optional headers

        module_flags = struct.unpack_from('>I', data, xex_off + 0x04)[0]
        pe_offset = struct.unpack_from('>I', data, xex_off + 0x08)[0]
        reserved = struct.unpack_from('>I', data, xex_off + 0x0C)[0]
        security_offset = struct.unpack_from('>I', data, xex_off + 0x10)[0]
        header_count = struct.unpack_from('>I', data, xex_off + 0x14)[0]

        print(f"  Module flags: 0x{module_flags:08X}")
        print(f"  PE data offset: 0x{pe_offset:X}")
        print(f"  Security info offset: 0x{security_offset:X}")
        print(f"  Optional header count: {header_count}")

        # The PE data starts at xex_off + pe_offset
        # We need to figure out the total XEX size
        # Security info contains image size info

        if security_offset > 0 and xex_off + security_offset + 0x180 < len(data):
            sec_data = data[xex_off + security_offset:]
            # Security info has image_size at offset 0x174 in the security structure
            # But the layout varies. Let's try to find the image size from the optional headers

        # Parse optional headers to find image size and other info
        print(f"  Optional headers:")
        oh_offset = xex_off + 0x18
        image_size = 0
        base_address = 0
        original_pe_name = ""

        for h in range(min(header_count, 50)):
            if oh_offset + 8 > len(data):
                break

            header_id = struct.unpack_from('>I', data, oh_offset)[0]
            header_data = struct.unpack_from('>I', data, oh_offset + 4)[0]

            key = (header_id >> 8) & 0xFFFFFF
            size_flag = header_id & 0xFF

            # Known header IDs
            header_names = {
                0x00010001: "RESOURCE_INFO",
                0x00020001: "BASE_FILE_FORMAT",
                0x000200FF: "BASE_REFERENCE",
                0x00030000: "ENTRY_POINT",
                0x00040006: "TLS_INFO",
                0x000503FF: "IMPORT_LIBRARIES",
                0x00080001: "ORIGINAL_PE_NAME",
                0x000E0002: "EXECUTION_INFO",
                0x00100001: "GAME_RATINGS",
                0x000181FF: "IMAGE_BASE_ADDRESS",
                0x00010100: "BOUNDING_PATH",
                0x000183FF: "ORIGINAL_BASE_ADDRESS",
                0x00018002: "LAN_KEY",
                0x000200FF: "BASE_REFERENCE",
                0x00020104: "DELTA_PATCH_DESCRIPTOR",
                0x000301FF: "SYSTEM_FLAGS",
                0x00040310: "DEFAULT_STACK_SIZE",
                0x00040404: "DEFAULT_FILESYSTEM_CACHE_SIZE",
                0x00040405: "DEFAULT_HEAP_SIZE",
            }

            name = header_names.get(header_id, f"0x{header_id:08X}")

            if header_id == 0x00030000:  # ENTRY_POINT
                print(f"    [{h}] ENTRY_POINT: 0x{header_data:08X}")
            elif header_id == 0x000181FF:  # IMAGE_BASE_ADDRESS
                # Data is offset to a structure
                if xex_off + header_data + 4 <= len(data):
                    base_address = struct.unpack_from('>I', data, xex_off + header_data)[0]
                    print(f"    [{h}] IMAGE_BASE_ADDRESS: 0x{base_address:08X}")
                else:
                    print(f"    [{h}] IMAGE_BASE_ADDRESS: (offset 0x{header_data:X})")
            elif header_id == 0x00080001:  # ORIGINAL_PE_NAME
                if xex_off + header_data + 0x10 < len(data):
                    name_off = xex_off + header_data
                    pe_name_size = struct.unpack_from('>I', data, name_off)[0]
                    pe_name_bytes = data[name_off + 4:name_off + pe_name_size]
                    original_pe_name = pe_name_bytes.decode('ascii', errors='replace').rstrip('\x00')
                    print(f"    [{h}] ORIGINAL_PE_NAME: {original_pe_name}")
            else:
                print(f"    [{h}] {name}: 0x{header_data:08X}")

            oh_offset += 8

        # Estimate XEX size: look for end of PE data
        # The PE data should be the bulk of the file
        # Use the STFS container to figure out total file listing size
        # Or just grab everything from XEX start to end of meaningful data

        # Better approach: look at the PE header to determine image size
        pe_start = xex_off + pe_offset
        if pe_start + 0x200 < len(data):
            # Check for compressed data (most XEX files use compression)
            # First check the base file format header
            # The raw PE data should be here
            pe_magic = data[pe_start:pe_start + 2]
            print(f"\n  PE data at offset 0x{pe_start:X}: {data[pe_start:pe_start+16].hex()}")

            # For STFS containers, the data might not be contiguous due to hash blocks
            # Let's just try to determine the size and extract what we can

        # Strategy: extract from XEX magic to just before the next structure or end of file
        # For a single XEX in an STFS, it's usually the main content
        # The XEX includes its headers + PE data
        # We need to figure out the actual end

        # Check if there's a file size hint from security info
        if security_offset > 0 and xex_off + security_offset + 8 < len(data):
            sec_off = xex_off + security_offset
            # XEX2 security info structure:
            # 0x000: header_size (4 bytes BE)
            # 0x004: image_size (4 bytes BE)
            sec_header_size = struct.unpack_from('>I', data, sec_off)[0]
            sec_image_size = struct.unpack_from('>I', data, sec_off + 4)[0]
            print(f"\n  Security info header size: 0x{sec_header_size:X}")
            print(f"  Security info image size: 0x{sec_image_size:X} ({sec_image_size / 1024 / 1024:.1f} MB)")
            image_size = sec_image_size

    # For this specific case, we know the STFS block layout might scramble the data
    # Let's try a different approach: use the known block structure

    # STFS block size is 0x1000
    # The XEX is at offset 0x1A8000 in the raw file
    # But the STFS hash tables interleave with data blocks

    # Actually, for LIVE packages, let's try to read the data as-is
    # The XEX header tells us its own structure, and we need the XEX including PE
    # For small XEX files, the data might be contiguous enough

    xex_off = xex_offsets[0]

    # The total file we need = XEX header + PE image
    # pe_offset tells us where the PE starts within the XEX
    # image_size from security info is the uncompressed PE image size
    # But the actual data in the STFS might be compressed

    # Let's just extract the raw XEX data - starting from XEX2 magic
    # up to pe_offset + image_size (or a reasonable estimate)

    # For STFS with hash interleaving, data blocks (0x1000 each) have
    # hash table blocks inserted every 0xAA blocks at separation level 1

    # The XEX starts at raw file offset 0x1A8000
    # This is likely block number (0x1A8000 - header_size) / 0x1000
    # But with hash tables this doesn't map directly

    # Simplest approach: detect hash table blocks and skip them
    BLOCK_SIZE = 0x1000
    HASH_BLOCK_SIZE = 0x1000

    # For this container, let's try reading the XEX assuming the data
    # might have hash blocks interspersed
    # A hash table block can be detected because it contains hashes (SHA1)
    # of the following data blocks

    # Even simpler: try extracting the raw data and see if the PE is valid
    # XEX size estimate: pe_offset + compressed_pe_size
    # For uncompressed/retail XEX, the PE image follows the header directly

    # Extract a generous amount starting from XEX magic
    # Use image_size as upper bound if available
    max_size = pe_offset + image_size if image_size > 0 else 32 * 1024 * 1024  # 32MB max
    max_size = min(max_size, len(data) - xex_off)

    # However, STFS interleaves hash blocks in the data area
    # We need to strip those out
    # Hash blocks appear after every 0xAA (170) data blocks

    # Determine the header area of the STFS
    stfs_magic = data[0:4].decode('ascii', errors='replace')
    if stfs_magic == 'CON ':
        stfs_header_size = 0xB000
    else:
        stfs_header_size = 0xA000  # Most LIVE/PIRS packages

    # Check: try each header size and see which puts us at the XEX
    for try_hs in [0xA000, 0xB000, 0xC000]:
        rel_offset = xex_off - try_hs
        if rel_offset > 0 and rel_offset % BLOCK_SIZE == 0:
            block_within_data = rel_offset // BLOCK_SIZE
            print(f"\n  With header_size=0x{try_hs:X}: XEX is at data area offset 0x{rel_offset:X}, block #{block_within_data}")

    # For block_separation=1, hash tables appear at:
    # After every 0xAA data blocks, there's 1 L0 hash table block
    # After every 0xAA L0 hash table regions, there's 1 L1 hash table block

    # Let's reconstruct the contiguous data by reading blocks and skipping hash tables
    # Working backwards from the XEX offset to determine the correct header size

    print(f"\n=== Extracting XEX data ===")

    # The STFS data area starts after the header
    # Each "cluster" of blocks has 0xAA data blocks followed by 1 hash table block
    # Actually, the hash table comes BEFORE the data blocks it covers

    # Let me try a simpler approach: just extract raw bytes from XEX offset
    # and check if the result is a valid XEX

    # Read raw XEX
    xex_data = bytearray()

    # Read from the XEX start, but skip any blocks that look like hash tables
    # Actually, let's first try the simplest thing: raw extraction
    print(f"  Attempting raw extraction from offset 0x{xex_off:X}...")

    # Determine how much data to read
    # For the XEX header, we need at least up to pe_offset
    # Then the PE data follows

    # Read XEX header (up to PE offset)
    xex_header = data[xex_off:xex_off + pe_offset]

    print(f"  XEX header size: 0x{pe_offset:X} ({pe_offset} bytes)")
    print(f"  PE data starts at file offset: 0x{xex_off + pe_offset:X}")

    # Check the block boundaries
    # If pe_offset = 0x4000, and XEX starts at 0x1A8000:
    # XEX header: 0x1A8000 - 0x1ABFFF (blocks at 0x1A8, 0x1A9, 0x1AA, 0x1AB)
    # PE data starts at: 0x1AC000

    # Check if hash table blocks need to be skipped in the PE data region
    # For block_separation=1, every 0xAB blocks (0xAA data + 1 hash) in the data area

    # Let's try the raw approach first - just grab everything
    # If the XEX is small enough it might all be contiguous

    # For the XEX header portion, it should be reliable since it's only 0x4000 bytes
    # The PE data is what could be split by hash blocks

    # Total XEX file to extract: header + PE
    # We'll read the PE portion carefully

    # First, let's compute how many blocks the XEX occupies
    total_xex_size = pe_offset + (image_size if image_size > 0 else 0)

    if total_xex_size == 0:
        # Fallback: try to read until we hit obvious non-PE data or end of file
        total_xex_size = 16 * 1024 * 1024  # 16MB guess

    total_blocks = (total_xex_size + BLOCK_SIZE - 1) // BLOCK_SIZE
    print(f"  Estimated total XEX size: 0x{total_xex_size:X} ({total_xex_size / 1024 / 1024:.1f} MB)")
    print(f"  Estimated blocks needed: {total_blocks}")

    # Read blocks, checking for and skipping hash table blocks
    # Heuristic: a hash table block will have SHA1 hashes (20 bytes each)
    # and a specific structure. Data blocks from a PE won't match that pattern.

    # Actually, let's try the STFS block reading approach properly
    # The data area has a specific layout:
    # For block_separation=1:
    #   Block 0-0xA9: data blocks 0-0xA9
    #   Block 0xAA: L0 hash table for blocks 0-0xA9
    #   Block 0xAB-0x154: data blocks 0xAA-0x153
    #   Block 0x155: L0 hash table for blocks 0xAA-0x153
    #   ... and so on
    #   After 0xAA L0 hash tables, there's an L1 hash table block

    # Wait, actually for block_separation=0, the hash tables come BEFORE data
    # For block_separation=1, the hash tables come AFTER data
    # Our container has block_separation=1

    # For separation=1: layout per L0 region is:
    # 0xAA data blocks, then 1 hash table block

    # XEX is at raw offset 0x1A8000
    # Data area starts at offset stfs_header_size
    # Let's figure out which data block number the XEX starts at

    # Try header_size = 0xC000 (since "61636869" = "achi" which looks like it could be
    # the start of actual file content)
    # Actually let's try to detect: scan the beginning of the data area

    # More pragmatic: read the whole data area, strip hash blocks, then find XEX
    print(f"\n  Rebuilding contiguous data stream (stripping hash table blocks)...")

    # For separation=1, data layout:
    # Groups of (0xAA data blocks + 1 hash block)
    # Plus L1 hash blocks after every 0xAA groups

    contiguous_data = bytearray()
    block_offset = stfs_header_size  # default to 0xA000

    # Try different header sizes
    for try_hs in [0xA000, 0xB000, 0xC000]:
        test_contiguous = bytearray()
        block_pos = try_hs
        data_block_count = 0
        group_count = 0

        while block_pos + BLOCK_SIZE <= len(data) and len(test_contiguous) < 200 * 1024 * 1024:
            blocks_in_group = 0
            # Read 0xAA data blocks
            while blocks_in_group < 0xAA and block_pos + BLOCK_SIZE <= len(data):
                test_contiguous.extend(data[block_pos:block_pos + BLOCK_SIZE])
                block_pos += BLOCK_SIZE
                blocks_in_group += 1
                data_block_count += 1

            # Skip 1 hash block
            block_pos += BLOCK_SIZE
            group_count += 1

            # After every 0xAA groups, skip 1 L1 hash block
            if group_count % 0xAA == 0:
                block_pos += BLOCK_SIZE

        # Check if XEX2 is in the reconstructed data
        xex_pos = test_contiguous.find(b'XEX2')
        if xex_pos >= 0:
            print(f"  header_size=0x{try_hs:X}: Found XEX2 at reconstructed offset 0x{xex_pos:X} (read {data_block_count} data blocks)")
            contiguous_data = test_contiguous
            stfs_header_size = try_hs
            break
        else:
            print(f"  header_size=0x{try_hs:X}: XEX2 not found in reconstructed data ({data_block_count} blocks read)")

    if not contiguous_data:
        print("\n  Falling back to raw extraction (no hash stripping)...")
        # Just grab the raw data from XEX offset
        raw_end = min(xex_off + total_xex_size + 1024 * 1024, len(data))
        raw_xex = data[xex_off:raw_end]

        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(raw_xex)
        print(f"  Wrote raw extraction to {output_path} ({len(raw_xex)} bytes)")
        return True

    # Find XEX in contiguous data
    xex_pos = contiguous_data.find(b'XEX2')
    if xex_pos < 0:
        print("ERROR: XEX2 not found in reconstructed data!")
        return False

    print(f"\n  XEX2 found at offset 0x{xex_pos:X} in contiguous data")

    # Parse XEX header from contiguous data
    pe_off = struct.unpack_from('>I', contiguous_data, xex_pos + 0x08)[0]
    sec_off = struct.unpack_from('>I', contiguous_data, xex_pos + 0x10)[0]

    # Get image size from security info
    img_size = 0
    if sec_off > 0 and xex_pos + sec_off + 8 < len(contiguous_data):
        img_size = struct.unpack_from('>I', contiguous_data, xex_pos + sec_off + 4)[0]

    xex_total = pe_off + img_size if img_size > 0 else pe_off + 16 * 1024 * 1024
    xex_total = min(xex_total, len(contiguous_data) - xex_pos)

    xex_bytes = contiguous_data[xex_pos:xex_pos + xex_total]

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(xex_bytes)

    print(f"\n  Extracted XEX: {output_path}")
    print(f"  Size: {len(xex_bytes)} bytes ({len(xex_bytes) / 1024 / 1024:.1f} MB)")
    print(f"  PE offset: 0x{pe_off:X}")
    if img_size:
        print(f"  Image size: 0x{img_size:X} ({img_size / 1024 / 1024:.1f} MB)")

    # Verify
    if xex_bytes[:4] == b'XEX2':
        print(f"  Verification: XEX2 magic OK")
    else:
        print(f"  WARNING: XEX2 magic mismatch!")

    return True


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <stfs_file> <output_xex>")
        sys.exit(1)

    extract_xex_from_stfs(sys.argv[1], sys.argv[2])
