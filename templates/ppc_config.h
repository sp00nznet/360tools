#pragma once
#ifndef PPC_CONFIG_H_INCLUDED
#define PPC_CONFIG_H_INCLUDED

#include <cstdio>
#include <cstdlib>
#include <cstdint>

#define PPC_IMAGE_BASE 0x82000000ull
#define PPC_IMAGE_SIZE 0x4E0000ull
#define PPC_CODE_BASE 0x82090000ull
#define PPC_CODE_SIZE 0x2FD8F8ull

// Counter for NULL indirect calls (defined in main.cpp)
extern uint64_t g_null_icall_count;

// Safe indirect call: validates target is in code range and function exists
#define PPC_CALL_INDIRECT_FUNC(x) do { \
    uint32_t _target = (x); \
    if (_target == 0) { \
        g_null_icall_count++; \
        if (g_null_icall_count <= 5) { \
            fprintf(stderr, "[WARN] Indirect call to NULL (LR=0x%08X, r3=0x%08X) - skipping\n", \
                    (uint32_t)ctx.lr, ctx.r3.u32); \
            fflush(stderr); \
        } \
        ctx.r3.u32 = 0; \
        break; \
    } \
    if (_target < (uint32_t)PPC_CODE_BASE || _target >= (uint32_t)(PPC_CODE_BASE + PPC_CODE_SIZE)) { \
        static int _oor_count = 0; \
        if (++_oor_count <= 20) { \
            fprintf(stderr, "[WARN] Indirect call to 0x%08X outside code [0x%08X-0x%08X) — skipping\n", \
                    _target, (uint32_t)PPC_CODE_BASE, (uint32_t)(PPC_CODE_BASE + PPC_CODE_SIZE)); \
            fprintf(stderr, "  LR=0x%08X, CTR=0x%08X, r1=0x%08X, r3=0x%08X\n", \
                    (uint32_t)ctx.lr, ctx.ctr.u32, ctx.r1.u32, ctx.r3.u32); \
            fflush(stderr); \
        } \
        ctx.r3.u32 = 0; \
        break; \
    } \
    PPCFunc* _fn = PPC_LOOKUP_FUNC(base, _target); \
    if (!_fn) { \
        fprintf(stderr, "[FATAL] Indirect call to 0x%08X: NULL function slot\n", _target); \
        fflush(stderr); abort(); \
    } \
    _fn(ctx, base); \
} while(0)

#ifdef PPC_INCLUDE_DETAIL
#include "ppc_detail.h"
#endif

#endif
