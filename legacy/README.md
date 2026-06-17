# legacy/ — pre-v0.8.0 (XenonRecomp-era) artifacts

These files served the original pipeline that fed **hedge-dev/XenonRecomp** and an
early **ReXGlue v0.1.x** runtime. As of ReXGlue **v0.8.0**, the toolkit pivoted:
ReXGlue ships its own recompiler (`rexglue codegen`), its own XEX/STFS/LZX/AES
extraction, jump-table/vtable/ABI detection, and a manifest-driven project model —
so XenonRecomp is no longer a dependency and most of this is obsolete.

Kept for reference and for anyone still on the old stack:

| Path | What it was | Why retired |
|---|---|---|
| `templates/project-xenonrecomp/` | v0.1.x project template (`main.cpp` with VEH handlers, `menu.cpp`/`settings.cpp`, `keyboard_driver.cpp`, `test_boot.cpp`) | v0.8.0 `ReXApp` provides windowing, VEH/crash handling, ImGui overlay/console/settings, and SDL3 input. Project now subclasses `rex::ReXApp` with virtual hooks. |
| `templates/ppc_config.h` | `PPC_CALL_INDIRECT_FUNC` / `__builtin_trap` / `PPC_UNIMPLEMENTED` overrides | Those macros no longer exist in v0.8.0; indirect dispatch is the SDK's `FunctionDispatcher`. |
| `tools/post_codegen.py` | Re-applied the `PPC_*` macro overrides after each codegen | The macros it patched are gone. |
| `patches/` | XenonRecomp instruction patches (altivec-vmx, missing-instructions, saintsrow) | Only relevant on the XenonRecomp track; ReXGlue's own codegen has its instruction coverage in `src/codegen/builders/`. |

Still-useful patterns from here have been **ported and verified** for v0.8.0:
- `templates/project-xenonrecomp/src/stubs.cpp` — multi-user sign-in, content-license
  bypass, XAM UI stubs. These override APIs the SDK **does** implement; the verified
  v0.8.0 form lives in `templates/overlay/src/overrides.example.cpp` (`REX_HOOK` +
  `/force:multiple`), with the mechanism documented in `templates/STUBS.md`.
