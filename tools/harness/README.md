# Recomp Harness

Batch-runs the ReXGlue v0.8.0 recompilation loop across a whole title library to
turn one-off observations into a **compatibility matrix** and a **catalog of
recurring failure modes** — the data that actually hardens the toolkit (and tells
us what to upstream to ReXGlue).

## Tiers (cost grows steeply — triage is cheap and scales to the whole library)

| Tier | Stage | Cost | Notes |
|---|---|---|---|
| 1 | extract → profile | seconds, ~1 MB kept | rar → STFS → `default.xex`; base/size/entry |
| 2 | + codegen | seconds, no VS env | `rexglue init`+`codegen` with **auto-resolve** |
| 3 | + build | minutes, GB-scale | cmake configure+build (opt-in) — needs VS2022 + LLVM |
| 4 | + boot | flaky, needs display | timed launch, captures furthest runtime stage (opt-in) |

**Auto-resolve:** v0.8.0 codegen fails fatally on `UnresolvedCall` (a branch whose
target the scanner didn't place in a function). The harness parses those targets,
injects `[entrypoint.functions]` entry hints into the manifest, and re-runs codegen
— repeating up to `--max-codegen-iters` times. On the pilot this took codegen from
1/6 → 6/6 passing (avg 2.8 hints/title). Hints are entry-only (size discovered);
fine for triage, verify before shipping a specific title.

**Import inventory** is harvested from ReXGlue's own resolved `*_init.h`
(`__imp__NAME`), not `parse_xex_imports.py` (which emits unreliable ordinals).

## Usage

```bash
# Triage the whole XBLA library (extract→profile→codegen), resumable:
python recomp_harness.py run --library XBLA --max-tier 2

# A few titles, all the way through boot (opt-in, needs VS env + retained artifacts):
python recomp_harness.py run --titles "Aegis Wing,1942*" --max-tier 4 \
    --keep-generated --keep-assets

# Re-aggregate the report from existing per-title results:
python recomp_harness.py report
```

Key flags: `--titles` (comma globs/substrings), `--limit N`, `--force` (re-run
recorded titles), `--sdk <rexglue-sdk root>`, `--out <results root>`,
`--keep-generated` (tier 3), `--keep-assets` (tier 4), `--max-codegen-iters`.

## Outputs (`--out`, default `D:\recomp\360\_harness`)

- `results/<id>.json` — one structured record per title (every stage, timing,
  errors, imports, hints). Resumable: a recorded title is skipped unless `--force`.
- `REPORT.md` — aggregate dashboard: pipeline funnel, image-base distribution
  (flags non-`0x82` high-base titles), codegen analysis-error catalog, auto-resolve
  stats, **top kernel imports across titles** (stub-prioritization list), undefined
  link symbols, giant-function warnings, boot furthest-stage histogram.

Each title is isolated and timed; one title's failure never aborts the batch.
Triage (tiers 1–2) needs no Visual Studio environment; build/boot do.
