#!/usr/bin/env python3
"""
Extract game files from an Xbox 360 ISO image.

Xbox 360 disc images use XDVDFS (Xbox DVD File System) with encryption.
This script locates the XDVDFS partition and attempts extraction.

For encrypted ISOs (retail discs), you need extract-xiso:
  https://github.com/XboxDev/extract-xiso

Usage:
  python tools/extract_iso.py <input.iso> [output_dir]

  Default output_dir: extracted/
"""

import struct
import sys
import os

MAGIC = b'MICROSOFT*XBOX*MEDIA'
SECTOR_SIZE = 2048

# Known XDVDFS partition offsets for different disc formats
KNOWN_OFFSETS = [
    0x0FD90000,  # XGD2 standard
    0x0FDA0000,  # XGD2 variant
    0x02080000,  # XGD1
    0x00000000,  # Start of file
]


def find_partition(f):
    """Find the XDVDFS partition in the ISO."""
    for off in KNOWN_OFFSETS:
        f.seek(off)
        data = f.read(20)
        if data == MAGIC:
            return off

    # Brute force scan
    print("Scanning for XDVDFS partition...")
    f.seek(0)
    chunk_size = 1024 * 1024
    pos = 0
    while pos < 0x20000000:
        f.seek(pos)
        data = f.read(chunk_size)
        idx = data.find(MAGIC)
        if idx >= 0:
            return pos + idx
        pos += chunk_size - 20
    return None


def parse_dir(f, sector, size, base_offset):
    """Parse XDVDFS directory entries (B-tree)."""
    entries = []
    f.seek(base_offset + sector * SECTOR_SIZE)
    data = f.read(size)

    stack = [0]
    visited = set()

    while stack:
        offset = stack.pop()
        if offset in visited or offset >= len(data) or offset + 14 > len(data):
            continue
        visited.add(offset)

        left = struct.unpack_from('<H', data, offset)[0]
        right = struct.unpack_from('<H', data, offset + 2)[0]
        start = struct.unpack_from('<I', data, offset + 4)[0]
        file_size = struct.unpack_from('<I', data, offset + 8)[0]
        attrs = data[offset + 12]
        name_len = data[offset + 13]

        if offset + 14 + name_len > len(data) or name_len == 0:
            continue

        name = data[offset + 14:offset + 14 + name_len]
        # Check if name looks valid (printable ASCII)
        if not all(32 <= b < 127 for b in name):
            print(f"WARNING: Non-ASCII name at offset {offset}, data may be encrypted")
            return []

        entries.append({
            'name': name.decode('ascii'),
            'sector': start,
            'size': file_size,
            'is_dir': bool(attrs & 0x10),
        })

        if left and left * 4 < len(data):
            stack.append(left * 4)
        if right and right * 4 < len(data):
            stack.append(right * 4)

    return entries


def extract_tree(f, sector, size, base_offset, out_dir, prefix=""):
    """Recursively extract files from XDVDFS."""
    entries = parse_dir(f, sector, size, base_offset)
    if not entries:
        return 0

    count = 0
    for e in entries:
        path = os.path.join(prefix, e['name'])
        out_path = os.path.join(out_dir, path)

        if e['is_dir']:
            os.makedirs(out_path, exist_ok=True)
            count += extract_tree(f, e['sector'], e['size'],
                                  base_offset, out_dir, path)
        else:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            f.seek(base_offset + e['sector'] * SECTOR_SIZE)
            remaining = e['size']
            with open(out_path, 'wb') as out_f:
                while remaining > 0:
                    chunk = min(remaining, 4 * 1024 * 1024)
                    data = f.read(chunk)
                    if not data:
                        break
                    out_f.write(data)
                    remaining -= len(data)
            print(f"  {path} ({e['size']:,} bytes)")
            count += 1

    return count


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    iso_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted"

    with open(iso_path, 'rb') as f:
        partition = find_partition(f)
        if partition is None:
            print("ERROR: No XDVDFS partition found in ISO")
            print()
            print("This ISO may be encrypted. Use extract-xiso instead:")
            print("  https://github.com/XboxDev/extract-xiso")
            print()
            print("  extract-xiso -d extracted/ input.iso")
            sys.exit(1)

        print(f"XDVDFS partition at 0x{partition:08X}")

        f.seek(partition + 20)
        root_sector = struct.unpack('<I', f.read(4))[0]
        root_size = struct.unpack('<I', f.read(4))[0]
        print(f"Root: sector {root_sector}, size {root_size}")

        os.makedirs(out_dir, exist_ok=True)
        count = extract_tree(f, root_sector, root_size, partition, out_dir)

        if count == 0:
            print()
            print("WARNING: No files extracted. The disc image may be encrypted.")
            print()
            print("For encrypted Xbox 360 ISOs, use extract-xiso:")
            print("  https://github.com/XboxDev/extract-xiso")
            print("  extract-xiso -d extracted/ input.iso")
        else:
            print(f"\nExtracted {count} files to {out_dir}/")


if __name__ == '__main__':
    main()
