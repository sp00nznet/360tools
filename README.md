# 360tools

**A toolkit and playbook for statically recompiling Xbox 360 games to native PC executables — built around the [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk).**

No emulator. No interpreter. No JIT. Your Xbox 360 game, recompiled to C++ and running natively on x86-64.

```
   XBLA / disc package
          |
   [ extract ]  default.xex + assets   (rexglue reads XEX/STFS directly,
          |                              or use tools/ for triage)
   [ rexglue init ]   ── scaffold project + manifest
          |
   [ rexglue codegen ] ── PowerPC → C++   (auto-resolve hints via tools/harness)
          |
   [ + stubs / hooks ] ── fill gaps the runtime doesn't cover (templates/)
          |
   [ cmake build ]    ── link against the ReXGlue runtime
          |
   Native x86-64 .exe
```

## Heads-up: this is the v0.8.0 era

ReXGlue **v0.8.0** is a self-contained recompiler. It ships its own codegen
(`rexglue codegen`), its own XEX/STFS/LZX/AES extraction, jump-table / RTTI-vtable
/ ABI-helper detection, and a manifest-driven project model. **XenonRecomp is no
longer required** — the older pipeline that fed it now lives in [`legacy/`](legacy/).
What's left for you is the genuinely hard part: runtime integration (stubs,
per-title quirks, rendering/audio), which is what this repo now focuses on.

## What's in the box

### `tools/harness/` — the generalizing engine *(start here for breadth)*

`recomp_harness.py` batch-runs the whole loop across a library of titles and
aggregates a **compatibility matrix** + a **failure-mode catalog**: codegen
success rate, the cross-title kernel-import frequency table (your stub-priority
list), high-base titles, analysis-error and giant-function catalogs, and (opt-in)
build/boot results. Tiered and resumable; triage (extract→codegen) scales to a
whole library cheaply. It even **auto-resolves** codegen's `UnresolvedCall` errors
by injecting function hints and retrying. See [`tools/harness/README.md`](tools/harness/README.md).

### `tools/` — triage & fallback helpers

Standalone Python tools, handy when you want to inspect a binary without building
the SDK. ReXGlue now does most of this internally, so these are **triage/fallback**,
not the main path (and a couple have known limits — noted below).

