// stubs.cpp -- project-level kernel stubs for APIs the ReXGlue runtime doesn't export.
//
// Add this file to your project's sources (the AEGISWING_SOURCES / <name>_SOURCES
// list in the CMakeLists.txt that `rexglue init` generated).
//
// WHEN YOU NEED THIS: codegen succeeds and the project compiles, but the LINK
// fails with `undefined symbol: __declspec(dllimport) _SomeXboxApi`. That means
// the recompiled game imports a kernel/XAM function that rexruntime.dll does not
// export. Provide it here with the v0.8.0 hook macros from <rex/hook.h>.
//
// Two kinds of stub:
//   1. MISSING API (not in rexruntime)         -> define it here (this file).  SAFE.
//   2. OVERRIDE an API the SDK already exports  -> advanced; see templates/STUBS.md.
//
// The macros (from <rex/hook.h>):
//   REX_EXPORT(__imp__Name, entry_fn)   hook + register; entry_fn is a normal C++
//                                        function with auto-marshaled args/return.
//   REX_EXPORT_STUB(__imp__Name)         no-op stub, logs a warning when called.
//   REX_EXPORT_STUB_RETURN(__imp__Name, v)  stub returning a fixed value.
//   REX_HOOK_RAW(name) { ... ctx/base ... }  raw PPCContext access when you need it.

#include <rex/hook.h>
#include <rex/types.h>
#include <rex/system/xtypes.h>
#include <rex/system/kernel_state.h>

// ---------------------------------------------------------------------------
// EXAMPLE (verified): XUsbcam (Xbox 360 Vision Camera).
//
// The SDK implements these in src/kernel/xboxkrnl/xboxkrnl_usbcam.cpp but it is
// commented out of the runtime build, so the symbols aren't exported. Many XBLA
// titles import the camera API and never use it -- Create must return success
// (some titles abort init on failure), the rest can be no-ops.
//
// DELETE this block if your title doesn't import XUsbcam* (the linker will tell
// you which symbols it actually needs).
// ---------------------------------------------------------------------------
namespace rex::kernel::xboxkrnl {

u32 XUsbcamCreate_entry(u32 buffer, u32 buffer_size, mapped_void unk3_ptr) {
  return X_STATUS_SUCCESS;  // success: titles may abort init on a nonzero result
}
u32 XUsbcamGetState_entry() { return 0; }  // 0 = camera not connected

}  // namespace rex::kernel::xboxkrnl

REX_EXPORT(__imp__XUsbcamCreate, rex::kernel::xboxkrnl::XUsbcamCreate_entry)
REX_EXPORT(__imp__XUsbcamGetState, rex::kernel::xboxkrnl::XUsbcamGetState_entry)
REX_EXPORT_STUB(__imp__XUsbcamSetCaptureMode);
REX_EXPORT_STUB(__imp__XUsbcamGetConfig);
REX_EXPORT_STUB(__imp__XUsbcamSetConfig);
REX_EXPORT_STUB(__imp__XUsbcamReadFrame);
REX_EXPORT_STUB(__imp__XUsbcamSnapshot);
REX_EXPORT_STUB(__imp__XUsbcamSetView);
REX_EXPORT_STUB(__imp__XUsbcamGetView);
REX_EXPORT_STUB(__imp__XUsbcamDestroy);
REX_EXPORT_STUB(__imp__XUsbcamReset);

// ---------------------------------------------------------------------------
// ADD YOUR TITLE'S MISSING STUBS BELOW.
//
// For each `undefined symbol: _Foo` at link, add one line. Pick the form that
// matches what the game expects back:
//
//   REX_EXPORT_STUB(__imp__Foo);                 // returns nothing
//   REX_EXPORT_STUB_RETURN(__imp__Foo, 0);       // returns a fixed value in r3
//
// Or, for real behavior, write a typed entry function with auto-marshaled args
// (u32/u64 by value; mapped_u32/mapped_u64/mapped_void/ppc_ptr_t<T> for guest
// pointers, which byte-swap on access) and register it:
//
//   static u32 Foo_entry(u32 arg, mapped_u32 out_ptr) {
//     if (out_ptr) *out_ptr = 0;   // writes byte-swapped to guest memory
//     return X_E_SUCCESS;
//   }
//   REX_EXPORT(__imp__Foo, Foo_entry)
// ---------------------------------------------------------------------------
