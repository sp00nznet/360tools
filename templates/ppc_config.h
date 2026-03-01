#pragma once
#ifndef PPC_CONFIG_H_INCLUDED
#define PPC_CONFIG_H_INCLUDED

#include <cstdio>
#include <cstdlib>
#include <cstdint>

// ============================================================================
// Game-specific constants -- update these for your game's PE layout.
// Run find_abi_addrs.py on your PE image to get these values.
// ============================================================================
#define PPC_IMAGE_BASE 0x82000000ull
#define PPC_IMAGE_SIZE 0x4E0000ull
#define PPC_CODE_BASE 0x82090000ull
#define PPC_CODE_SIZE 0x2FD8F8ull

// ============================================================================
// Override __builtin_trap() for switch-case defaults.
// XenonRecomp emits these as safety nets for out-of-range jump table indices,
// but some paths are legitimately reached at runtime. Log a rate-limited
// warning instead of crashing.
// ============================================================================
#ifdef __builtin_trap
#undef __builtin_trap
#endif
#define __builtin_trap() do { \
    static int _tc = 0; \
    if (++_tc <= 10) \
        fprintf(stderr, "[WARN] Switch case out of range (LR=0x%08X) -- continuing\n", \
                (uint32_t)ctx.lr); \
} while(0)

// ============================================================================
// Safe indirect call with NULL check, range validation, and import thunk
// resolution. Handles three cases:
//   1. NULL target -> skip with r3=0
//   2. Import thunks (in image range but below code range) -> decode PPC thunk
//      pattern (lis/lwz/mtctr/bctr), read IAT entry, dispatch to resolved func
//   3. Code range targets -> normal lookup and call
// ============================================================================
#undef PPC_CALL_INDIRECT_FUNC
#define PPC_CALL_INDIRECT_FUNC(x) do { \
    uint32_t _target = (x); \
    if (_target == 0) { \
        static int _nc = 0; \
        if (++_nc <= 5) \
            fprintf(stderr, "[WARN] Indirect call to NULL (LR=0x%08X) -- skipping\n", \
                    (uint32_t)ctx.lr); \
        ctx.r3.u32 = 0; \
        break; \
    } \
    if (_target < (uint32_t)PPC_CODE_BASE || _target >= (uint32_t)(PPC_CODE_BASE + PPC_CODE_SIZE)) { \
        /* Import thunks live in image range but below code range. */ \
        /* Decode: lis r11,hi / lwz r12,lo(r11) / mtctr r12 / bctr */ \
        if (_target >= (uint32_t)PPC_IMAGE_BASE && _target < (uint32_t)PPC_CODE_BASE) { \
            uint32_t insn0 = PPC_LOAD_U32(_target);      /* lis r11, X */ \
            uint32_t insn1 = PPC_LOAD_U32(_target + 4);  /* lwz r12, Y(r11) */ \
            uint16_t hi = insn0 & 0xFFFF; \
            int16_t lo = (int16_t)(insn1 & 0xFFFF); \
            uint32_t iat_addr = ((uint32_t)hi << 16) + lo; \
            uint32_t resolved = PPC_LOAD_U32(iat_addr); \
            { static int _dbg = 0; if (++_dbg <= 5) \
                fprintf(stderr, "[THUNK] 0x%08X -> IAT=0x%08X -> 0x%08X\n", \
                    _target, iat_addr, resolved); } \
            if (resolved >= (uint32_t)PPC_CODE_BASE && \
                resolved < (uint32_t)(PPC_CODE_BASE + PPC_CODE_SIZE)) { \
                PPCFunc* _fn = PPC_LOOKUP_FUNC(base, resolved); \
                if (_fn) { _fn(ctx, base); break; } \
            } \
            static int _imp = 0; \
            if (++_imp <= 20) \
                fprintf(stderr, "[WARN] Import thunk 0x%08X -> 0x%08X (unresolved) -- LR=0x%08X\n", \
                        _target, resolved, (uint32_t)ctx.lr); \
            ctx.r3.u32 = 0; \
            break; \
        } \
        static int _oor = 0; \
        if (++_oor <= 20) \
            fprintf(stderr, "[WARN] Indirect call to 0x%08X outside code range -- LR=0x%08X\n", \
                    _target, (uint32_t)ctx.lr); \
        ctx.r3.u32 = 0; \
        break; \
    } \
    PPCFunc* _fn = PPC_LOOKUP_FUNC(base, _target); \
    if (!_fn) { \
        static int _nf = 0; \
        if (++_nf <= 50) \
            fprintf(stderr, "[WARN] Indirect call to 0x%08X: no recompiled function -- LR=0x%08X\n", \
                    _target, (uint32_t)ctx.lr); \
        ctx.r3.u32 = 0; \
        break; \
    } \
    _fn(ctx, base); \
} while(0)

#ifdef PPC_INCLUDE_DETAIL
#include "ppc_detail.h"
#endif

#endif
