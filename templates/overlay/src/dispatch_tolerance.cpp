// dispatch_tolerance.cpp -- tolerate calls to null/invalid/unregistered guest functions.
//
// v0.8.0's rex::runtime::ResolveIndirectFunction returns a trap that REX_FATALs
// when the guest makes an indirect call to an address that isn't a registered
// function (e.g. a null function pointer left behind by a failed file open, or a
// vtable slot the game never initialized). The original XenonRecomp-era toolkit's
// PPC_CALL_INDIRECT_FUNC instead NULL-checked and skipped such calls; many titles
// rely on that tolerance. This restores it by overriding the (exported) resolver
// to return a no-op trampoline for invalid targets, so the guest continues.
//
// Add to your project's sources and add /force:multiple at link (we redefine an
// exported rexruntime symbol; project objects link first, so ours wins):
//
//     target_sources(mygame PRIVATE src/dispatch_tolerance.cpp)
//     if(WIN32)
//       target_link_options(mygame PRIVATE "LINKER:/force:multiple")
//     endif()
//
// Note: tolerating an invalid call lets the game continue, but the call does
// nothing and returns 0 -- if the game genuinely needed that function, you'll
// likely surface a follow-on bug. Treat a flood of "tolerated" log lines as a
// signal to find the real root cause (an unimplemented import, a failed load,
// a mis-detected function boundary), not as a fix in itself.

#include <cstdio>

#include <rex/ppc/context.h>
#include <rex/runtime.h>
#include <rex/system/function_dispatcher.h>

namespace {

// No-op stand-in for an unresolved indirect call: log the first few, return 0.
void NoopTrap(PPCContext& ctx, uint8_t* /*base*/) {
  static int logged = 0;
  if (logged < 25) {
    if (std::FILE* f = std::fopen("dispatch_tolerance.log", "a")) {
      std::fprintf(f, "tolerated indirect call to unregistered target 0x%08X\n",
                   (unsigned)ctx.last_indirect_target);
      std::fclose(f);
    }
    ++logged;
  }
  ctx.r3.u64 = 0;
}

}  // namespace

namespace rex::runtime {

// Overrides the SDK definition (exported; /force:multiple selects ours).
::PPCFunc* ResolveIndirectFunction(uint32_t guest_address) {
  if (Runtime* rt = Runtime::instance())
    if (FunctionDispatcher* d = rt->function_dispatcher())
      if (::PPCFunc* f = d->GetFunction(guest_address))
        return f;
  return &NoopTrap;
}

}  // namespace rex::runtime
