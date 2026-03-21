#!/usr/bin/env python3
"""
Post-codegen fixup for Xbox 360 static recompilation projects.
Re-applies safety macro overrides to the generated *_init.h after codegen
regenerates it. This is necessary because codegen overwrites the header.

Run this after every `rexglue.exe codegen` pass.

Usage: py post_codegen.py <init_header> <config_header>
  e.g. py post_codegen.py generated/game_init.h game_config.h
"""

import sys
import argparse
from pathlib import Path


def make_safety_overrides(config_header, code_start_macro, code_end_macro):
    """Generate the safety override block for a given config header."""
    return f'''
// ============================================================================
// Safety Macro Overrides (re-applied by post_codegen.py)
// ============================================================================
#include "{config_header}"

// Safe indirect function call dispatch
#ifdef PPC_CALL_INDIRECT_FUNC
#undef PPC_CALL_INDIRECT_FUNC
#endif
#define PPC_CALL_INDIRECT_FUNC(ctx, target) \\
    do {{ \\
        if ((target) == 0) {{ \\
            ctx.r3.u64 = 0; \\
            break; \\
        }} \\
        if ((target) < {code_start_macro} || (target) >= {code_end_macro}) {{ \\
            ctx.r3.u64 = 0; \\
            break; \\
        }} \\
        auto* __fn = PPCFuncTable::getFunc(target); \\
        if (__fn == nullptr) {{ \\
            ctx.r3.u64 = 0; \\
            break; \\
        }} \\
        __fn(ctx, target); \\
    }} while(0)

// Unimplemented PPC instruction handler (warn, don't crash)
#ifdef PPC_UNIMPLEMENTED
#undef PPC_UNIMPLEMENTED
#endif
#define PPC_UNIMPLEMENTED(ctx, addr, opcode) \\
    do {{ \\
        static bool __warned = false; \\
        if (!__warned) {{ \\
            printf("[RECOMP] WARNING: Unimplemented PPC instruction at 0x%08X (opcode: 0x%08X)\\n", \\
                   (unsigned)(addr), (unsigned)(opcode)); \\
            __warned = true; \\
        }} \\
    }} while(0)

// ============================================================================
'''


def main():
    parser = argparse.ArgumentParser(
        description='Re-apply safety macro overrides to a generated init header after codegen.')
    parser.add_argument('init_header', help='Path to the generated *_init.h file')
    parser.add_argument('config_header', help='Name of the game config header to #include (e.g. game_config.h)')
    parser.add_argument('--code-start', default='PPC_CODE_BASE',
                        help='Macro name for code start address (default: PPC_CODE_BASE)')
    parser.add_argument('--code-end', default='(PPC_CODE_BASE + PPC_CODE_SIZE)',
                        help='Macro expression for code end address (default: PPC_CODE_BASE + PPC_CODE_SIZE)')
    args = parser.parse_args()

    init_header = Path(args.init_header)

    if not init_header.exists():
        print(f"ERROR: {init_header} not found. Run codegen first.")
        sys.exit(1)

    content = init_header.read_text(encoding='utf-8')

    # Check if overrides are already present
    if 'Safety Macro Overrides (re-applied by post_codegen.py)' in content:
        print("Safety overrides already present. Skipping.")
        return

    overrides = make_safety_overrides(args.config_header, args.code_start, args.code_end)

    # Find the #pragma once line and insert overrides after it
    if '#pragma once' in content:
        content = content.replace('#pragma once', '#pragma once\n' + overrides, 1)
    else:
        content = overrides + '\n' + content

    init_header.write_text(content, encoding='utf-8')
    print(f"Safety overrides applied to {init_header}")
    print(f"  - PPC_CALL_INDIRECT_FUNC: NULL check + range validation + slot check")
    print(f"  - PPC_UNIMPLEMENTED: warn-and-skip (no crash)")


if __name__ == '__main__':
    main()
