# XBLA library triage — findings

Results of running `tools/harness/recomp_harness.py` across the XBLA library on
ReXGlue v0.8.0. The goal was *generalizing*: turn one-off observations into a
compatibility matrix, a default stub bundle, and a catalog of the codegen defects
worth chasing. Reproduce with:

```bash
python tools/harness/recomp_harness.py run --library XBLA --max-tier 2   # triage all
python tools/harness/recomp_harness.py run --titles "..." --max-tier 3 --keep-generated  # build sample
```

## Pipeline funnel (747 titles, tier 2)

| Stage | Result | Notes |
|---|---|---|
| extract | ~97% | Failures are mostly episodic/DLC packages with no standalone XEX (Telltale, Minecraft Story Mode, …) — reclassified "not a recomp target", not real failures. |
| codegen | **~99%** (of extractable) | With auto-resolve. **Without** it only ~16% codegen clean — function-hint injection is the difference between 16% and 99%. |

Auto-resolve injects `[entrypoint.functions]` hints for `UnresolvedCall` errors and
re-runs codegen. Most titles need a handful of hints (avg ~7); a few need many
(timeouts recovered with a higher `--t-codegen`).

## Default stub bundle: XUsbcam

A tier-3 build sample (build → link) found that **the only consistently missing
kernel export is the XUsbcam (Vision Camera) API**. It's imported by **~26% of
titles** (184/700) — none of them camera games; they pull it in via a shared MS
XDK library and never use it. The SDK implements it in
`src/kernel/xboxkrnl/xboxkrnl_usbcam.cpp` but leaves it commented out of the
runtime build, so the symbols aren't exported.

→ `templates/overlay/src/stubs.cpp` ships exactly these stubs. It's the highest-value
default: it fixes the link for ~1/4 of the library. A confirmation build of titles
importing the other suspicious clusters (XeCrypt, LDI, Etx, PsCam, XeKeys, Hid) all
linked clean — the SDK's ~2,866 exports cover everything else.

## Cohorts worth knowing

- **High-base titles (`0x92000000`)** — 4 found: Aegis Wing, Hexic HD, Hexic 2, UNO.
  These codegen and *build* fine but fail at runtime: the function table lands at
  `IMAGE_BASE+IMAGE_SIZE`, which is misaligned and outside the guest heap. A
  small, well-defined cohort to fix in the runtime layer.
- **Emulation-wrapper XBLA** — Super SF2 Turbo HD (~60), Puzzle Fighter HD,
  Virtual On, Castlevania SotN, Ikaruga. Produce many "giant function" warnings:
  the bundled emulator core gets mis-detected as huge functions. Usually still
  builds; flagged as a class.

## Codegen defects (fork-track candidates)

Two distinct failure modes survive auto-resolve — both point at ReXGlue's codegen
*analysis*, to be addressed on a fork (we do not push upstream):

1. **Undeclared-label** — codegen "passes" but emits uncompilable C++:
   `error: use of undeclared label 'loc_XXXXXXXX'` (a `goto`/jump to a label it
   never declared). Seen on Minesweeper Flags, Scrap Metal.
2. **Auto-resolve divergence** — hint injection never converges; each round spawns
   hundreds of *new* unresolved calls (Earthworm Jim HD: 1,496 hints over 16
   iterations, still failing). Seen on Batman Arkham Origins Blackgate, Earthworm
   Jim HD, Jet Set Radio, Super Meat Boy, TNT Racers. The harness now bails on
   divergence (`--max-hints` / `--diverge-round`) instead of burning iterations.

Both likely share a root cause in function-boundary / jump-target analysis.

## Heavy titles

A couple of large titles (Halo Spartan Assault, Happy Wars) exceed even a 1,200 s
single-pass codegen timeout — genuinely big, not broken. Raise `--t-codegen`.
