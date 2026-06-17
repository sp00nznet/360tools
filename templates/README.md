# templates/ — v0.8.0 project overlay

ReXGlue v0.8.0 generates the project scaffold for you (`rexglue init` writes
`CMakeLists.txt`, `CMakePresets.json`, `<name>_manifest.toml`, `src/main.cpp`,
and `src/<name>_app.h`). So this is **not** a from-scratch project template — it's
the small set of things you add *on top of* `rexglue init`, plus the playbook.

## What's here

| File | Purpose |
|---|---|
| `overlay/src/stubs.cpp` | Drop-in project stubs for kernel/XAM APIs the runtime doesn't export. Ships a verified `XUsbcam` stub set; add your title's missing symbols here. Add to your CMake sources. |
| `overlay/src/overrides.example.cpp` | Verified port of overriding APIs the SDK **already** implements — multi-user sign-in (kernel override via `REX_HOOK` + `/force:multiple`) and the generated-`sub_` game-logic/license patch. |
| `overlay/src/game_app.reference.h` | Annotated `rex::ReXApp` subclass — the virtual hooks, what each is for, and which old battle-tested fix each replaces. Copy hooks into your generated `<name>_app.h`. |
| `overlay/manifest-overrides.example.toml` | How to add `[entrypoint.functions]` hints (and friends) to your manifest when codegen needs them. |
| `STUBS.md` | The kernel stub & override playbook (missing-API vs override-existing vs codegen hint). |

## The v0.8.0 loop

```bash
# 1. Get default.xex + assets out of the package.
#    Either use the kit's triage tool:
python tools/extract_stfs.py <STFS_package> extracted/
#    ...or skip it: rexglue reads XEX/STFS directly.

# 2. Scaffold the project (writes manifest + CMake + app.h + main.cpp).
rexglue init --project-name mygame --xex-path extracted/default.xex \
             --game-root extracted --project-root mygame

# 3. Recompile PPC -> C++.  If it fails with `UnresolvedCall`, add an
#    [entrypoint.functions] hint (manifest-overrides.example.toml) and re-run,
#    or let the harness auto-resolve it:
cd mygame && rexglue codegen
#    or:  python tools/harness/recomp_harness.py run --titles mygame --max-tier 2

# 4. Build.  If the LINK reports `undefined symbol: _SomeXboxApi`, copy
#    overlay/src/stubs.cpp into mygame/src/, add the missing symbol(s), and add
#    stubs.cpp to the *_SOURCES list in the generated CMakeLists.txt.
cmake --preset win-amd64-release && cmake --build out/build/win-amd64-release

# 5. Run.  --game_data_root points at your extracted assets.
./out/build/win-amd64-release/mygame.exe --game_data_root=../extracted
```

The hard part is no longer extraction or codegen (ReXGlue does those) — it's the
runtime work: missing stubs (`STUBS.md`), per-title data/path quirks (the
`ReXApp` hooks), and rendering/audio edge cases. That's what this overlay and the
docs capture.
