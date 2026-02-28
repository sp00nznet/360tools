// Minimal console test for ReXGlue Runtime initialization
// This skips the windowed app framework to isolate crashes

#include "vig8_config.h"
#include "vig8_init.h"

#include <rex/runtime.h>
#include <rex/logging.h>
#include <rex/cvar.h>

#include <cstdio>
#include <filesystem>

#ifdef _WIN32
#include <windows.h>
#include <dbghelp.h>

// VEH handler: catch null page reads in guest memory and return 0
// This handles the case where game code dereferences a not-yet-initialized pointer
static LONG CALLBACK NullPageHandler(EXCEPTION_POINTERS* ep) {
    auto* ctx = ep->ContextRecord;
    auto* rec = ep->ExceptionRecord;
    if (rec->ExceptionCode != STATUS_ACCESS_VIOLATION) return EXCEPTION_CONTINUE_SEARCH;
    // Only handle reads (ExceptionInformation[0] == 0)
    if (rec->ExceptionInformation[0] != 0) return EXCEPTION_CONTINUE_SEARCH;
    uint64_t addr = rec->ExceptionInformation[1];
    // Check if accessing guest null page (base + 0x0000 to base + 0xFFFF)
    uint64_t base = ctx->Rsi;  // RSI = base pointer in generated code
    if (base >= 0x100000000ULL && base <= 0x200000000ULL &&
        addr >= base && addr < base + 0x10000) {
        // Decode the faulting instruction to determine destination register
        // For mov reg, [mem] instructions, we zero the destination and skip
        uint8_t* rip = (uint8_t*)ctx->Rip;
        // REX prefix + opcode analysis for common load instructions
        int rex = 0, oplen = 0;
        uint8_t op = rip[0];
        if ((op & 0xF0) == 0x40) { rex = op; op = rip[1]; oplen = 1; }
        if (op == 0x8B) { // MOV r, r/m
            uint8_t modrm = rip[oplen + 1];
            int reg = (modrm >> 3) & 7;
            if (rex & 0x04) reg += 8; // REX.R
            // Determine instruction length (modrm + optional SIB + disp)
            int mod = (modrm >> 6) & 3;
            int rm = modrm & 7;
            int insn_len = oplen + 2; // prefix + opcode + modrm
            if (rm == 4 && mod != 3) insn_len++; // SIB byte
            if (mod == 0 && rm == 5) insn_len += 4; // RIP-relative
            else if (mod == 1) insn_len += 1;
            else if (mod == 2) insn_len += 4;
            // Zero the destination register
            uint64_t* regs[] = { &ctx->Rax, &ctx->Rcx, &ctx->Rdx, &ctx->Rbx,
                                  &ctx->Rsp, &ctx->Rbp, &ctx->Rsi, &ctx->Rdi,
                                  &ctx->R8, &ctx->R9, &ctx->R10, &ctx->R11,
                                  &ctx->R12, &ctx->R13, &ctx->R14, &ctx->R15 };
            if (reg < 16) *regs[reg] = 0;
            ctx->Rip += insn_len;
            static int _nullpage_count = 0;
            if (++_nullpage_count <= 20) {
                fprintf(stderr, "[NULLPAGE] Read from guest addr 0x%04llX at RIP+%d, zeroed reg %d\n",
                        addr - base, insn_len, reg);
                fflush(stderr);
            }
            return EXCEPTION_CONTINUE_EXECUTION;
        }
        // Unhandled instruction encoding - fall through to crash handler
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static LONG WINAPI CrashHandler(EXCEPTION_POINTERS* ep) {
    auto* ctx = ep->ContextRecord;
    auto* rec = ep->ExceptionRecord;
    fprintf(stderr, "\n========== CRASH ==========\n");
    fprintf(stderr, "Thread: %lu\n", GetCurrentThreadId());
    fprintf(stderr, "Exception: 0x%08lX at RIP=0x%016llX\n",
            rec->ExceptionCode, (unsigned long long)ctx->Rip);
    fprintf(stderr, "Access address: 0x%016llX (%s)\n",
            (unsigned long long)rec->ExceptionInformation[1],
            rec->ExceptionInformation[0] == 0 ? "READ" : "WRITE");
    fprintf(stderr, "RAX=0x%016llX RBX=0x%016llX RCX=0x%016llX RDX=0x%016llX\n",
            ctx->Rax, ctx->Rbx, ctx->Rcx, ctx->Rdx);
    fprintf(stderr, "RSI=0x%016llX RDI=0x%016llX RSP=0x%016llX RBP=0x%016llX\n",
            ctx->Rsi, ctx->Rdi, ctx->Rsp, ctx->Rbp);
    fprintf(stderr, "R8 =0x%016llX R9 =0x%016llX R10=0x%016llX R11=0x%016llX\n",
            ctx->R8, ctx->R9, ctx->R10, ctx->R11);
    fprintf(stderr, "R12=0x%016llX R13=0x%016llX R14=0x%016llX R15=0x%016llX\n",
            ctx->R12, ctx->R13, ctx->R14, ctx->R15);
    // Try to read PPC context from RDI (PPCContext* in generated code convention)
    __try {
        PPCContext* ppc = (PPCContext*)ctx->Rdi;
        if (ppc) {
            fprintf(stderr, "\nPPC Context (from RDI):\n");
            fprintf(stderr, "  LR=0x%08X  CTR=0x%08X\n", (uint32_t)ppc->lr, ppc->ctr.u32);
            fprintf(stderr, "  r0=0x%08X  r1=0x%08X  r3=0x%08X  r4=0x%08X\n",
                    ppc->r0.u32, ppc->r1.u32, ppc->r3.u32, ppc->r4.u32);
            fprintf(stderr, "  r5=0x%08X  r6=0x%08X  r7=0x%08X  r8=0x%08X\n",
                    ppc->r5.u32, ppc->r6.u32, ppc->r7.u32, ppc->r8.u32);
            fprintf(stderr, "  r11=0x%08X  r12=0x%08X  r28=0x%08X  r29=0x%08X\n",
                    ppc->r11.u32, ppc->r12.u32, ppc->r28.u32, ppc->r29.u32);
            fprintf(stderr, "  r30=0x%08X  r31=0x%08X\n",
                    ppc->r30.u32, ppc->r31.u32);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        fprintf(stderr, "\nPPC Context: <unreadable>\n");
    }
    // Stack trace
    fprintf(stderr, "\nStack (RSP):\n");
    uint64_t* sp = (uint64_t*)ctx->Rsp;
    for (int i = 0; i < 16; i++) {
        __try {
            fprintf(stderr, "  [RSP+%02X] = 0x%016llX\n", i*8, sp[i]);
        } __except(EXCEPTION_EXECUTE_HANDLER) {
            fprintf(stderr, "  [RSP+%02X] = <unreadable>\n", i*8);
        }
    }
    fprintf(stderr, "===========================\n");
    fflush(stderr);
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

int main(int argc, char** argv) {
#ifdef _WIN32
    AddVectoredExceptionHandler(1, NullPageHandler);
    SetUnhandledExceptionFilter(CrashHandler);
#endif
    fprintf(stderr, "[test] Starting ReXGlue boot test...\n");
    fflush(stderr);

    // Parse cvars
    rex::cvar::Init(argc, argv);

    fprintf(stderr, "[test] CVARs initialized\n");
    fflush(stderr);

    // Init logging
    auto log_config = rex::BuildLogConfig(nullptr, "trace", {});
    rex::InitLogging(log_config);

    fprintf(stderr, "[test] Logging initialized\n");
    fflush(stderr);

    std::filesystem::path game_dir;
    if (argc > 1) {
        game_dir = argv[1];
    } else {
        game_dir = "E:/vig8/extracted";
    }

    fprintf(stderr, "[test] Game dir: %s\n", game_dir.string().c_str());
    fflush(stderr);

    // Create runtime (tool mode - no GPU)
    fprintf(stderr, "[test] Creating Runtime...\n");
    fflush(stderr);

    auto runtime = std::make_unique<rex::Runtime>(game_dir);

    fprintf(stderr, "[test] Runtime created, calling Setup...\n");
    fflush(stderr);

    auto status = runtime->Setup(
        static_cast<uint32_t>(PPC_CODE_BASE),
        static_cast<uint32_t>(PPC_CODE_SIZE),
        static_cast<uint32_t>(PPC_IMAGE_BASE),
        static_cast<uint32_t>(PPC_IMAGE_SIZE),
        PPCFuncMappings);

    fprintf(stderr, "[test] Setup returned: 0x%08X\n", status);
    fflush(stderr);

    if (status != 0) {
        fprintf(stderr, "[test] Setup FAILED\n");
        return 1;
    }

    // Load XEX
    fprintf(stderr, "[test] Loading XEX...\n");
    fflush(stderr);

    status = runtime->LoadXexImage("game:\\default.xex");
    fprintf(stderr, "[test] LoadXexImage returned: 0x%08X\n", status);
    fflush(stderr);

    if (status != 0) {
        fprintf(stderr, "[test] LoadXexImage FAILED\n");
        return 1;
    }

    fprintf(stderr, "[test] Boot test PASSED - XEX loaded successfully!\n");
    fflush(stderr);

    // Launch module
    fprintf(stderr, "[test] Launching module...\n");
    fflush(stderr);

    auto thread = runtime->LaunchModule();
    if (thread) {
        fprintf(stderr, "[test] Module launched, waiting...\n");
        fflush(stderr);
        thread->Wait(0, 0, 0, nullptr);
    }

    fprintf(stderr, "[test] Done.\n");
    return 0;
}
