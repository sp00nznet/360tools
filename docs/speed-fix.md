# Speed Fix: VdSwap Frame Limiter + Timebase Scaling

## Problem
The game ran at half speed (~30 FPS game logic) despite reporting ~70 FPS in the overlay.

## Root Causes Found

### 1. VdSwap Sleep(16) + Windows Timer Granularity

**File:** `src/kernel_stubs.cpp` — `PPC_FUNC(__imp__VdSwap)`

The VdSwap stub (frame swap function) had a `Sleep(16)` call to cap the frame rate at ~60 FPS. However, Windows' default timer resolution is **15.6ms**, which means `Sleep(16)` actually sleeps for **~31ms** (rounds up to the next timer tick). This alone caused the game to run at ~32 FPS.

Additionally, the SDK's vsync worker thread independently fires `MarkVblank()` every 16ms. If the game waits on vblank interrupts AND VdSwap sleeps, you get double-throttling: ~16ms vblank wait + ~31ms Sleep = ~47ms per frame = ~21 FPS.

**Fix:** Replace `Sleep(16)` with a precise frame limiter using `QueryPerformanceCounter`:

```cpp
// In VdSwap:
static LARGE_INTEGER s_freq = {}, s_last = {};
if (s_freq.QuadPart == 0) {
    QueryPerformanceFrequency(&s_freq);
    QueryPerformanceCounter(&s_last);
}
const int64_t target_us = 16667; // 16.667ms = 60 Hz
LARGE_INTEGER now;
for (;;) {
    // pump Win32 messages here too
    QueryPerformanceCounter(&now);
    int64_t elapsed_us = (now.QuadPart - s_last.QuadPart) * 1000000 / s_freq.QuadPart;
    if (elapsed_us >= target_us) break;
    if (elapsed_us < target_us - 2000)
        Sleep(1);  // coarse yield if >2ms remain
}
QueryPerformanceCounter(&s_last);
```

This gives precise 60 Hz frame pacing regardless of Windows timer resolution.

### 2. __rdtsc() Timebase Mismatch (Secondary Fix)

**File:** `ppc/ppc_detail.h`

XenonRecomp generates `__rdtsc()` for PPC `mftb` (move from timebase) instructions. On the Xbox 360, the timebase runs at **49.875 MHz**. On modern PCs, `__rdtsc()` returns the CPU's TSC counter which runs at **~3-4 GHz** — roughly 60-80x faster.

The SDK provides `PPC_QUERY_TIMEBASE()` (which calls `rex::chrono::Clock::QueryGuestTickCount()`) that returns properly scaled guest ticks at 50 MHz. But XenonRecomp doesn't know about this macro.

**Fix:** Override `__rdtsc()` with a macro in `ppc_detail.h` (included before `ppc_context.h`):

```cpp
#include <rex/time/clock.h>

inline uint64_t __ppc_query_timebase() {
    return rex::chrono::Clock::QueryGuestTickCount();
}

#define __rdtsc() __ppc_query_timebase()
```

This intercepts all 21 `mftb` → `__rdtsc()` calls in the generated PPC code without touching the generated files.

## Applying to vig8

1. **VdSwap fix** — Edit `src/kernel_stubs.cpp`, find `PPC_FUNC(__imp__VdSwap)`, replace `Sleep(16)` with the QueryPerformanceCounter frame limiter above.

2. **Timebase fix** — Edit `ppc/ppc_detail.h`, add the `__rdtsc()` override macro shown above. Requires `#include <rex/time/clock.h>`.

3. **Rebuild** — Both fixes require a full rebuild since `ppc_detail.h` is included by all recompiled PPC files.

## Why This Matters

- The VdSwap fix is the critical one — it's the difference between half speed and correct speed
- The timebase fix is secondary but ensures game logic that uses `mftb` for timing (profiling, delays, etc.) gets correct values
- Both fixes apply to any XenonRecomp-based static recompilation project using the ReXGlue SDK
