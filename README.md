# 360tools

**Everything you need to statically recompile Xbox 360 XBLA games to native PC executables.**

No emulator. No interpreter. No JIT. Just your Xbox 360 game, recompiled to C++ and running natively on x86-64 at full speed.

```
   XBLA Game (PowerPC)
         |
    [ extract_stfs.py ]     <-- crack open the STFS/LIVE package
         |
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
| **`extract_stfs.py`** | Rips files out of STFS/LIVE/PIRS Xbox 360 packages. Point it at a downloaded XBLA title and it pulls out the XEX and all game assets. |
| **`extract_pe.py`** | Decrypts (AES-128) and decompresses (LZX or basic block) the PE image buried inside an XEX2 file. This is what XenonRecomp actually needs. |
| **`lzx_decompress.py`** | Pure Python LZX decompression. Used by `extract_pe.py` for XEX files with LZX-compressed PE images. |
| **`find_abi_addrs.py`** | Scans the PE binary for all 10 standard PowerPC ABI helper functions (`__savegprlr_14`, `__restfpr_14`, VMX save/restore, `setjmp`/`longjmp`, etc.) and outputs them in TOML format ready for XenonRecomp. |
| **`extract_switch_tables.py`** | Finds PPC switch/jump tables by pattern-matching `add r12,r12,r0; mtctr r12; bctr` sequences, reads the table data, and generates `[[switch]]` TOML entries. Handles u8/u16 entries, scaling, bounds checking. |
| **`find_missing_vtable_funcs.py`** | Scans the PE data section for C++ vtable entries pointing to functions that XenonRecomp missed (because they're never called directly -- only through vtable dispatch). Classifies entries as THUNK or FUNC. |
| **`parse_xex_imports.py`** | Parses XEX2 import tables to identify which kernel/XAM functions the game actually calls. Helps you know which stubs you need to implement. |
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
  ppc_config.h              # PPC_INCLUDE_DETAIL gate for macro overrides
  project/
    CMakeLists.txt           # ReXGlue SDK build with WHOLEARCHIVE linking
    CMakePresets.json         # Clang + Ninja preset (win-amd64)
    src/
      main.cpp               # Windowed app: VEH crash handler, null page handler,
                              #   F11 fullscreen, ImGui overlay, stderr logging
      menu.cpp / menu.h      # Win32 native menu bar + ImGui config dialogs
                              #   (Graphics, Game, Debug, Controls)
      settings.cpp / settings.h  # TOML-based settings persistence via toml++
      stubs.cpp              # Game-specific kernel stub overrides
                              #   (license bypass, multi-user sign-in, etc.)
      keyboard_driver.cpp/h  # WASD/arrow keyboard input -> gamepad mapping
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

- **Python 3.8+** with `pycryptodome` (`pip install pycryptodome`)
- **CMake 3.20+**, **Ninja**, **Clang 18+** (clang-cl on Windows)
- **MSVC 2022** (for Windows SDK headers)
- **Git** (for cloning XenonRecomp and ReXGlue)

### The Pipeline

```bash
# 1. Get your game files out of the XBLA package
python tools/extract_stfs.py path/to/XBLA_PACKAGE output_dir/

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
C++ vtable calls on Xbox 360 need NULL checks, code range validation, and graceful fallback instead of hard crashes. The `generated/*_init.h` template includes the battle-hardened macro.

### VEH Null Page Handler
A Vectored Exception Handler that intercepts null pointer dereferences in guest memory space, decodes the x86-64 instruction, zeros the destination register, and continues execution. Prevents crashes from lazy null checks that the Xbox 360 hardware handled silently.

### ROV vs RTV Render Path
If you're getting white screens with certain render target formats (especially `k_2_10_10_10_FLOAT` + 4xMSAA), switch to the ROV (Rasterizer Ordered Views) path. ROV uses pixel shader interlock for EDRAM emulation and handles these edge cases correctly.

## Projects Built With These Tools

| Game | Repo | Status |
|------|------|--------|
| **The Simpsons Arcade** (XBLA, 2012) | [simpsonsarcade](https://github.com/sp00nznet/simpsonsarcade) | Playable -- full speed, audio, input, graphics |
| **Vigilante 8 Arcade** (XBLA) | [vig8](https://github.com/sp00nznet/vig8) | Playable -- 90 FPS, split-screen multiplayer, 79 shaders |
| **Crazy Taxi** (XBLA, 2010) | [ctxbla](https://github.com/sp00nznet/ctxbla) | In progress -- keyboard input, frame timing done |
| **Virtual On: Oratorio Tangram** (XBLA) | [voot](https://github.com/sp00nznet/voot) | Foundation -- project structure, codegen config ready |

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