| Script | What it does |
|--------|-------------|
| `extract_stfs.py` | Rip files out of STFS/LIVE/PIRS/CON packages (handles the `start_block=0` edge case). |
| `extract_iso.py` | Extract Xbox 360 XDVDFS disc images (XGD1/XGD2). |
| `xex_info.py` | Quick XEX2 header dump — base address, image size, entry, imports. Best triage tool. |
| `extract_pe.py` | XEX2 AES-decrypt + LZX-decompress to a raw PE. *Known limit: fails on some compression variants — use rexglue, which decompresses internally.* |
| `parse_xex_imports.py` | XEX import-table parser. *Known limit: unreliable ordinals — for an authoritative import list use the harness (harvests from ReXGlue's own output).* |
| `find_abi_addrs.py`, `extract_switch_tables.py`, `find_missing_vtable_funcs.py` | ABI-helper / jump-table / vtable scanners. **Superseded** by ReXGlue's built-in analysis; kept for reference. |

### `templates/` — v0.8.0 project overlay

`rexglue init` scaffolds the project; this overlay adds what it doesn't: a
drop-in `stubs.cpp`, an annotated `ReXApp` hook reference, manifest-override
examples, and the [`STUBS.md`](templates/STUBS.md) playbook. See
[`templates/README.md`](templates/README.md).

### `docs/`, `config/`, `legacy/`

Workflow & analysis notes (incl. [`docs/rexglue-workflow.md`](docs/rexglue-workflow.md)
and the library-wide [`docs/xbla-triage-findings.md`](docs/xbla-triage-findings.md));
example configs; and the archived XenonRecomp-era kit
(see [`legacy/README.md`](legacy/README.md)).

## Quick start

```bash
# Prereqs: Python 3.8+, CMake 3.25+, Ninja, Clang 20+, VS2022 (Windows SDK + D3D12),
#          and a built ReXGlue SDK (see its repo). git clone --recursive the SDK;
#          on Windows, materialize libmspack's symlinked sources before building.

# 1. Extract (or point rexglue straight at the package)
python tools/extract_stfs.py path/to/PACKAGE extracted/

# 2. Scaffold + recompile
rexglue init --project-name mygame --xex-path extracted/default.xex \
             --game-root extracted --project-root mygame
cd mygame && rexglue codegen        # add [entrypoint.functions] hints if it complains

# 3. Build (link errors -> add missing stubs from templates/overlay/src/stubs.cpp)
cmake --preset win-amd64-release && cmake --build out/build/win-amd64-release

# 4. Run
./out/build/win-amd64-release/mygame.exe --game_data_root=../extracted
```

To survey many titles at once instead:

```bash
python tools/harness/recomp_harness.py run --library XBLA --max-tier 2
# -> per-title results + REPORT.md (funnel, import table, error catalog, ...)
```

## Runtime knowledge

The v0.8.0 SDK now provides what used to be hand-rolled in every project: the
window + D3D12/Vulkan presentation and frame loop, the ImGui debug overlay /
console / settings dialogs, SDL3 input (keyboard+gamepad), crash/VEH handling,
guest function dispatch, and frame pacing + guest timebase. So the old
"battle-tested fixes" for those are now **SDK-internal** — you mostly write:

- **Kernel stubs** for APIs the runtime doesn't export — see [`templates/STUBS.md`](templates/STUBS.md).
- **`ReXApp` hook overrides** for per-title quirks (GPU config in `OnPreSetup`,
  data patches in `OnPostLoadXexImage`/`OnPreLaunchModule`, paths in
  `OnConfigurePaths`) — see `templates/overlay/src/game_app.reference.h`.
- **Manifest hints** when codegen can't resolve a boundary.

## The Stack

- **[ReXGlue SDK](https://github.com/rexglue/rexglue-sdk)** — the recompiler + runtime (codegen, XboxKrnl/XAM/XBDM kernel, D3D12 **and** Vulkan GPU backends derived from [Xenia](https://github.com/xenia-project/xenia), XMA audio via FFmpeg, SDL3 input). v0.8.0+. Build with **Clang 20+**, **CMake 3.25+**, Ninja.
- **[Xenia](https://github.com/xenia-project/xenia)** — the emulator whose GPU code underpins ReXGlue's backends.
- **SDL3**, **Dear ImGui**, **toml++**, **FFmpeg**, **SIMDE** — runtime/codegen dependencies (vendored by the SDK).

> Note: we build against and fork the ReXGlue SDK as needed, but we do **not** push changes upstream.

## Projects Built With These Tools

| Game | Repo | Status |
|------|------|--------|
| The Simpsons Arcade (XBLA) | [simpsonsarcade](https://github.com/sp00nznet/simpsonsarcade) | Playable |
| Vigilante 8 Arcade (XBLA) | [vig8](https://github.com/sp00nznet/vig8) | Playable |
| Guitar Hero II (360) | [gh2](https://github.com/sp00nznet/gh2) | Playable (controller WIP) |
| Crazy Taxi (XBLA) | [ctxbla](https://github.com/sp00nznet/ctxbla) | Playable (XMA WIP) |
| Comix Zone (XBLA) | [comixzone](https://github.com/sp00nznet/comixzone) | Analysis |
| Virtual On (XBLA) | [voot](https://github.com/sp00nznet/voot) | Foundation |
| Saints Row (360) | [saintsrow](https://github.com/sp00nznet/saintsrow) | Planning |

> These shipped on an earlier ReXGlue (v0.1.x). The current loop and the runtime
> APIs differ — see [`legacy/`](legacy/) for the older patterns.

## Want to Recomp a Game?

Pick an XBLA title — the delisted ones especially. Simpler is better (arcade
ports, 2D, smaller 3D); single-player or local-multiplayer avoids Xbox Live
stubbing; well-known titles get more testers. Extraction and codegen are minutes
of work now; the runtime is the craft. **Every game you recomp is a game
preserved forever.**

## License

MIT unless noted otherwise per file. `extract_stfs.py` includes code derived from
work by Rene Ladan (2-clause BSD). ReXGlue and other dependencies carry their own
licenses.
