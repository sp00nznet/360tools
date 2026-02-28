"""
STFS extractor for Xbox 360 LIVE/PIRS/CON packages.
Ported from extract360.py by Rene Ladan to Python 3.
Simplified to just extract files without interactive prompts.

Original: Copyright (c) 2007, 2008, Rene Ladan, 2-clause BSD license.
Block reading algorithm from wxPirs.
"""
import hashlib
import os
import struct
import sys
import time


def get_cluster(startclust, offset):
    """Get the real starting cluster offset (from wxPirs algorithm)."""
    rst = 0
    while startclust >= 170:
        startclust //= 170
        rst += (startclust + 1) * offset
    return rst


def mstime(intime):
    """Convert Microsoft FAT time format to time tuple."""
    num_d = (intime & 0xFFFF0000) >> 16
    num_t = intime & 0x0000FFFF
    return ((num_d >> 9) + 1980, (num_d >> 5) & 0x0F, num_d & 0x1F,
            (num_t & 0xFFFF) >> 11, (num_t >> 5) & 0x3F, (num_t & 0x1F) * 2,
            0, 0, -1)


def extract_live_pirs(input_path, output_dir):
    """Extract files from a LIVE/PIRS STFS package."""
    sys.stdout.reconfigure(encoding='utf-8')

    with open(input_path, 'rb') as infile:
        fsize = os.path.getsize(input_path)
        magic = infile.read(4)
        print(f"Magic: {magic}")
        assert magic in (b'LIVE', b'PIRS'), f"Not a LIVE/PIRS file: {magic}"

        if fsize < 0xD000:
            print(f"File too small: {fsize} bytes (need at least 0xD000)")
            return

        # Determine start of file table / data area
        # wxPirs method: read path indicator of first entry at 0xC032
        infile.seek(0xC032)
        pathind = struct.unpack(">H", infile.read(2))[0]
        if pathind == 0xFFFF:
            start = 0xC000
        else:
            start = 0xD000

        # The offset used for hash table block skipping
        if start == 0xC000:
            offset = 0x1000  # 4KB gap per hash table
        else:
            offset = 0x2000  # 8KB gap per hash table

        print(f"Data start: 0x{start:X}")
        print(f"Hash table offset: 0x{offset:X}")

        # Read first cluster number from first entry's start_block field
        infile.seek(start + 0x2F)
        firstclust = struct.unpack("<H", infile.read(2))[0]
        print(f"First cluster (file table size in blocks): {firstclust}")

        # Read the entire file table
        infile.seek(start)
        ft_data = infile.read(0x1000 * firstclust)

        # Dictionary for directory structure
        paths = {0xFFFF: ""}

        os.makedirs(output_dir, exist_ok=True)
        original_dir = os.getcwd()
        os.chdir(output_dir)

        files_extracted = []

        num_entries = len(ft_data) // 64
        for i in range(num_entries):
            cur = ft_data[i * 64:(i + 1) * 64]
            namelen_flags = cur[40]  # byte 0x28

            name_len = namelen_flags & 0x3F  # low 6 bits = name length
            is_dir = bool(namelen_flags & 0x80)
            is_contiguous = bool(namelen_flags & 0x40)

            if name_len == 0:
                break

            # Parse the entry fields
            # Bytes 0-39: filename
            # Byte 40: flags|name_len
            # Bytes 41-43: valid data blocks (LE16 + high byte)
            # Bytes 44-46: valid data blocks copy
            # Bytes 47-49: starting block (LE16 + high byte)
            # Bytes 50-51: path indicator (BE16)
            # Bytes 52-55: file size (BE32)
            # Bytes 56-59: update date (BE32)
            # Bytes 60-63: access date (BE32)

            outname = cur[0:name_len].decode('ascii', errors='replace')

            clustsize1 = struct.unpack("<H", cur[41:43])[0] + (cur[43] << 16)
            clustsize2 = struct.unpack("<H", cur[44:46])[0] + (cur[46] << 16)
            startclust = struct.unpack("<H", cur[47:49])[0] + (cur[49] << 16)
            pathind = struct.unpack(">H", cur[50:52])[0]
            filelen = struct.unpack(">I", cur[52:56])[0]
            dati1 = struct.unpack(">I", cur[56:60])[0]
            dati2 = struct.unpack(">I", cur[60:64])[0]

            type_str = "DIR " if is_dir else "FILE"
            contig = " [contiguous]" if is_contiguous else ""
            print(f"  [{type_str}] {outname:<40s} {filelen:>12d} bytes  start_block={startclust}  blocks={clustsize1}{contig}  path={pathind}")

            if name_len < 1 or name_len > 40:
                print(f"    WARNING: Name length {name_len} out of range, skipping")
                continue

            if clustsize1 != clustsize2:
                print(f"    WARNING: Cluster sizes don't match ({clustsize1} != {clustsize2})")

            if is_dir:
                paths[i] = paths.get(pathind, "") + outname + "/"
                full_dir = os.path.join(output_dir, paths[i])
                os.makedirs(full_dir, exist_ok=True)
                print(f"    -> Created directory: {paths[i]}")
            else:
                if startclust < 1:
                    print(f"    WARNING: Starting cluster must be >= 1, skipping")
                    continue

                # Determine output path
                parent = paths.get(pathind, "")
                out_path = os.path.join(output_dir, parent, outname)
                os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)

                # Read file data using wxPirs block algorithm
                adstart = startclust * 0x1000 + start
                remaining = filelen
                file_data = bytearray()
                cur_clust = startclust

                while remaining > 0:
                    realstart = adstart + get_cluster(cur_clust, offset)
                    infile.seek(realstart)
                    chunk = infile.read(min(0x1000, remaining))
                    file_data.extend(chunk)
                    cur_clust += 1
                    adstart += 0x1000
                    remaining -= 0x1000

                with open(out_path, 'wb') as outfile:
                    outfile.write(bytes(file_data[:filelen]))

                # Check magic of extracted file
                file_magic = bytes(file_data[:4]) if len(file_data) >= 4 else b''
                magic_str = ""
                if file_magic == b'XEX2':
                    magic_str = " >> XEX2 executable!"
                elif file_magic == b'XEX1':
                    magic_str = " >> XEX1 executable!"
                elif file_magic == b'\x89PNG':
                    magic_str = " >> PNG image"

                print(f"    -> Extracted: {out_path} ({filelen} bytes){magic_str}")
                files_extracted.append((outname, out_path, filelen, file_magic))

        os.chdir(original_dir)
        print(f"\nDone! Extracted {len(files_extracted)} file(s) to {output_dir}")

        return files_extracted


if __name__ == '__main__':
    if len(sys.argv) < 2:
        input_path = r'E:\vig8\Vigilante 8 Arcade'
    else:
        input_path = sys.argv[1]

    if len(sys.argv) < 3:
        output_dir = os.path.join(os.path.dirname(input_path) or '.', 'extracted')
    else:
        output_dir = sys.argv[2]

    print(f"Input:  {input_path}")
    print(f"Output: {output_dir}")
    print()

    extract_live_pirs(input_path, output_dir)
