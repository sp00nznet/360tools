# ReXGlue v0.8.0 workflow

End-to-end: from an XBLA/disc package to a running native `.exe`, on the
self-contained ReXGlue v0.8.0 toolchain (no XenonRecomp). Commands shown for
Windows (Clang + VS2022); Linux is analogous with the `linux-*` presets.

## 0. Build the ReXGlue SDK (once)

Requirements: **Clang 20+** (we used 21.1.8), **CMake 3.25+**, **Ninja**, **VS2022**
(Windows SDK + D3D12 headers). The SDK's `win-amd64` preset uses `clang`/`clang++`
(not clang-cl) and installs to `out/install/win-amd64`.

```bash
# Resilient clone (a full --recurse-submodules clone can fail on one big pack):
git clone --branch v0.8.0 --depth 1 --no-recurse-submodules \
  https://github.com/rexglue/rexglue-sdk.git rexglue-sdk
cd rexglue-sdk
# Init only what a Windows D3D12 build needs (skip the Vulkan/SPIRV stack + catch2):
for m in fmt spdlog snappy utfcpp xxHash simde tomlplusplus cli11 o1heap inja \
         libmspack sdl3 tracy imgui FFmpeg; do
  git submodule update --init --depth 1 thirdparty/$m
done
```

**Windows gotcha — libmspack symlinks.** `thirdparty/libmspack/cabextract/mspack/*`
are git symlinks (`120000`) to `../../libmspack/mspack/*`. On Windows they check
out as text stubs and the build fails with `expected identifier or '('` on
`lzxd.c:1`. Materialize them (overwrite each stub with its target's contents):

```bash
cd thirdparty/libmspack
for f in $(git ls-files -s | awk '$1=="120000"{print $4}'); do
  cp -f "$(cd "$(dirname "$f")" && realpath -m "$(cat "$f")")" "$f"; done
cd ../..
```

Configure + build + install (from a VS dev shell with LLVM ahead on PATH):

```powershell
& "...\Common7\Tools\Launch-VsDevShell.ps1" -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$env:PATH = "C:\Program Files\LLVM\bin;$env:PATH"
cmake --preset win-amd64                       # D3D12=ON, Vulkan=OFF, Tracy=ON on Windows
cmake --build   out/build/win-amd64 --config Release
cmake --install out/build/win-amd64 --config Release
```

You now have `out/install/win-amd64/bin/rexglue.exe` (+ `rexruntime.dll`) and a
`find_package(rexglue)` package registered for projects to link against.

## 1. Extract the game

```bash
python tools/extract_stfs.py path/to/PACKAGE extracted/   # -> extracted/default.xex + assets
# (rexglue can also read XEX/STFS directly; extract_stfs is convenient for triage.)
```

Sanity-check the binary: `python tools/xex_info.py extracted/default.xex`. Note
the **base address** — the usual XBLA base is `0x82000000`. A non-standard base
(e.g. Aegis Wing's `0x92000000`) currently breaks the runtime's function-table
placement; expect that title class to need a fix.

## 2. Scaffold + recompile

```bash
rexglue init --project-name mygame --xex-path extracted/default.xex \
             --game-root extracted --project-root mygame
cd mygame
rexglue codegen
```

Codegen is strict: it **fails** on `UnresolvedCall: 0xTARGET from 0xSITE` (a branch
target it couldn't place in a function). Resolve by adding a function-entry hint
to `mygame_manifest.toml`:

```toml
[entrypoint.functions]
0x8207D730 = {}      # entry-only; discovery determines the extent
```

Re-run codegen. To do this automatically (and across many titles), use the
harness, which parses the unresolved targets, injects hints, and retries:

```bash
python tools/harness/recomp_harness.py run --titles mygame --max-tier 2
```

## 3. Build

```powershell
# (VS dev shell + LLVM on PATH, as in step 0)
cmake --preset win-amd64-release "-DCMAKE_PREFIX_PATH=...\rexglue-sdk\out\install\win-amd64"
cmake --build out/build/win-amd64-release
```

If the **link** fails with `undefined symbol: _SomeXboxApi`, the game imports a
kernel/XAM function `rexruntime` doesn't export. Copy
`templates/overlay/src/stubs.cpp` into `mygame/src/`, add the missing symbol(s)
(see `templates/STUBS.md`), and add `stubs.cpp` to the `*_SOURCES` list in the
generated `CMakeLists.txt`. (e.g. `XUsbcam*` is a common one — the SDK implements
it but leaves it out of the runtime build.)

## 4. Run

```powershell
.\out\build\win-amd64-release\mygame.exe --game_data_root=..\extracted
```

A healthy boot logs (to `out/build/win-amd64-release/logs/`): D3D12 device →
`FunctionDispatcher initialized` → SDL3 input → audio + XMA decoder thread → GPU
threads → `Runtime initialized successfully` → `Function table initialized for
module` → `Loading XEX image` → shader storage → guest code. From here it's
runtime work: per-title stubs, data/path quirks (`ReXApp` hooks), and
rendering/audio. See `docs/binary-analysis.md` and `docs/speed-fix.md` for
background (note the speed fixes are now handled inside the SDK).
