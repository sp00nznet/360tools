# The Simpsons Arcade - Binary Analysis Notes

## STFS Container

The game is distributed as a LIVE (STFS) container:
- **Magic:** LIVE (expected)
- **Content Type:** 0x000D0000 (Xbox Live Arcade)
- **Title ID:** 0x584111FA
- **Package Path:** `The Simpsons Arcade\584111FA\000D0000\5BA2C88EDCCD952114B3809DA53200C5C3B2236358`
- **Package Size:** 18,812,928 bytes (~18 MB)
- **Extracted using:** `tools/extract_stfs.py`
- **Contents:** 12 achievement PNGs, ArcadeInfo.xml, default.xex, icon.png, MarketPlace.png, 0B/SIMPSONS.SR, 0B/SIMPSONS_FW.SR

## XEX File Information

- **Filename:** `default.xex`
- **Format:** XEX2 (Xbox 360 executable)
- **Architecture:** PowerPC (Xenon, big-endian, machine type 0x01F2)
- **Platform:** Xbox Live Arcade (XBLA)
- **Title ID:** 0x584111FA
- **XEX Size:** 1,327,104 bytes
- **Encryption:** Normal (AES-CBC)
- **Compression:** Normal (LZX, window=32KB)
- **Base Address:** 0x82000000
- **Entry Point:** 0x8214DB50
- **Image Size:** 0x3E0000 (4,063,232 bytes)

## PE Image Sections

| Section  | Virtual Address | VSize    | Raw Size | Offset   | Flags        |
|----------|----------------|----------|----------|----------|--------------|
| .rdata   | 0x82000400     | 0x09414C | 0x094200 | 0x000400 | IDATA, R     |
| .pdata   | 0x82094600     | 0x0088D0 | 0x008A00 | 0x094600 | IDATA, R     |
| .text    | 0x820A0000     | 0x237350 | 0x237400 | 0x09D000 | CODE, X, R   |
| .data    | 0x822E0000     | 0x0D45D4 | 0x02FC00 | 0x2D4400 | IDATA, R, W  |
| .XBMOVIE | 0x823B4600    | 0x00000C | 0x000200 | 0x304000 | IDATA, R, W  |
| .idata   | 0x823C0000     | 0x0003C4 | 0x000400 | 0x304200 | IDATA, R, W  |
| .XBLD    | 0x823D0000     | 0x000100 | 0x000200 | 0x304600 | IDATA, R     |
| .reloc   | 0x823D0200     | 0x01A998 | 0x01AA00 | 0x304800 | IDATA, R     |

## Key Constants

| Constant         | Value        |
|-----------------|-------------|
| IMAGE_BASE      | 0x82000000  |
| IMAGE_SIZE      | 0x3E0000    |
| CODE_BASE       | 0x820A0000  |
| CODE_SIZE       | 0x237350    |
| CODE_END        | 0x822D7350  |
| ENTRY_POINT     | 0x8214DB50  |
| DYNAMIC_STUB    | 0x822D7350  |

## ABI Addresses

Found by scanning PE image with `tools/find_abi_addrs.py`.

| Function | Address | Verified |
|----------|---------|----------|
| savegprlr_14 | 0x8225D390 | YES |
| restgprlr_14 | 0x8225D3E0 | YES |
| savefpr_14 | 0x8225E270 | YES |
| restfpr_14 | 0x8225E2BC | YES |
| savevmx_14 | 0x8225E6C0 | YES |
| restvmx_14 | 0x8225E958 | YES |
| savevmx_64 | 0x8225E754 | YES |
| restvmx_64 | 0x8225E9EC | YES |
| setjmp | Not found | N/A |
| longjmp | Not found | N/A |

## Code Statistics

- ~4,007 function prologues detected in .text section
- ~6,611 return instructions (blr) detected

## Game Data Files

| File | Size | Notes |
|------|------|-------|
| SIMPSONS.SR | 2,748,416 bytes | Game resource archive |
| SIMPSONS_FW.SR | 14,419,520 bytes | Game resource archive (firmware/assets) |
| ArcadeInfo.xml | 2,674 bytes | Arcade metadata |

## Jump Tables

TODO: Run XenonAnalyse to detect jump tables.

## Recompilation Statistics

TODO: Run XenonRecomp first pass.

## Game Information

- **Title:** The Simpsons Arcade
- **Developer:** Backbone Entertainment
- **Publisher:** Konami
- **Release:** February 2012 (XBLA)
- **Original Arcade:** 1991, Konami
- **Genre:** Beat 'em up (up to 4 players)
- **Players:** Homer, Marge, Bart, Lisa
