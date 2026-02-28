# XenonRecomp Workflow for The Simpsons Arcade

## Tool Overview

**XenonRecomp** (https://github.com/hedge-dev/XenonRecomp) is a static recompiler that converts Xbox 360 PowerPC executables into C++ source code compilable for x86-64.

### What it produces
- C++ source files with 1:1 translated PowerPC functions
- Each function operates on a `ppc_context` struct (32 GPRs, 32 FPRs, 128 vector regs, CR, CTR, XER, LR, MSR, FPSCR)
- Functions use weak linking for easy hooking
- Handles big-endian to little-endian byte-swapping automatically
- Converts jump tables to C++ switch statements
- Supports mid-ASM hooks for injecting custom code

### What it does NOT provide
- No runtime implementation (graphics, audio, input, I/O, memory, threading)
- No MMIO operations
- No exception handling support

## Step-by-Step Workflow

### Step 1: Build XenonRecomp

```bash
git clone --recursive https://github.com/hedge-dev/XenonRecomp.git tools/XenonRecomp
cd tools/XenonRecomp

# Apply required patches
git apply ../patches/xenonrecomp-altivec-vmx.patch
git apply ../patches/xenonrecomp-missing-instructions.patch

# Build (requires MSVC environment for vcvarsall + clang-cl)
# On Windows, use a batch script:
# call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" amd64
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="C:/Program Files/LLVM/bin/clang-cl.exe" \
  -DCMAKE_CXX_COMPILER="C:/Program Files/LLVM/bin/clang-cl.exe" \
  -DCMAKE_CXX_STANDARD=20
cmake --build build --config Release
```

**Requirements:** CMake 3.20+, Clang 18+ (clang-cl), MSVC 2022+, Ninja

**Patches:**
- `xenonrecomp-altivec-vmx.patch` — Adds 30+ missing Altivec/VMX instruction handlers
- `xenonrecomp-missing-instructions.patch` — Adds 21 missing PPC instructions needed by this game:
  - Update-form loads: lhzu, lhau, lbzux, lhzux, lwzux, ldux, lfsu, lfsux, lfdu
  - Update-form stores: sthu, sthux, stbux, stdux, stfsu, stfdu
  - Conditional branches: bdzf, bdnzt
  - Integer arithmetic: addc, addme, subfze
  - Vector: lvehx

### Step 2: Extract Game Files

```bash
# Extract STFS container
python tools/extract_stfs.py

# Extract PE from XEX2 (handles LZX decompression)
python tools/extract_pe.py extracted/default.xex extracted/pe_image.bin
```

### Step 3: Run XenonAnalyse

```bash
cd config
../tools/XenonRecomp/build/XenonAnalyse/XenonAnalyse.exe ../extracted/default.xex simpsons_switch_tables.toml
```

### Step 4: Locate ABI Addresses

```bash
python tools/find_abi_addrs.py extracted/pe_image.bin
```

Results for this game (already in config/simpsons.toml):
- savegprlr_14 = 0x8225D390, restgprlr_14 = 0x8225D3E0
- savefpr_14 = 0x8225E270, restfpr_14 = 0x8225E2BC
- savevmx_14 = 0x8225E6C0, restvmx_14 = 0x8225E958
- savevmx_64 = 0x8225E754, restvmx_64 = 0x8225E9EC

### Step 5: Run XenonRecomp

```bash
cd config
../tools/XenonRecomp/build/XenonRecomp/XenonRecomp.exe simpsons.toml \
  ../tools/XenonRecomp/XenonUtils/ppc_context.h
```

**Output:** 59 source files (~45MB) with 15,237 recompiled functions in `ppc/`

### Step 5b: Post-process Generated Headers

The generated `ppc_recomp_shared.h` uses `PPC_EXTERN_FUNC` for all declarations, including
`__imp__*` kernel import stubs. The ReXGlue SDK defines these stubs with `extern "C"` linkage,
so we must convert the import declarations to use `PPC_EXTERN_IMPORT` (defined in `ppc_detail.h`):

```bash
cd ppc
sed -i 's/PPC_EXTERN_FUNC(__imp__/PPC_EXTERN_IMPORT(__imp__/g' ppc_recomp_shared.h
```

This ensures the C linkage names match between the recompiled code references and the SDK's
kernel stub implementations in `rexkernel.lib`.

### Step 6: Build ReXGlue SDK

```bash
git clone --recursive https://github.com/rexglue/rexglue-sdk.git tools/rexglue-sdk
cd tools/rexglue-sdk

# Fix Git symlinks on Windows (libmspack uses symlinks that Git stores as plain text)
# See build script for details

# Build (requires MSVC environment + clang in PATH)
cmake --preset win-amd64
cmake --build --preset win-amd64
cmake --install out/build/win-amd64 --prefix out/install/win-amd64
```

### Step 7: Build Project

```bash
cd project
cmake -B out -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="C:/Program Files/LLVM/bin/clang.exe" \
  -DCMAKE_CXX_COMPILER="C:/Program Files/LLVM/bin/clang++.exe" \
  -DCMAKE_CXX_STANDARD=23
cmake --build out --config Release
```

**Key CMake settings:**
- `/WHOLEARCHIVE:rexkernel.lib` on Windows (forces all kernel stubs to link)
- `PPC_INCLUDE_DETAIL` compile definition (enables ppc_detail.h with custom macros)
- SIMDE include path (`${REXSDK}/include/simde`) for PPC vector intrinsic headers

### Step 8: Runtime Implementation (The Hard Part)

The generated C++ is just the translated game logic. The ReXGlue SDK provides the runtime:

1. **Memory management** - `rex::kernel` maps Xbox 360 virtual address space
2. **Graphics** - `rex::graphics` translates Xenos GPU draw calls to D3D12
3. **Audio** - `rex::audio` handles XMA/PCM audio decoding and playback
4. **Input** - `rex::input` maps Xbox 360 controller calls to PC input
5. **File I/O** - `rex::filesystem` translates Xbox 360 paths to PC paths
6. **Threading** - `rex::kernel` handles Xbox 360 threading model
7. **System calls** - `rex::kernel` provides 253 Xbox 360 kernel stubs
8. **UI** - `rex::ui` provides ImGui-based debug overlays

Game-specific stubs not in the SDK are in `project/src/stubs.cpp`.

### Step 9: Iterate

- Fix recompilation errors
- Add `functions` entries for broken function boundaries
- Add mid-ASM hooks where needed

### Step 10: Optimize

Enable TOML optimization flags one by one after everything works.

## Reference Projects

- [UnleashedRecomp](https://github.com/hedge-dev/UnleashedRecomp) - Sonic Unleashed recomp
- [vig8](https://github.com/sp00nznet/vig8) - Vigilante 8 Arcade recomp (sister project)
