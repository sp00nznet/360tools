# Runtime debugging: when a recompile boots but crashes

Once a title builds, the loop is: it boots into the runtime, the guest starts
executing, and then something goes wrong. This is the genuinely hard, per-title
part. Here's the toolkit and the common early crashes, drawn from real titles.

## Step 1 — get a stack on the crash

A recompiled exe that dies with a bare `0xC0000005` and nothing in the log is the
norm: the SDK's VEH only *fixes up* guest memory faults; anything it doesn't handle
falls through unlogged. No `cdb`/WinDbg needed — drop in
[`templates/overlay/debug/crash_diag.cpp`](../templates/overlay/debug/crash_diag.cpp),
build **RelWithDebInfo**, and re-run. It logs the fault address, the operation
(read/write/exec), and a **symbolized stack** (`sub_XXXXXXXX` guest frames + `rex::`
runtime frames) to `crash_diag.log`.

Read the fault address against the guest base (host `0x100000000` == guest `0x0`):

- **`base + 0` (e.g. `0x100000000`)** → a guest **NULL dereference**.
- **`base + <guest addr>`** → the guest computed a bad pointer; the top `sub_`
  frame is where to look.

## Step 2 — common early crashes and their fixes

| Symptom | Cause | Fix |
|---|---|---|
| AV **read** at `base+0` | guest reads through a null pointer (often a failed file open / uninitialized struct) | run with **`--protect_zero=false`** (SDK cvar: maps the zero page so null reads return 0) |
| `[FATAL] Call to invalid or unregistered function at guest address 0x0` | guest **calls** a null/invalid function pointer; v0.8.0's resolver fatals (the old `PPC_CALL_INDIRECT_FUNC` tolerated it) | add [`overlay/src/dispatch_tolerance.cpp`](../templates/overlay/src/dispatch_tolerance.cpp) + `/force:multiple` (no-ops invalid indirect calls) |
| AV at a wild address after the above | you're **symptom-chasing**: the null/garbage came from an earlier failure | stop patching symptoms — go find the root cause (the first thing that failed) |

`--protect_zero=false` and `dispatch_tolerance.cpp` are blunt tolerances: they keep
the guest running past a bad value rather than fixing why it's bad. Use them to get
*past* a crash and see what's next, but if they just lead to another fault, the real
bug is upstream.

## Step 3 — find the root cause

Trace back to the **first** thing that went wrong before the cascade. Frequent
culprits, in order of how often they bite:

1. **A missing kernel/XAM stub** the game called and used the (zero) result of —
   check the link step and `templates/STUBS.md`.
2. **A failed file/device open** the game didn't error-check — look for a
   `VFS: '...' -> [no device]` or `NtCreateFile FAILED` warning just before the
   crash, and make that path resolve (mount the device, or return the status the
   game expects).
3. **A mis-detected function boundary** — codegen produced a wrong/short function;
   add an `[entrypoint.functions]` hint.

The `crash_diag.log` stack tells you which guest function to study; map the
`sub_XXXXXXXX` address back through your generated code (or a disassembler) to see
what it was doing.
