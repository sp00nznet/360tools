# 360tools

**Everything you need to statically recompile Xbox 360 XBLA games to native PC executables.**

No emulator. No interpreter. No JIT. Just your Xbox 360 game, recompiled to C++ and running natively on x86-64 at full speed.

```
   XBLA Game (PowerPC) ----or---- Xbox 360 ISO
         |                              |
    [ extract_stfs.py ]         [ extract_iso.py ]
         |                              |
    [ extract_pe.py ]        <-- decrypt & decompress the XEX2
         |
    [ find_abi_addrs.py ]    <-- locate PPC ABI helpers
    [ extract_switch_tables.py ] <-- map out all jump tables
    [ find_missing_vtable_funcs.py ] <-- catch vtable-only functions
         |
    [ XenonRecomp ]          <-- translate PowerPC -> C++
         |
    [ ReXGlue SDK ]          <-- provides the Xbox 360 runtime
         |
    Native x86-64 .exe       <-- your game, running on PC
```

## What's In The Box

### `tools/` -- The Pipeline

| Script | What It Does |
|--------|-------------|
| **`extract_stfs.py`** | Rips files out of STFS/LIVE/PIRS/CON Xbox 360 packages. Point it at a downloaded XBLA title and it pulls out the XEX and all game assets. Handles edge cases like `start_block=0` entries. |
| **`extract_iso.py`** | Extracts game files from Xbox 360 XDVDFS disc images. Finds the partition automatically (XGD1/XGD2), parses the B-tree directory, and extracts all files. Detects encrypted ISOs and points you to extract-xiso. |
| **`extract_pe.py`** | Decrypts (AES-128) and decompresses the PE image buried inside an XEX2 file. Handles both basic block and LZX (Normal) compression, plus raw COFF headers without MZ/PE signatures. This is what XenonRecomp actually needs. |
| **`lzx_decompress.py`** | Pure Python LZX decompression. Used by `extract_pe.py` for XEX files with LZX-compressed PE images. |
| **`find_abi_addrs.py`** | Scans the PE binary for all 10 standard PowerPC ABI helper functions (`__savegprlr_14`, `__restfpr_14`, VMX save/restore, `setjmp`/`longjmp`, etc.) and outputs them in TOML format ready for XenonRecomp. |
| **`extract_switch_tables.py`** | Finds PPC switch/jump tables by pattern-matching `add r12,r12,r0; mtctr r12; bctr` sequences, reads the table data, and generates `[[switch]]` TOML entries. Handles u8/u16 entries, scaling, bounds checking. |
| **`find_missing_vtable_funcs.py`** | Scans the PE data section for C++ vtable entries pointing to functions that XenonRecomp missed (because they're never called directly -- only through vtable dispatch). Classifies entries as THUNK or FUNC. |
| **`parse_xex_imports.py`** | Parses XEX2 import tables to identify which kernel/XAM functions the game actually calls. Helps you know which stubs you need to implement. |
| **`xex_info.py`** | Quick XEX2 header dumper -- parses and displays all header fields, security info, import libraries, static libraries, and a recompilation summary. Great for initial triage before running the full pipeline. |
| **`extract_xex_direct.py`** | Brute-force XEX2 extractor that finds XEX2 magic in STFS containers and rebuilds the contiguous data stream (stripping hash table blocks). Useful fallback when `extract_stfs.py`'s block algorithm fails on unusual packages. |
| **`post_codegen.py`** | Re-applies safety macro overrides (`PPC_CALL_INDIRECT_FUNC`, `PPC_UNIMPLEMENTED`) to the generated `*_init.h` after codegen regenerates it. Run after every `rexglue codegen` pass. |
| **`dump_pe.cpp`** | C++ XEX-to-PE extractor using XenonUtils. Faster than the Python version if you've already built XenonRecomp. |

### `patches/` -- XenonRecomp Fixes

The stock XenonRecomp doesn't handle every instruction you'll hit in the wild. These patches add what's missing:

| Patch | What It Adds |
|-------|-------------|
| **`xenonrecomp-altivec-vmx.patch`** | 30+ missing Altivec/VMX instruction handlers: `vaddsbs`, `vaddsws`, `vavguh`, `vcmpequh`, `vcmpgtsh`, `vpkshss`, `vpkswus`, `vrlh`, `vslh`, `vslo`, `vnor`, `vspltish`, `vsrab`, `vsrah`, and more. Also adds `cror`, `crorc`, `eqv`, `rldicl` with Rc bit. |
| **`xenonrecomp-missing-instructions.patch`** | 21 missing PPC instructions: update-form loads (`lhzu`, `lhau`, `lbzux`, `lhzux`, `lwzux`, `ldux`, `lfsu`, `lfsux`, `lfdu`), update-form stores (`sthu`, `sthux`, `stbux`, `stdux`, `stfsu`, `stfdu`), conditional branches (`bdzf`, `bdnzt`), integer arithmetic (`addc`, `addme`, `subfze`), and `lvehx`. |

### `templates/` -- Project Scaffold

A complete, working project template based on the patterns proven across multiple shipped recomp projects. Copy this into your new project and customize:

```
templates/
  ppc_config.h              # __builtin_trap() override, PPC_CALL_INDIRECT_FUNC
                             #   with import thunk resolution, PPC_INCLUDE_DETAIL gate
  project/
    CMakeLists.txt           # ReXGlue SDK build with WHOLEARCHIVE linking
    CMakePresets.json         # Clang + Ninja preset (win-amd64)
    src/
      main.cpp               # Windowed app: VEH crash handler, null page handler,
                              #   guest page demand paging, C++ exception decoding,
                              #   F11 fullscreen, ImGui overlay, stderr logging
      menu.cpp / menu.h      # Win32 native menu bar + ImGui config dialogs
                              #   (Graphics, Game, Debug, Controls)
      settings.cpp / settings.h  # TOML-based settings persistence via toml++
      stubs.cpp              # Game-specific kernel stub overrides
                              #   (license bypass, multi-user sign-in, etc.)
      keyboard_driver.cpp/h  # Keyboard + XInput merged input driver
                              #   (both keyboard and real controller work simultaneously)
      test_boot.cpp          # Console-mode test harness for isolating crashes
```

### `docs/` -- How It All Works

| Doc | What It Covers |
|-----|---------------|
| **`xenonrecomp-workflow.md`** | Full step-by-step from "I have an XBLA download" to "I have a running PC executable". Building XenonRecomp, applying patches, running codegen, integrating with ReXGlue. |
| **`speed-fix.md`** | The two speed fixes every 360 recomp needs: VdSwap frame limiter (Windows `Sleep(16)` actually sleeps 31ms!) and `__rdtsc()` timebase scaling (host TSC is 60-80x faster than Xbox 360's 49.875 MHz timebase). |
| **`binary-analysis.md`** | How to analyze an Xbox 360 PE binary: memory layout, section mapping, finding entry points, understanding the PPC ABI. |

### `config/` -- Example Configs

Reference TOML configurations for XenonRecomp and ReXGlue codegen, with comments explaining every field.

## Quick Start

### Prerequisites

- **Python 3.8+** with dependencies: `pip install -r requirements.txt`
- **CMake 3.20+**, **Ninja**, **Clang 18+** (clang-cl on Windows)
- **MSVC 2022** (for Windows SDK headers)
- **Git** (for cloning XenonRecomp and ReXGlue)

### The Pipeline

```bash
# 1. Get your game files out of the XBLA package (or ISO)
python tools/extract_stfs.py path/to/XBLA_PACKAGE output_dir/
# -- or for disc-based games --
python tools/extract_iso.py path/to/game.iso output_dir/

# 2. Decrypt and decompress the XEX into a raw PE image
python tools/extract_pe.py output_dir/default.xex pe_image.bin

# 3. Find ABI helper addresses (paste output into your TOML config)
python tools/find_abi_addrs.py pe_image.bin

# 4. Build XenonRecomp with our patches
git clone --recursive https://github.com/hedge-dev/XenonRecomp.git
cd XenonRecomp
git apply ../patches/xenonrecomp-altivec-vmx.patch
git apply ../patches/xenonrecomp-missing-instructions.patch
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl
cmake --build build --config Release
cd ..

# 5. Create your TOML config (see config/example.toml)
#    Add the ABI addresses from step 3
#    Run XenonRecomp:
./XenonRecomp/build/XenonRecomp pe_image.bin your_game.toml

# 6. Extract switch tables and add them to config
python tools/extract_switch_tables.py pe_image.bin
#    Append the output to your TOML config, re-run XenonRecomp

# 7. Find vtable functions that were missed
python tools/find_missing_vtable_funcs.py pe_image.bin generated/your_game_init.cpp
#    Add missing functions to your config, re-run XenonRecomp

# 8. Set up your project from the template
cp -r templates/project your_game/project
#    Customize CMakeLists.txt, main.cpp, stubs.cpp for your game
#    Clone ReXGlue SDK, build, and run!
```

### Parse XEX Imports (Optional but Helpful)

```bash
# See which kernel/XAM functions your game actually calls
python tools/parse_xex_imports.py path/to/default.xex
```

This tells you exactly which Xbox 360 API stubs you'll need to implement (or which ones the ReXGlue SDK already covers).

## Battle-Tested Fixes

These patterns have been discovered, debugged, and proven across multiple projects. They're already baked into the templates:

### VdSwap Frame Limiter
Windows `Sleep(16)` actually sleeps ~31ms due to 15.6ms timer granularity. The fix uses `QueryPerformanceCounter` spin-loop for precise 16.667ms frame pacing. Without this, your game runs at half speed. See `docs/speed-fix.md`.

### Timebase Scaling
XenonRecomp generates `__rdtsc()` for PPC `mftb` instructions, but your PC's TSC runs at ~3-4 GHz vs the Xbox 360's 49.875 MHz. The `ppc_config.h` template overrides `__rdtsc()` to route through the ReXGlue SDK's scaled guest timebase.

### PPC_CALL_INDIRECT_FUNC Safe Dispatch
C++ vtable calls on Xbox 360 need NULL checks, code range validation, import thunk resolution, and graceful fallback instead of hard crashes. The `ppc_config.h` template includes the battle-hardened macro that handles all three cases: NULL targets, import thunks (decodes the PPC `lis/lwz/mtctr/bctr` pattern and resolves through the IAT), and normal code-range targets.

### __builtin_trap() Override
XenonRecomp emits `__builtin_trap()` as safety nets for out-of-range switch/jump table indices, but some paths are legitimately reached at runtime. The template overrides this to log a rate-limited warning instead of crashing.

### VEH Null Page Handler + Guest Page Demand Paging
Three Vectored Exception Handlers work together: a crash logger (with C++ exception decoding via MSVC's `0xE06D7363` magic), a guest page commit handler (demand-pages 4KB within the guest address range), and a null page handler that intercepts null pointer dereferences, decodes the x86-64 instruction (MOV, MOVZX, MOVSX, MOVSXD, MOV8), zeros the destination register, and continues execution.

### ROV vs RTV Render Path
If you're getting white screens with certain render target formats (especially `k_2_10_10_10_FLOAT` + 4xMSAA), switch to the ROV (Rasterizer Ordered Views) path. ROV uses pixel shader interlock for EDRAM emulation and handles these edge cases correctly.

## Projects Built With These Tools

| Game | Repo | Status |
|------|------|--------|
| **The Simpsons Arcade** (XBLA, 2012) | [simpsonsarcade](https://github.com/sp00nznet/simpsonsarcade) | Playable -- full speed, audio, input, graphics |
| **Vigilante 8 Arcade** (XBLA) | [vig8](https://github.com/sp00nznet/vig8) | Playable -- 90 FPS, split-screen multiplayer, 79 shaders |
| **Guitar Hero II** (Xbox 360, 2007) | [gh2](https://github.com/sp00nznet/gh2) | Playable -- gameplay, audio, scoring, keyboard input working. Guitar controller support in progress |
| **Crazy Taxi** (XBLA, 2010) | [ctxbla](https://github.com/sp00nznet/ctxbla) | Playable -- D3D12 rendering, keyboard + XInput, arcade mode. In-game audio (XMA) in progress |
| **Comix Zone** (XBLA, 2009) | [comixzone](https://github.com/sp00nznet/comixzone) | Analysis -- binary extracted, 11,824 functions generated, runtime scaffold pending |
| **Virtual On: Oratorio Tangram** (XBLA) | [voot](https://github.com/sp00nznet/voot) | Foundation -- project structure, codegen config ready |
| **Saints Row** (Xbox 360, 2006) | [saintsrow](https://github.com/sp00nznet/saintsrow) | Planning -- ISO extracted, binary analysis pending |

## The Stack

This whole pipeline stands on the shoulders of some incredible projects:

- **[XenonRecomp](https://github.com/hedge-dev/XenonRecomp)** by hedge-dev -- The static recompiler that translates PowerPC to C++. This is the engine that makes it all possible.
- **[ReXGlue SDK](https://github.com/hedge-dev/ReXGlue)** by hedge-dev -- The runtime that provides everything the Xbox 360 OS gave games: kernel, D3D12 GPU backend (derived from [Xenia](https://github.com/xenia-project/xenia)'s GPU code), XMA audio, input, threading.
- **[Xenia](https://github.com/xenia-project/xenia)** -- The Xbox 360 emulator whose GPU implementation powers the D3D12 backend in ReXGlue.
- **[SIMDE](https://github.com/simd-everywhere/simde)** -- SIMD Everywhere, used by XenonRecomp to translate Altivec/VMX vector instructions to SSE/AVX.
- **[toml++](https://github.com/marzer/tomlplusplus)** -- TOML config parsing for the settings system.
- **[Dear ImGui](https://github.com/ocornut/imgui)** -- The in-game overlay UI for settings, debug info, and controller config.

## Want to Recomp a Game?

Pick an XBLA title. Seriously, just pick one. The delisted ones especially -- those games deserve to be preserved and playable. Here's what to look for in a good first target:

- **Simpler is better** -- Arcade ports, 2D games, and smaller 3D titles are easier than massive open-world games
- **Single-player or local multiplayer** -- No Xbox Live dependency to stub out
- **Well-known titles** -- More people will care, more people will help test
- **Delisted games** -- These are the most important to preserve. If you can't buy it anymore, recomp is the only way to play it

The tools in this repo will get you from "I have an XBLA download" to "I have generated C++ code" in about 30 minutes. The real work is in the runtime -- implementing the game-specific stubs, fixing rendering quirks, and getting audio/input working. But ReXGlue handles most of the heavy lifting.

**Every game you recomp is a game preserved forever.** No more worrying about delisted stores, dead hardware, or emulator compatibility. The game IS the executable.

Let's go.

## License

Tools and scripts in this repo are provided under the MIT License unless otherwise noted in individual files. `extract_stfs.py` contains code derived from work by Rene Ladan under the 2-clause BSD license.

XenonRecomp, ReXGlue, and other dependencies have their own licenses -- check their respective repositories.
