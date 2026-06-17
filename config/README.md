# config/

ReXGlue v0.8.0 is **manifest-driven** — there's no separate hand-written
recompiler config anymore. `rexglue init` generates `<name>_manifest.toml`
(`[project]` + `[entrypoint]`), and codegen reads it.

- To tune codegen (function-boundary hints, etc.), add override tables to that
  manifest — see [`../templates/overlay/manifest-overrides.example.toml`](../templates/overlay/manifest-overrides.example.toml).
- The pre-v0.8.0 standalone config examples (XenonRecomp's `recompiler_config`
  and the early ReXGlue v0.1 format) are archived in [`../legacy/config/`](../legacy/config/).
